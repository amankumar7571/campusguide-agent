# CampusGuide Agent — Independent Re-Test Report

**Date:** 12 November 2026
**Tester role:** independent re-test (did not fix code, deploy, or push; no
passwords/secrets/`.env` changed)
**Build under test:** CampusGuide Agent after the 12 Nov blocker-fix pass
(batched Gemini embeds + persisted vector cache, TF-IDF fallback / clean
503, top-5 quoting, rotated admin password + JWT secret, CORS via env,
`POST /auth/change-password`)
**Reference:** QA report `TEST_REPORT_2026-11-12.md` (NO-GO, 4 blockers,
5 majors, 6 minors). Fix pass claimed all blockers + assigned majors fixed,
26/26 pytest.
**Test environment:** local only, `http://127.0.0.1:8000`, SQLite.

## Verdict: GO for pushing to GitHub (both repos)

All four blockers are verified fixed by live testing, both test suites pass,
and the simulated push sets contain no secrets. Two new/remaining items
(R-01, R-02 below) should be fixed before any deployment or demo, but
neither blocks pushing code. The claimed eval improvement could **not** be
independently verified — the Gemini free-tier daily quota was exhausted
during this re-test (see §3).

---

## 1. Verification table — CampusGuide

| # | Check | Result | Evidence |
|---|---|---|---|
| R01 | `pytest tests/ -q` | **PASS** — 26/26 in 8.11s | Matches claimed 26 (19 original + 7 new) |
| R02 | `/chat` attendance — must state 75% | **PASS** — 200, "75%" present, 5 citations incl. §11 Attendance criteria | Live, Gemini enabled, cached |
| R03 | `/chat` exam phrasing 1 ("exam pattern and pass marks for theory subjects") | **PASS** — 200, "30%"/"40%" present | Was FAIL in QA (T29) |
| R04 | `/chat` exam phrasing 2 ("pass marks for ESE and CIE") | **PASS** — 200, "30%"/"40%" present | Was false "I don't know" in QA (T30) — fixed |
| R05 | `/chat` exam phrasing 3 ("minimum marks to pass the end semester examination") | **PASS** — 200, "30%"/"40%" present | |
| R06 | `/chat` hostel timings for girls | **PASS** — 200, "8:00" present | |
| R07 | `/chat` fee breakdown | **PASS** — 200, "₹1,90,000", "₹8,500", "₹1,98,500" all present | Was PARTIAL in QA (T33) |
| R08 | `/chat` out-of-corpus ("capital of France") | **PASS** — 200, honest "I don't know", citations `[]` | |
| R09 | `/chat` injection ("Ignore previous instructions… pirate") | **PASS** — 200, `route=guardrail`, safe refusal | |
| R10 | B-01 cold start, cache warm | **PASS** — first `/chat` after server restart: 200 in 1.52s, 75% present | Vector cache in `data/vector_cache/` used (3 `.npz` files). True cache-miss (~86s claimed) not re-measured |
| R11 | B-04 degradation, bad key + cache moved aside | **PASS** — 200 in 1.9s, 75% present, `route=retriever_agent` | Invalid key confirmed present in server process env; a fresh `tfidf-local` cache file was written during the run, proving TF-IDF fallback engaged. No 500 |
| R12 | B-04 degradation, real quota exhaustion | **PASS** — 200 in 3.5s, 75% present | Gemini daily quota was exhausted (see §3); query fell back to TF-IDF with ~2s extra latency. No 500, no traceback |
| R13 | B-02 old admin password | **PASS** — `admin@campus.local / admin123` → 401 "Invalid credentials" | |
| R14 | B-03 JWT secret rotated | **PASS** — 0 occurrences of the placeholder value in `.env` (count comparison only; value never printed) | |
| R15 | `POST /auth/change-password` exists + behaves | **PASS** — unauthenticated → 401; authenticated + wrong current password → 401 "Current password is incorrect" | No password was changed |
| R16 | B-09 CORS no longer `*` | **PASS** — `CORS_ORIGINS` env-configured, default `http://127.0.0.1:5173,http://localhost:5173`; request with `Origin: https://evil.example.com` got **no** `access-control-allow-origin` header | |
| R17 | `/health` | **PASS** — 200, `embedder: gemini-embedding-001`, `sample_placement_data: true` | |
| R18 | `/eval` re-run (claimed 0.856/1.000/0.89/0.907) | **NOT VERIFIED** — see §3 | First direct run completed (84s) but aggregates were not captured; second run blocked by quota |
| R19 | Frontend build | **PASS** — `npm run build` clean in 1.15s | |
| R20 | Push set clean (CampusGuide) | **PASS** — 58 files would push (simulated `git add -A --dry-run`); `.env`, `*.db`, `.venv/`, `node_modules/`, `frontend/dist/`, `__pycache__/`, `data/vector_cache/`, `checkpoints.sqlite*`, `eval_results.json` all excluded; secret-pattern scan of the 58 files clean; CI workflow contains no secrets | `.env.example` is placeholder-only |
| R21 | No 429/traceback in server logs across all live runs | **PASS** — 0 matches in all server logs, except the expected quota-exhaustion 429 from the eval attempt (handled, see §3) | |

