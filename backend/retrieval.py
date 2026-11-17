"""Hybrid retrieval: BM25 + dense vectors, reciprocal-rank fusion, rerank.

BM25 is implemented in-house (no extra dependency). Dense vectors come
from embeddings.py (Gemini when keyed, TF-IDF fallback otherwise).
Every returned passage carries document title + section for citations.

Query expansion: the ordinance writes MSE / ESE / CIE far more often than
the spelled-out forms students type ("end semester exam"). The acronym is
appended to the query so both BM25 and dense search see it, closing that
lexical gap. Longest phrases first; each acronym is added at most once.
"""
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path

import numpy as np

from .config import DATA_DIR, RETRIEVAL_MIN_SCORE, RRF_K, TOP_K
from .embeddings import LocalTfidfEmbedder, get_embedder

VECTOR_CACHE_DIR = DATA_DIR / "vector_cache"
# Gemini embedding dimensionality (gemini-embedding-001 default).
GEMINI_EMBED_DIM = 3072

_TOKEN = re.compile(r"[a-z0-9]+")

# (spelled-out phrase, acronym) — checked against the lowercased query.
ACRONYM_EXPANSIONS = [
    ("end semester examinations", "ese"),
    ("end semester examination", "ese"),
    ("end semester exam", "ese"),
    ("end semester", "ese"),
    ("mid semester examinations", "mse"),
    ("mid semester examination", "mse"),
    ("mid semester exam", "mse"),
    ("mid-semester", "mse"),
    ("mid semester", "mse"),
    ("continuous internal evaluation", "cie"),
]


# Synonym expansion: students type "pass marks" / "exam pattern" but the
# ordinance writes "passing standards" / "assessment (pattern)". Without
# it, the pass-marks chunk shares almost no tokens with the question
# (B-06: "exam pattern and pass marks" never retrieved it). Same
# longest-phrase-first pattern as the acronym expansion.
SYNONYM_EXPANSIONS = [
    ("pass marks", "passing minimum"),
    ("pass mark", "passing minimum"),
    ("exam pattern", "assessment"),
]


def expand_query(query: str) -> str:
    """Append acronyms and synonyms for exam terms found in the query."""
    lowered = query.lower()
    extra = {acronym for phrase, acronym in ACRONYM_EXPANSIONS
             if phrase in lowered}
    for phrase, terms in SYNONYM_EXPANSIONS:
        if phrase in lowered:
            extra.update(terms.split())
    extra = sorted(extra)
    return query + " " + " ".join(extra) if extra else query


def tokenize(text: str):
    return _TOKEN.findall(text.lower())


class BM25:
    def __init__(self, docs, k1: float = 1.5, b: float = 0.75):
        self.docs = [tokenize(d) for d in docs]
        self.k1, self.b = k1, b
        self.doc_len = [len(d) for d in self.docs]
        self.avg_len = sum(self.doc_len) / max(len(self.doc_len), 1)
        df = Counter()
        for d in self.docs:
            for term in set(d):
                df[term] += 1
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5))
                    for t, c in df.items()}

    def score(self, query: str):
        q_terms = tokenize(query)
        scores = []
        for i, doc in enumerate(self.docs):
            tf = Counter(doc)
            s = 0.0
            for term in q_terms:
                if term not in tf:
                    continue
                f = tf[term]
                denom = f + self.k1 * (1 - self.b + self.b * self.doc_len[i]
                                       / (self.avg_len or 1))
                s += self.idf.get(term, 0) * f * (self.k1 + 1) / denom
            scores.append(s)
        return scores


def rrf(rank_lists, k: int = RRF_K):
    """Reciprocal-rank fusion over lists of chunk indices (best rank first)."""
    fused = Counter()
    for ranks in rank_lists:
        for rank, idx in enumerate(ranks):
            fused[idx] += 1.0 / (k + rank + 1)
    return fused


