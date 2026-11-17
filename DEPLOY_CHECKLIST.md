# CampusGuide — Deploy Checklist ($0 stack)

Target: frontend on Vercel (free), backend on Render (free web service),
database on Supabase free Postgres with pgvector. Do NOT use Render free
Postgres — it is a 30-day trial, then it is deleted.

## 0. Before you start

- [ ] Code is pushed to https://github.com/amankumar7571/campusguide-agent (main branch).
- [ ] You have accounts on Vercel, Render, and Supabase (all free tiers, no card needed).

## 1. Database — Supabase free Postgres

- [ ] Create a Supabase project (free tier).
- [ ] In the Supabase SQL editor, enable pgvector: `CREATE EXTENSION IF NOT EXISTS vector;`
- [ ] Copy the connection string (URI form). It looks like:
  `postgresql+psycopg2://postgres:<password>@db.<ref>.supabase.co:5432/postgres`
- [ ] Note: Supabase free pauses the project after 7 days idle — wake it in
  the Supabase dashboard if the app stops answering.

## 2. Backend — Render free web service

- [ ] In Render, create a Web Service from the repo (Dockerfile at the repo root).
- [ ] Start command: `uvicorn backend.app:app --host 0.0.0.0 --port $PORT`
  (Render assigns the port via `$PORT`; the Dockerfile's `--port 8000`
  is for local/docker-compose only.)
- [ ] Set these environment variables on the Render service:

  | Variable | Value | Required? |
  |---|---|---|
  | `DATABASE_URL` | Supabase connection string from step 1 | Yes |
  | `JWT_SECRET` | A fresh long random string (see below) | Yes |
  | `GEMINI_API_KEY` | Your Gemini API key | No — without it the app uses the local TF-IDF embedder |
  | `JWT_EXPIRE_MINUTES` | `480` | No (default 480) |
  | `TOP_K` | `5` | No (default 5) |

- [ ] Generate the JWT secret with: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`.
  Do NOT reuse the repo default (`dev-only-secret-change-me` / `change-me-to-a-long-random-secret`).
- [ ] Gemini note: the code uses model `gemini-embedding-001` in
  `backend/embeddings.py` (the older `text-embedding-004` name 404s for
  this key). Embeddings are batched (25/batch) and paced to ~75
  contents/min, and corpus vectors are cached under
  `data/vector_cache/` — the first cold start embeds the corpus once
  (~90s), later starts load from disk. If you leave the key unset,
  nothing breaks (TF-IDF fallback).

## 3. Frontend — Vercel

- [ ] In Vercel, import the repo, set Root Directory to `frontend/`.
- [ ] Build command `npm run build`, output directory `dist` (Vite defaults).
- [ ] Set environment variable `VITE_API_URL` to the Render backend URL,
  e.g. `https://campusguide-api.onrender.com` (no trailing slash).
  The frontend reads it in `src/App.jsx`; without it, `/api` only works
  with the local Vite dev proxy.
- [ ] Deploy.

## 4. Security — do these BEFORE sharing the URL

- [ ] Log in as the seeded admin (`admin@campus.local` / `admin123`) and
  change the admin password via `POST /auth/change-password`
  (authenticated; send `current_password` + `new_password`).
- [ ] Confirm `JWT_SECRET` on Render is the fresh random value, not the default.
- [ ] If you ever use `docker-compose.yml` locally, change the database
  password (`campusguide` in the file) — it is a placeholder.
- [ ] CORS is controlled by the `CORS_ORIGINS` env var (comma-separated).
  Default is the local dev frontend only; set it to the Vercel domain
  on deploy — never `*` for a public backend.

## 5. Post-deploy checks

- [ ] `GET <backend>/health` returns `status: ok`, `sample_data: false`,
  `embedder: tfidf-local` (or `gemini-embedding-001` if keyed).
  Documents are ingested automatically at startup (`seed()` calls
  `ingest_documents()`), so no manual ingest step is needed.
- [ ] Ask these four questions in the deployed UI and check the answers:
  attendance 75% for MSE2/ESE (with the Affiliated Batch / AKTU caveat),
  exam pattern ESE 30% / overall 40%, girls hostel entry 8:00 PM,
  B.Tech CSE (AI & ML) fees Rs. 1,90,000 tuition / Rs. 1,98,500 total.
  Known weakness (11 Nov 2026): the final-year attendance phrasing cites
  §11 but the answer text does not quote the 75% figure — see
  `docs/LOAD_LOG.md`.
- [ ] `POST /eval` as admin re-runs the golden-set eval (expect roughly
  precision 0.84, recall 1.0, faithfulness 0.83, relevance 0.86).

## 6. Known deploy-time caveats

- Render free instances sleep when idle — the first request after idle is slow.
- Supabase free pauses after 7 days idle — wake it in the dashboard.
- The 12 placement-stats rows are still SAMPLE data (fictional companies).
  The SQL agent answers from them; the UI labels them sample.
- The AKTU B.Tech ordinance (governs the 2023–27 Affiliated Batch) and the
  full texts of the University Ordinance, Student Manual 2025, Discipline
  Policy 2026-27 and Academic Calendar are NOT in the corpus yet — see
  `docs/LOAD_LOG.md` for what is missing and where to get it.
