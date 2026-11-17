# CampusGuide — Real KIET Documents Load Log

**Date:** 11 November 2026
**What changed:** the 10 sample documents in `data/documents/` were moved to `data/docs_sample_archive/` (not deleted) and replaced with 10 real official KIET documents fetched from kiet.edu / old.kiet.edu via browser text fetch. Ingest re-run: **10 documents, 107 chunks** (was 10 sample documents, 46 chunks). All documents have `is_sample = False`. The 12 sample placement-stats rows are UNCHANGED (no real placement-stats table is publicly available) — the SQL agent still answers from sample data, and the UI / `/health` say so.

## Documents loaded

| # | File (slug) | Source URL | Regime tag | Chunks |
|---|---|---|---|---|
| 1 | `autonomous-ordinance-2024-25.md` | https://www.old.kiet.edu/uploads/deanA/682580.pdf (full PDF text) | Autonomous Ordinance 2024-25 — autonomous batches only; does NOT govern the 2023–27 Affiliated Batch (AKTU rules) | 54 |
| 2 | `fee-structure-2026-27.md` | Official 2026-27 fee PDF (kiet.edu) + https://www.kiet.edu/admissions/fee-structure/ | Institute-wide — 2026-27 rates | 7 |
| 3 | `hostel-timings-rules.md` | https://www.old.kiet.edu/uploads/department/deansw/hostel/Hostel Timings and Entry-Out rules.pdf (full PDF text) + FAQ | Institute-wide | 6 |
| 4 | `placement-records-crpc.md` | https://www.kiet.edu/placements/placement-recs/, https://www.kiet.edu/placements/team-crpc/, https://www.kiet.edu/faq/ | Institute-wide — records only; no placement policy exists publicly | 7 |
| 5 | `faq-admissions-programmes.md` | https://www.kiet.edu/faq/ (full page) + https://www.kiet.edu/about/Overview/ | Institute-wide | 11 |
| 6 | `kiet-university-status.md` | https://www.kiet.edu/about/Overview/, https://www.kiet.edu/ranking-accreditations/ugc/, https://www.kiet.edu/ranking-accreditations/aicte/ | Institute-wide | 5 |
| 7 | `ordinances-hub.md` | https://www.kiet.edu/academics/ordinance/ (hub listing only) | University Ordinance — new deemed-university batches; does NOT govern the 2023–27 Affiliated Batch | 5 |
| 8 | `academic-calendar-2026-27.md` | https://www.kiet.edu/academics/academic-calendar/ (hub listing only) | Institute-wide — calendar listing | 4 |
| 9 | `student-manual-2025.md` | https://www.kiet.edu/student-welfare/student-handbook/ (hub listing only) | Institute-wide | 4 |
| 10 | `student-discipline-policy-2026-27.md` | https://www.kiet.edu/student-welfare/student-discipline-policy/ (hub listing only) | Institute-wide — current code of conduct, 2026-27 | 4 |

Every file header carries its source URL, fetch date (11 Nov 2026) and regime tag. The Autonomous Ordinance file also repeats a short regime note at the start of its key sections (§11, §13, §15, §16) so the tag travels with retrieved chunks. No Scribd copy and no invented content was loaded.

## Documents NOT loaded and why

- **University Ordinance (full text)** — the PDF opens only in the site's in-page modal viewer; no direct PDF URL is exposed and a targeted search found no kiet.edu-hosted copy. Only the hub listing was loaded (`ordinances-hub.md`). Needs a browser download or the PDF from the college.
- **Student Manual 2025 (full text)** — same modal-viewer wall; only the hub listing was loaded. Cover says AY 2024-25, pre-university branding.
- **Student Discipline Policy 2026-27 (full text)** — same modal-viewer wall; only the listing was loaded.
- **Academic Calendar 2026-27 (full contents/dates)** — same modal-viewer wall; only the three calendar titles were loaded. Exam windows and dates are NOT in the corpus.
- **Official placement policy (any batch)** — does not exist publicly on kiet.edu. The only copy found is an unverified Scribd copy of the 2026-batch policy — deliberately NOT loaded.
- **AKTU B.Tech ordinance (for the 2023–27 Affiliated Batch)** — not found publicly on aktu.ac.in. This is the biggest gap: the final-year batch is governed by AKTU rules, and those rules are NOT in the corpus. Until an AKTU ordinance is obtained, final-year questions cannot be answered from the governing document.
- **Circulars/notices** — the official circulars page renders empty; nothing to load.
- **Re-evaluation procedure** — none found; the Autonomous Ordinance offers only §14 paper showing + grievance handling.