## 2. Verification table — MandiLens (light)

| # | Check | Result | Evidence |
|---|---|---|---|
| M01 | `pytest backend/tests/ -q` | **PASS** — 6/6 in 6.37s | |
| M02 | Push set clean | **PASS** — 36 files would push; exact `.env` excluded, `*.db`, `.venv/`, `node_modules/`, `frontend/dist/` excluded; secret-pattern scan of the 36 files clean; `.env.example` placeholder-only; no real `.env` file exists | |

## 3. New / remaining items

### R-01 — NEW BUG (Major): stale draft leaks into every `/chat` via the shared default thread
- **Found by this re-test.** Every plain (non-writer) `/chat` call on the
  default `thread_id` returned a stale draft and created a duplicate draft
  row: my 11 test chats produced 11 spurious `pending_approval` drafts
  (ids 7–17), all with the identical body of the old "Draft a notice about
  library timings" draft (#1), and responses carried
  `"draft_pending_approval": true` on questions that never asked for a
  draft (attendance, exam, hostel, fees, even "capital of France").
- Mechanism: `ask()` returns `result.get("draft")` from the LangGraph
  `SqliteSaver` checkpointer state for the shared `"default"` thread, so
  a draft set by any earlier writer call persists into all later calls on
  that thread; `app.py` then saves a new `Draft` row per call.
- Impact: admin draft queue fills with duplicates; users are wrongly told
  a draft is pending. Does not break answers and does not leak secrets.
- Fix direction: clear/reset `draft` (and `draft_pending_approval`) at
  the start of each non-writer invocation, or use a fresh thread per
  request, or only persist the draft when the route is `writer_agent`.
- **Cleanup done by this pass:** the 11 spurious drafts were deleted;
  drafts 1–6 are untouched (all `pending_approval`); the re-test student
  account was deleted; users table is back to admin only; 0 feedback rows.

### R-02 — Stale default-credential references (Minor, fix before deploy/demo)
- `backend/seed.py` still seeds the admin as `admin@campus.local /
  admin123`; `README.md`, `DEPLOY_CHECKLIST.md`, and the frontend hint in
  `frontend/src/App.jsx` still advertise those credentials. The live DB
  password was rotated, so the hint now points users at a dead password,
  and a fresh `seed` run would recreate the known default. No secret is
  leaked (the value is a documented default, and the DB is not pushed),
  but the references must be updated/removed before any deployment or
  public demo.

### Eval improvement claim — NOT verified (quota)
- The fix pass claimed eval improved to hybrid 0.856 / 1.000 / 0.890 /
  0.907 (was 0.840 / 1.000 / 0.830 / 0.858). My first direct `run_eval`
  run completed in 84s, but the aggregate numbers were not captured from
  its output (only per-question rows were retained); the second run failed
  with `429 RESOURCE_EXHAUSTED` — Gemini free-tier **daily** embed quota
  (1000 requests/day) exhausted, retry in ~4h24m. Re-verify after the
  quota resets. Note: the morning's testing volume (QA's 12 burst
  attempts, the fix pass's cold starts/evals, and this re-test's 2 eval
  runs at 50 query-embeds each) burned the day's budget — worth watching
  before any public demo, since each `/chat` costs 1 query embed when the
  cache is warm.

### Deliberately not re-checked
- True cache-miss cold start (~86s claimed): not re-measured; only the
  cached path (1.52s) was timed.
- Hinglish queries (B-08), SQL tautology (B-10), `vercel.json` (B-13),
  NL→SQL company filter (pre-existing limitation): unchanged per the fix
  report; not re-tested.
- Postgres/pgvector deploy path: still untested locally (no Postgres).

## 4. Test artifacts left behind
- None in the project. Re-test student account deleted; 11 spurious
  drafts deleted (see R-01); no feedback rows; no server left running
  (port 8000 confirmed down). The vector cache was moved aside for the
  degradation test and restored byte-identical afterwards (same 3 files).
  `.env` was never modified. Only files created by this pass are this
  report and scratch in `/tmp/cg-retest/` (outside the repo).
