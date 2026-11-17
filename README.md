# CampusGuide Agent

A stateful **LangGraph multi-agent RAG assistant** over college documents
(handbook, notices, placement rules). Built for a final-year B.Tech
student's portfolio — Python, FastAPI, LangGraph, React + Vite, SQLite
locally / Postgres + pgvector as the deploy target.

> ✅ **Real KIET documents loaded 11 Nov 2026.** The 10 documents in
> `data/documents/` are real official KIET documents fetched from kiet.edu /
> old.kiet.edu (Autonomous Ordinance 2024-25, fee structure 2026-27, hostel
> rules, placement records, FAQ, and index entries for the modal-viewer
> PDFs). Every document carries a source URL and a regime tag. The 12
> placement-stats rows are still sample data, and the sample documents are
> archived in `data/docs_sample_archive/`. See `docs/LOAD_LOG.md` for
> sources, regime tags and gaps.

## What is real vs sample

| Real | Sample / placeholder |
|---|---|
| FastAPI backend, LangGraph supervisor graph, hybrid retrieval (BM25 + dense + RRF + rerank, plus acronym query expansion), read-only SQL agent with allow-list validation, JWT auth, feedback logging, job table, MCP server, golden-set eval | All 12 placement-stats rows, the admin login `admin@campus.local / admin123` |
| TF-IDF local embedder (works with no key); Gemini embeddings when `GEMINI_API_KEY` is set | No real placement-stats table is publicly available; no official placement policy or AKTU ordinance was found publicly |

## Architecture

```
User question
  → guardrails (injection filter, off-topic check, PII masking, token budget)
  → LangGraph supervisor (SQLite checkpointer = conversation memory)
      ├─ retriever_agent : BM25 + dense vectors, RRF fusion, rerank, citations
      ├─ sql_agent       : NL → SELECT over placement_stats (allow-listed, read-only)
      └─ writer_agent    : drafts grounded text from passages only; saved as
                            pending_approval — an admin must approve via
                            POST /drafts/{id}/approve. Nothing auto-publishes.
```

- **Embeddings:** Gemini `gemini-embedding-001` only when `GEMINI_API_KEY`
  is set; otherwise a local TF-IDF embedder (`backend/embeddings.py`).
  The local default needs no key and no network.
- **Database:** SQLite locally (SQLAlchemy, same schema). Postgres +
  pgvector is the deploy target — see `docker-compose.yml`. Vectors are
  held in the in-memory TF-IDF index rebuilt at ingest, so the schema is
  portable; an optional pgvector `embedding` column migration is noted
  in `backend/db.py`.