## Verification (11 Nov 2026)

- **pytest: 19 passed** (unchanged).
- **Eval (golden set, still written against the sample corpus — NOT edited):** hybrid context_precision 0.428, context_recall 0.0, faithfulness 0.292, answer_relevance 0.54; vector-only baseline precision 0.392. Previous (sample corpus): 0.588 / 1.000 / 0.982 / 0.968. Context recall is 0.0 because all 50 questions expect sample-doc slugs (e.g. `attendance-rules`) that no longer exist — 0/50 questions can match an expected doc. Faithfulness fell largely because several expected answers encode sample-doc specifics that the real documents contradict (e.g. q03 expected "condonation up to 10%, 65%–75%"; the real ordinance says up to 15% relaxation with a 60% floor). The golden set needs rebuilding against the real corpus before these numbers mean anything again.
- **Live backend checks (port 8000, TF-IDF embedder):**
  - (a) Attendance for a final-year student ("What is the minimum attendance required for a final-year B.Tech student to appear in the end semester exam?") — **WEAK/FAIL**: answer did not contain the 75% figure and did not mention the Affiliated Batch / AKTU regime. §11 was not in the top-5 retrieved chunks for that phrasing. Rephrased as the golden-set question ("What is the minimum attendance required in every subject?"), §11 IS retrieved and cited and the answer contains 75% (MSE1 70%, MSE2/ESE 75% course-wise, 60% floor). Root cause: top-5 retrieval on a 107-chunk corpus plus the ESE-vs-"end semester exam" lexical gap; the regime warning also did not surface for the final-year phrasing.
  - (b) Exam pattern / pass marks — **PASS**: answer states ESE minimum 30% and overall (ESE+CIE) minimum 40% for B.Tech theory, cites §15, and the regime note ("autonomous batches only; not the 2023–27 Affiliated Batch") appears in the answer.
  - (c) Hostel entry timings — **PASS**: girls 8:00 PM (emergency to 9:00 PM with permission), boys 7:00 PM / 10:00 PM by hostel, cited to the hostel rules document.
  - (d) B.Tech CSE (AI & ML) fee structure — **PARTIAL**: natural phrasing returned only "tuition fee of Rs. 1.90 lakh per year" from the FAQ; a sharper phrasing ("tuition fee exam fee total per annum") returned the full breakdown — tuition Rs. 1,90,000, exam fee Rs. 8,500, total Rs. 1,98,500 per annum — cited to the fee-structure document.

## Labels updated with the swap

- `backend/app.py`: FastAPI description and `/health` now report `sample_data: false` ("Corpus: official KIET documents fetched 11 Nov 2026. Placement stats table is still sample data.").
- `backend/guardrails.py`: out-of-corpus reply now names the official KIET documents instead of the sample handbook.
- `backend/mcp_server.py`: `search_notices` tool description updated (placement tool still correctly says sample).
- `frontend/src/App.jsx`: banners now say "Real KIET documents" and the documents heading reads "Documents (official KIET)". The placement-stats heading still says "(sample)". Note: `frontend/dist/` is stale until `npm run build` is re-run.
- `README.md`: banner and real-vs-sample table updated to the 11 Nov 2026 load.

## Still to do (not done here)