def _corpus_fingerprint(chunks, embedder_name: str) -> str:
    """Hash of chunk contents + embedder: cache key for stored vectors.
    Chunk DB ids churn on every re-ingest, so they must NOT be part of
    the key — doc slug + section + text (in corpus order) is stable."""
    payload = json.dumps([[c["doc_slug"], c["section"], c["text"]]
                          for c in chunks],
                         ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(
        f"{embedder_name}|{payload}".encode("utf-8")).hexdigest()[:16]


def _cache_path(embedder_name: str, fingerprint: str) -> Path:
    return VECTOR_CACHE_DIR / f"{embedder_name}-{fingerprint}.npz"


def _load_vectors(embedder_name: str, fingerprint: str, n_chunks: int,
                  expected_dim: int):
    """Return cached vectors if they match this corpus + embedder, else None."""
    path = _cache_path(embedder_name, fingerprint)
    if not path.exists():
        return None
    try:
        data = np.load(path)
        vectors = data["vectors"]
        if vectors.shape == (n_chunks, expected_dim):
            return vectors
    except Exception:
        return None
    return None


def _save_vectors(embedder_name: str, fingerprint: str, vectors) -> None:
    try:
        VECTOR_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(_cache_path(embedder_name, fingerprint),
                            vectors=np.asarray(vectors, dtype=float))
    except Exception:
        pass  # cache is an optimisation; a failed write must not break search


class Retriever:
    """In-memory hybrid index built from the chunk table."""

    def __init__(self, chunks):
        # chunks: [{id, doc_slug, doc_title, section, text}]
        self.chunks = list(chunks)
        self.texts = [c["text"] for c in self.chunks]
        self.bm25 = BM25(self.texts) if self.texts else None
        self.embedder = get_embedder()
        if self.texts:
            if self.embedder.name == "tfidf-local":
                self.embedder.fit(self.texts)
            self.vectors = self._load_or_embed()
        else:
            self.vectors = np.zeros((0, 1))

    def _expected_dim(self) -> int:
        if self.embedder.name == "gemini-embedding-001":
            return GEMINI_EMBED_DIM
        vectorizer = getattr(self.embedder, "vectorizer", None)
        return len(getattr(vectorizer, "vocabulary_", {}) or {})

    def _load_or_embed(self):
        """Vectors from the disk cache when the corpus is unchanged;
        otherwise embed once (batched) and cache the result. A Gemini
        failure degrades to the local TF-IDF embedder instead of dying."""
        fingerprint = _corpus_fingerprint(self.chunks, self.embedder.name)
        cached = _load_vectors(self.embedder.name, fingerprint,
                               len(self.texts), self._expected_dim())
        if cached is not None:
            return cached
        try:
            vectors = np.array(self.embedder.embed(self.texts))
        except Exception:
            if self.embedder.name == "tfidf-local":
                raise
            # B-04: fall back to the local embedder on any Gemini failure.
            self.embedder = LocalTfidfEmbedder().fit(self.texts)
            fingerprint = _corpus_fingerprint(self.chunks, self.embedder.name)
            cached = _load_vectors(self.embedder.name, fingerprint,
                                   len(self.texts), self._expected_dim())
            if cached is not None:
                return cached
            vectors = np.array(self.embedder.embed(self.texts))
        _save_vectors(self.embedder.name, fingerprint, vectors)
        return vectors

    def _result_dict(self, idx, final, bm25_scores, dense_scores):
        c = self.chunks[idx]
        return {
            "chunk_id": c["id"], "doc_slug": c["doc_slug"],
            "doc_title": c["doc_title"], "section": c["section"],
            "text": c["text"], "score": round(float(final), 4),
            "bm25": round(float(bm25_scores[idx]), 4),
            "dense": round(float(dense_scores[idx]), 4),
            "citation": f"{c['doc_title']} — {c['section'] or 'General'}",
        }

    def search(self, query: str, top_k: int = TOP_K):
        query = expand_query(query)
        if not self.chunks:
            return []
        bm25_scores = self.bm25.score(query)
        bm25_rank = sorted(range(len(self.chunks)),
                           key=lambda i: -bm25_scores[i])
        q_vec = np.array(self.embedder.embed_query(query))
        dense_scores = (self.vectors @ q_vec).tolist() \
            if self.vectors.size else [0.0] * len(self.chunks)
        dense_rank = sorted(range(len(self.chunks)),
                            key=lambda i: -dense_scores[i])
        fused = rrf([bm25_rank, dense_rank])
        # Rerank: fused score + keyword-overlap bonus + dense score tiebreak.
        q_terms = set(tokenize(query))
        ranked = []
        for idx, fuse_score in fused.items():
            chunk_terms = set(tokenize(self.chunks[idx]["text"]))
            overlap = len(q_terms & chunk_terms) / max(len(q_terms), 1)
            final = fuse_score + 0.5 * overlap + 0.25 * max(dense_scores[idx], 0)
            ranked.append((final, idx))
        ranked.sort(reverse=True)
        results = []
        for final, idx in ranked[:top_k]:
            # A chunk must show real lexical or dense evidence; RRF alone
            # gives every chunk a positive score, so it cannot gate alone.
            if bm25_scores[idx] <= 0 and dense_scores[idx] < 0.1:
                continue
            results.append(self._result_dict(idx, final, bm25_scores,
                                             dense_scores))
        if not results and ranked:
            # B-15: the gate can empty the set for an in-corpus question
            # (e.g. "pass marks for ESE and CIE"). Fall back to the best
            # passage that has real lexical evidence; off-topic questions
            # score bm25 <= 0 everywhere, so they still get no results.
            for final, idx in ranked:
                if bm25_scores[idx] > 0:
                    results.append(self._result_dict(idx, final, bm25_scores,
                                                     dense_scores))
                    break
        return results

    def dense_only_search(self, query: str, top_k: int = TOP_K):
        """Vector-only baseline (for the eval comparison)."""
        query = expand_query(query)
        if not self.chunks:
            return []
        q_vec = np.array(self.embedder.embed_query(query))
        scores = (self.vectors @ q_vec).tolist()
        order = sorted(range(len(self.chunks)), key=lambda i: -scores[i])
        return [{"chunk_id": self.chunks[i]["id"],
                 "doc_slug": self.chunks[i]["doc_slug"],
                 "doc_title": self.chunks[i]["doc_title"],
                 "section": self.chunks[i]["section"],
                 "text": self.chunks[i]["text"],
                 "score": round(float(scores[i]), 4)}
                for i in order[:top_k]]