- **Ingestion** runs as a background job (`POST /ingest`, `GET /jobs`),
  never in the request path. Drop `.md`/`.txt` files into
  `data/documents/` (or upload as admin) and re-run ingestion.

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # optional; GEMINI_API_KEY only if you have one
python -m backend.seed      # seeds sample placement data + admin user, ingests docs
uvicorn backend.app:app --host 127.0.0.1 --port 8000
# Frontend (separate terminal):
cd frontend && npm install && npm run dev   # or: npm run build
```

Default admin: `admin@campus.local` / `admin123` — change on first deploy.
Students register via `POST /auth/register`.

## API

| Endpoint | Auth | Notes |
|---|---|---|
| `GET /health` | — | status, embedder in use, sample-data flag |
| `POST /auth/register`, `POST /auth/login` | — | JWT, roles `student` / `admin` |
| `POST /chat` | JWT | `{question, thread_id}` → answer + citations + sources + route |
| `GET /documents`, `POST /documents` | JWT / admin upload | list / upload `.md`/`.txt` |
| `POST /ingest`, `GET /jobs` | admin | background ingestion, job status |
| `POST /feedback` | JWT | thumbs up/down per answer |
| `POST /eval` | admin | golden-set eval (see below) |
| `GET /stats`, `POST /stats` | JWT | placement stats via the SQL tool |
| `GET /drafts`, `POST /drafts/{id}/approve` | admin | human-in-the-loop publishing |

## Evaluation (golden set, 50 Q&A)

`data/golden_set.json` — 50 questions grounded in the real official KIET
documents loaded 11 Nov 2026 (old sample-based set kept at
`data/golden_set_sample_based_backup.json`), each with an expected answer,
expected documents, and expected keywords.
`scripts/run_eval.py` runs deterministic RAGAS-style metrics (no API key
needed). An LLM-judge pass is possible when `GEMINI_API_KEY` is set, but
the deterministic scores are the reported ones.

**Actual results, run 11 Nov 2026 (local TF-IDF embedder, no API key,
real corpus, after the acronym-expansion retrieval fix):**

| Metric | Hybrid (BM25 + dense + RRF) | Vector-only baseline |
|---|---|---|
| Context precision* | **0.840** | 0.836 |
| Context recall | **1.000** | 1.000 |
| Faithfulness | **0.830** | — |
| Answer relevance | **0.858** | — |

\* Chunk-level precision (RAGAS-style): a retrieved chunk counts as
relevant if it comes from an expected document or contains an expected
keyword. Doc-level precision was 0.337 and is misleading here — top-5
retrieval legitimately returns neighbouring same-topic chunks (e.g. other
attendance sections), so it is not reported as the headline number.

Retrieval fix, 11 Nov 2026: the retriever now expands spelled-out exam
terms to their acronyms before scoring (`end semester exam` → `ese`,
`mid semester` → `mse`, `continuous internal evaluation` → `cie`).
Before the fix, the §11 attendance chunk with the 75% figure ranked 38th
for the natural phrasing "minimum attendance required for a final-year
B.Tech student to appear in the end semester exam"; after the fix it
ranks 4th (inside top-5). Known remaining weakness: the extractive
answer quotes only the top 3 passages, so the 75% figure still does not
appear in the answer text for that phrasing — the §11 citation is listed,
but the figure is not quoted. Fixing that needs a second change (answer
builder using top-5 passages, or merging §11's two chunks at ingest).

For comparison, the same 50-question set run against the old sample-based
golden set on the real corpus scored 0.428 / 0.0 / 0.292 / 0.54 — those
numbers were meaningless because the old questions expected sample-doc
slugs that no longer exist, not because retrieval was that bad.

```bash
python scripts/run_eval.py --out eval_results.json   # or POST /eval as admin
python -m pytest tests/ -q                            # 19 tests
```

## MCP server

```bash
python -m backend.mcp_server   # stdio transport
```

Tools: `search_notices(query, top_k)` and `placement_stats(question)`
— the same retrieval and read-only SQL agent as the HTTP API.

## Adding real documents

1. Delete or replace the sample files in `data/documents/` (keep the
   `SAMPLE DOCUMENT` header only on sample files).
2. Add real `.md`/`.txt` files, or upload them as admin via
   `POST /documents`.
3. `POST /ingest` (admin) — the index rebuilds in the background.
4. Replace the sample placement rows (`backend/seed.py`,
   `SAMPLE_PLACEMENTS`) with real data, and extend
   `data/golden_set.json` with questions over the real corpus, then
   re-run the eval.

## Deploy notes ($0 stack)

- **Frontend:** Vercel free tier.
- **API:** Render free tier (web service sleeps when idle; first request
  after sleep is slow).
- **Database:** Supabase free tier with pgvector. **Caveats:**
  - Do **NOT** use Render's free Postgres — it is a 30-day trial, after
    which the database is deleted.
  - Supabase free projects pause after 7 days of inactivity; wake them
    from the dashboard.
  - Gemini free-tier limits are unstable and can change without notice;
    the app keeps working without a key via the local TF-IDF embedder.
- Set a long random `JWT_SECRET` and change the default admin password
  before any deployment. Never commit `.env`.

## Tests

`tests/` covers chunking, BM25 + RRF hybrid retrieval, SQL validation
(including `DROP TABLE` / injection strings), citation presence,
out-of-corpus refusal, prompt-injection refusal, PII masking, password
hashing, JWT round-trip, and supervisor routing. CI (`.github/workflows/ci.yml`)
runs pytest + the frontend build on PRs.