1. Rebuild the 50-question golden set against the real corpus (expected docs/answers must match real documents and real rules) and re-run eval.
2. Obtain the AKTU B.Tech ordinance for the 2023–27 Affiliated Batch (from the college/CRPC/AKTU) — without it, final-year questions have no governing document in the corpus.
3. Obtain the University Ordinance, Student Manual 2025, Discipline Policy 2026-27 and Academic Calendar PDFs (modal-viewer wall — needs a browser download) and replace the four index entries with full text.
4. Obtain the official placement policy for the 2027 batch from CRPC.
5. Replace the 12 sample placement-stats rows with real figures (or remove the SQL agent's sample table) — currently the SQL route still answers from fictional companies.
6. Consider retrieval follow-ups: the top-5 is easily flooded by the 54-chunk ordinance (per-document caps, larger TOP_K, or a regime-aware rerank) and the extractive answer builder leads with noisy sentences.
7. Rebuild the frontend (`npm run build`) so the new banner ships; change the default admin password and JWT secret before any deployment (pre-existing TODO, not done here).

## Update — 11 Nov 2026 (evening): golden set rebuilt, retrieval fixed, eval re-run

**Retrieval fix (one focused change, `backend/retrieval.py`):** query expansion — spelled-out exam terms are expanded to their acronyms before scoring (`end semester exam`/`end semester` → `ese`, `mid semester` → `mse`, `continuous internal evaluation` → `cie`), applied in both `search()` and `dense_only_search()`. Four variants were measured offline before choosing (per-document cap, section-title boost, stemming, chunk-recall overlap — none of them moved the §11 figure chunk into the top-5; expansion did, with zero change to the three control queries: exam pattern, hostel, fees). Measured effect on the failing phrasing ("minimum attendance required for a final-year B.Tech student to appear in the end semester exam"): the §11 chunk carrying the 75% figure moved from rank 38 to rank 4 (inside top-5); the §11 regime-note chunk is at rank 41. Known remaining weakness, NOT fixed (one-change scope): the extractive answer builder quotes only the top 3 passages, so the 75% figure still does not appear in the answer text for that phrasing — the §11 citation is listed in Sources, but the figure is not quoted. The follow-up fix is to have the answer builder use the top-5 passages, or to merge §11's two chunks at ingest.

**Golden set rebuilt:** `data/golden_set.json` is now 50 questions grounded in the real loaded documents (6 attendance, 8 exam/evaluation, 6 grading/promotion, 5 results/vacation/summer, 8 other ordinance, 4 university status, 5 fees, 4 hostel, 3 placement records, 1 regime question — q50: AKTU governs the 2023–27 Affiliated Batch). The old sample-based set is kept at `data/golden_set_sample_based_backup.json`. No question expects a sample-doc slug; every expected answer/keyword was checked against the loaded document text.

**Eval, re-run 11 Nov 2026 (TF-IDF, real corpus, new golden set):** hybrid context_precision 0.840, context_recall 1.000, faithfulness 0.830, answer_relevance 0.858; vector-only baseline precision 0.836, recall 1.000. Previous numbers (0.428 / 0.0 / 0.292 / 0.54) were from the stale sample-based set and are not comparable. Per-question lows: q30 (duplicate marksheet, faithfulness 0.0 — "4-5 days" not in the quoted top-3), q01 (final-year attendance, faithfulness 0.333 — the 75% chunk ranks 4th, outside the quoted top-3), q03/q26/q38/q42 (faithfulness 0.333–0.5, same top-3 cutoff pattern). 11 of 50 questions score perfectly on all four metrics. Recall is 1.000 on every question — the expected document is always retrieved.

**pytest: 19 passed** (unchanged).

**Live backend re-verification (port 8000, TF-IDF, 11 Nov 2026 evening):**
- (a) Attendance for a final-year student — **IMPROVED BUT STILL WEAK**: §11 "Attendance criteria" is now cited in Sources (it was not cited before), but the three quoted snippets are §19/§12/§22 — the answer text still does not state 75% and does not mention the Affiliated Batch / AKTU regime. Root cause is now precisely the answer builder's top-3 cutoff, not retrieval.
- (b) Exam pattern / pass marks — **PASS**: ESE minimum 30%, overall 40%, cites §15, regime note appears in the answer text.
- (c) Hostel entry timings — **PASS**: girls 8:00 PM (emergency 9:00 PM with permission), cited to the hostel rules document.
- (d) B.Tech CSE (AI & ML) fees — **PARTIAL**: answer gives "Rs. 1.90 lakh per year" (FAQ) and the M.Tech/MCA figures, but the B.Tech line (tuition Rs. 1,90,000, total Rs. 1,98,500) is not among the three quoted snippets — same top-3 cutoff pattern.

**README.md** eval table updated to the new numbers, with the retrieval fix and the remaining weakness documented.
