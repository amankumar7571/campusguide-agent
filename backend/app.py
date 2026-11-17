"""CampusGuide Agent — FastAPI app.

Endpoints: /health, /auth/register, /auth/login, /chat, /documents
(upload/list, admin), /feedback, /ingest (background job), /eval,
/stats (placement stats via the SQL tool), /drafts (+ approve).
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .auth import (create_token, get_current_user, hash_password,
                   require_admin, verify_password)
from .config import CORS_ORIGINS, DOCS_DIR, MAX_TOKENS_PER_REQUEST, TOP_K
from .db import (Chunk, Document, Draft, Feedback, Job, PlacementStat,
                 SessionLocal, User, get_db, init_db)
from .embeddings import embedder_name
from .eval import run_eval
from .graph import ask as graph_ask, make_graph
from .guardrails import guard_input
from .ingest import get_retriever, run_ingest_job
from .seed import seed
from .sql_agent import (SQLValidationError, natural_language_to_sql, run_sql)

app = FastAPI(title="CampusGuide Agent",
              description="Stateful LangGraph multi-agent RAG over official KIET documents.")
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS,
                   allow_methods=["*"], allow_headers=["*"])

_graph = None


def _sql_runner(sql):
    db = SessionLocal()
    try:
        return run_sql(db, sql)
    finally:
        db.close()


def get_graph():
    global _graph
    if _graph is None:
        retriever = get_retriever()
        _graph = make_graph(retriever, _sql_runner)
    return _graph


@app.on_event("startup")
def startup():
    seed()


# ---------- schemas ----------
class RegisterIn(BaseModel):
    email: str
    password: str = Field(min_length=6)
    role: str = "student"


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6)
    # Admins may pass another user's email to reset that account.
    email: str = ""


class LoginIn(BaseModel):
    email: str
    password: str


class ChatIn(BaseModel):
    question: str
    thread_id: str = "default"


class FeedbackIn(BaseModel):
    question: str
    answer: str
    vote: str  # up|down
    comment: str = ""


class StatsIn(BaseModel):
    question: str = "List companies with offers"


class DraftApproveIn(BaseModel):
    approve: bool = True


# ---------- endpoints ----------
@app.get("/health")
def health():
    return {"status": "ok", "embedder": embedder_name(),
            "sample_data": False,
            "sample_placement_data": True,
            "note": "Corpus: official KIET documents fetched 11 Nov 2026. "
                    "Placement stats table is still sample data."}


@app.post("/auth/register")
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(400, "Email already registered")
    if body.role not in ("student", "admin"):
        raise HTTPException(400, "Role must be student or admin")
    user = User(email=body.email, password_hash=hash_password(body.password),
                role=body.role)
    db.add(user)
    db.commit()
    return {"email": user.email, "role": user.role,
            "token": create_token(user.email, user.role)}


@app.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid credentials")
    return {"email": user.email, "role": user.role,
            "token": create_token(user.email, user.role)}


@app.post("/auth/change-password")
def change_password(body: ChangePasswordIn,
                    user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    target_email = body.email or user.email
    if target_email != user.email and user.role != "admin":
        raise HTTPException(403, "Only admins can change another user's password")
    # current_password is always the *requester's own* password: proof of
    # identity for a self-change, and re-authentication for an admin reset.
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(401, "Current password is incorrect")
    target = db.query(User).filter(User.email == target_email).first()
    if not target:
        raise HTTPException(404, "User not found")
    target.password_hash = hash_password(body.new_password)
    db.commit()
    return {"status": "password updated", "email": target.email}


@app.post("/chat")
def chat(body: ChatIn, user: User = Depends(get_current_user)):
    try:
        question = guard_input(body.question, MAX_TOKENS_PER_REQUEST)
    except ValueError as exc:
        return {"answer": str(exc), "citations": [], "route": "guardrail",
                "sources": []}
    try:
        result = graph_ask(get_graph(), question, thread_id=body.thread_id)
    except Exception:
        # B-04: an embedder/graph failure must never surface as a raw 500
        # with a traceback. Degrade to a clean 503 the user can act on.
        raise HTTPException(
            503, "The chat service is temporarily unavailable — please try "
                 "again in a minute. If the problem persists, contact an admin.")
    if result.get("draft"):
        db = SessionLocal()
        try:
            db.add(Draft(title=body.question[:200], body=result["draft"],
                         sources=json.dumps(result.get("citations", [])),
                         created_by=user.email))
            db.commit()
        finally:
            db.close()
    return {"answer": result["answer"], "citations": result["citations"],
            "route": result["route"],
            "sources": [{"doc_title": p["doc_title"], "section": p["section"],
                         "citation": p["citation"], "score": p["score"]}
                        for p in result.get("passages", [])],
            "sql_result": result.get("sql_result"),
            "draft_pending_approval": bool(result.get("draft"))}


@app.get("/documents")
def list_documents(user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    docs = db.query(Document).all()
    return [{"slug": d.slug, "title": d.title, "filename": d.filename,
             "is_sample": d.is_sample,
             "chunks": db.query(Chunk).filter(Chunk.document_id == d.id).count()}
            for d in docs]


@app.post("/documents")
async def upload_document(file: UploadFile = File(...),
                          user: User = Depends(require_admin)):
    if not file.filename.endswith((".md", ".txt")):
        raise HTTPException(400, "Only .md / .txt documents are accepted")
    dest = DOCS_DIR / Path(file.filename).name
    dest.write_bytes(await file.read())
    return {"filename": dest.name, "message": "Uploaded. Run POST /ingest to index it."}


@app.post("/ingest")
def ingest(background: BackgroundTasks, user: User = Depends(require_admin),
           db: Session = Depends(get_db)):
    background.add_task(run_ingest_job)
    return {"status": "started",
            "message": "Ingestion running in background; check /jobs for status."}


@app.get("/jobs")
def list_jobs(user: User = Depends(require_admin),
              db: Session = Depends(get_db)):
    jobs = db.query(Job).order_by(Job.id.desc()).limit(20).all()
    return [{"id": j.id, "kind": j.kind, "status": j.status,
             "rows_processed": j.rows_processed,
             "duration_seconds": j.duration_seconds, "detail": j.detail,
             "created_at": str(j.created_at)} for j in jobs]


@app.post("/feedback")
def feedback(body: FeedbackIn, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    if body.vote not in ("up", "down"):
        raise HTTPException(400, "vote must be up or down")
    db.add(Feedback(question=body.question, answer=body.answer,
                    vote=body.vote, comment=body.comment))
    db.commit()
    return {"status": "recorded"}


@app.post("/eval")
def run_eval_endpoint(user: User = Depends(require_admin)):
    retriever = get_retriever()

    def answer_fn(q, passages):
        from .graph import _answer_from_passages
        ans, _ = _answer_from_passages(q, passages)
        return ans

    return run_eval(retriever, answer_fn)


@app.post("/stats")
def stats(body: StatsIn, user: User = Depends(get_current_user),
          db: Session = Depends(get_db)):
    try:
        sql = natural_language_to_sql(body.question)
        cols, rows = run_sql(db, sql)
    except SQLValidationError as exc:
        raise HTTPException(400, str(exc))
    return {"sql": sql, "columns": cols, "rows": rows,
            "note": "Sample placement data — not real figures."}


@app.get("/stats")
def stats_table(user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    rows = db.query(PlacementStat).all()
    return [{"company": r.company, "year": r.year, "role": r.role,
             "offers": r.offers, "ctc_lpa": r.ctc_lpa,
             "is_sample": r.is_sample} for r in rows]


@app.get("/drafts")
def list_drafts(user: User = Depends(require_admin),
                db: Session = Depends(get_db)):
    return [{"id": d.id, "title": d.title, "body": d.body,
             "sources": d.sources, "status": d.status,
             "created_by": d.created_by} for d in
            db.query(Draft).order_by(Draft.id.desc()).all()]


@app.post("/drafts/{draft_id}/approve")
def approve_draft(draft_id: int, body: DraftApproveIn,
                  user: User = Depends(require_admin),
                  db: Session = Depends(get_db)):
    draft = db.query(Draft).filter(Draft.id == draft_id).first()
    if not draft:
        raise HTTPException(404, "Draft not found")
    draft.status = "approved" if body.approve else "rejected"
    db.commit()
    return {"id": draft.id, "status": draft.status,
            "message": ("Approved — an admin may now publish it outside this "
                        "system. Nothing is published automatically.")
            if body.approve else "Rejected."}


if __name__ == "__main__":
    import uvicorn
    init_db()
    uvicorn.run("backend.app:app", host="127.0.0.1", port=8000, reload=False)
