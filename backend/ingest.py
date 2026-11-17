"""Ingestion: read data/documents/*.md|*.txt -> chunk -> DB, rebuild index.

Runs as a background job (see app.py /ingest), never in the request path.
A Job row records status / duration / rows processed.
"""
import time
from datetime import datetime, timezone
from pathlib import Path

from .chunking import chunk_document
from .config import DOCS_DIR
from .db import Chunk, Document, Job, SessionLocal
from .retrieval import Retriever

_retriever = None


def _slug(filename: str) -> str:
    return Path(filename).stem.lower().replace(" ", "-")


def ingest_documents(db=None) -> dict:
    """(Re)ingest every file in data/documents. Returns counts."""
    close = False
    if db is None:
        db = SessionLocal()
        close = True
    try:
        files = sorted(DOCS_DIR.glob("*.md")) + sorted(DOCS_DIR.glob("*.txt"))
        docs_in, chunks_in = 0, 0
        for path in files:
            text = path.read_text(encoding="utf-8", errors="ignore")
            is_sample = "SAMPLE DOCUMENT" in text[:2000]
            # Title = first real heading, not the SAMPLE banner line.
            headings = [ln.lstrip("# ").strip() for ln in text.splitlines()
                        if ln.startswith("# ")]
            title = next((h for h in headings if "SAMPLE DOCUMENT" not in h),
                         path.stem)
            # Strip the banner line before chunking so it never becomes
            # a document title or section name.
            text = "\n".join(ln for ln in text.splitlines()
                             if "SAMPLE DOCUMENT" not in ln)
            doc = db.query(Document).filter(
                Document.slug == _slug(path.name)).first()
            if doc:
                db.query(Chunk).filter(Chunk.document_id == doc.id).delete()
                doc.title, doc.filename, doc.is_sample = title, path.name, is_sample
            else:
                doc = Document(slug=_slug(path.name), title=title,
                               filename=path.name, is_sample=is_sample)
                db.add(doc)
                db.flush()
            for ch in chunk_document(text):
                db.add(Chunk(document_id=doc.id, section=ch["section"],
                             text=ch["text"], chunk_index=ch["chunk_index"]))
                chunks_in += 1
            docs_in += 1
        db.commit()
        # Drop documents whose source file was deleted from the folder.
        present = {p.name for p in files}
        for doc in db.query(Document).all():
            if doc.filename not in present:
                db.query(Chunk).filter(Chunk.document_id == doc.id).delete()
                db.delete(doc)
        db.commit()
        return {"documents": docs_in, "chunks": chunks_in}
    finally:
        if close:
            db.close()


def get_retriever() -> Retriever:
    """Cached in-memory hybrid index; rebuilt after each ingestion."""
    global _retriever
    if _retriever is None:
        _retriever = build_retriever()
    return _retriever


def build_retriever() -> Retriever:
    db = SessionLocal()
    try:
        rows = (db.query(Chunk, Document)
                .join(Document, Chunk.document_id == Document.id)
                .order_by(Document.slug, Chunk.chunk_index).all())
        chunks = [{"id": c.id, "doc_slug": d.slug, "doc_title": d.title,
                   "section": c.section, "text": c.text}
                  for c, d in rows]
        return Retriever(chunks)
    finally:
        db.close()


def rebuild_retriever():
    global _retriever
    _retriever = build_retriever()
    return _retriever


def run_ingest_job() -> dict:
    """Background-job wrapper: records a Job row with timing."""
    db = SessionLocal()
    job = Job(kind="ingest", status="running")
    db.add(job)
    db.commit()
    started = time.time()
    try:
        counts = ingest_documents(db)
        rebuild_retriever()
        job.status = "done"
        job.rows_processed = counts["chunks"]
        job.detail = f"{counts['documents']} documents, {counts['chunks']} chunks"
    except Exception as exc:
        job.status = "failed"
        job.detail = str(exc)
        db.commit()
        raise
    finally:
        job.duration_seconds = round(time.time() - started, 2)
        job.finished_at = datetime.now(timezone.utc)
        db.commit()
        db.close()
    return {"job_id": job.id, "status": job.status,
            "detail": job.detail, "duration_seconds": job.duration_seconds}
