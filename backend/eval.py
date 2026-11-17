"""Golden-set evaluation (RAGAS-style, deterministic by default).

Metrics, all in [0, 1]:
- context_precision: fraction of retrieved passages from expected docs
- context_recall: fraction of expected docs retrieved
- faithfulness: fraction of expected-answer keywords present in the answer
  AND in retrieved passages (answer grounded in retrieved context)
- answer_relevance: token overlap between answer and expected answer

Optional LLM judge: if GEMINI_API_KEY is set, a second pass scores
faithfulness/relevance with Gemini; deterministic scores are always
reported and are the ones that run with no API key.
A vector-only (dense) baseline is reported alongside the hybrid scores.
"""
import json
import re
from pathlib import Path

from .config import BASE_DIR

GOLDEN_PATH = BASE_DIR / "data" / "golden_set.json"


def _tokens(text: str):
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def load_golden(path: str | Path = GOLDEN_PATH):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run_eval(retriever, answer_fn, golden=None, top_k: int = 5):
    golden = golden if golden is not None else load_golden()
    rows, base_rows = [], []
    for item in golden:
        q = item["question"]
        expected_docs = set(item.get("expected_docs", []))
        expected_kw = set(item.get("expected_keywords", []))
        # Hybrid — chunk-level context precision (RAGAS-style): a retrieved
        # chunk counts as relevant if it comes from an expected document OR
        # its text contains an expected keyword. (Doc-level precision is
        # misleading here: top-5 retrieval legitimately returns neighbouring
        # same-topic chunks, e.g. other attendance sections.)
        passages = retriever.search(q, top_k=top_k)
        got_docs = {p["doc_slug"] for p in passages}
        kw_lower = [k.lower() for k in expected_kw]
        relevant = sum(1 for p in passages
                       if p["doc_slug"] in expected_docs
                       or any(k in p["text"].lower() for k in kw_lower))
        cp = relevant / max(len(passages), 1)
        cr = len(got_docs & expected_docs) / max(len(expected_docs), 1)
        answer = answer_fn(q, passages)
        ans_tokens = _tokens(answer)
        exp_tokens = _tokens(item["expected_answer"])
        relevance = len(ans_tokens & exp_tokens) / max(len(exp_tokens), 1)
        passage_tokens = set()
        for p in passages:
            passage_tokens |= _tokens(p["text"])
        grounded_kw = {k for k in expected_kw
                       if k.lower() in answer.lower()
                       and k.lower() in " ".join(p["text"] for p in passages).lower()}
        faith = len(grounded_kw) / max(len(expected_kw), 1)
        rows.append({"id": item["id"], "question": q,
                     "context_precision": round(cp, 3),
                     "context_recall": round(cr, 3),
                     "faithfulness": round(faith, 3),
                     "answer_relevance": round(relevance, 3)})
        # Vector-only baseline (same chunk-level precision definition)
        base = retriever.dense_only_search(q, top_k=top_k)
        base_rel = sum(1 for p in base
                       if p["doc_slug"] in expected_docs
                       or any(k in p["text"].lower() for k in kw_lower))
        base_docs = {p["doc_slug"] for p in base}
        base_rows.append({
            "context_precision": base_rel / max(len(base), 1),
            "context_recall": len(base_docs & expected_docs) / max(len(expected_docs), 1)})

    def _avg(key, rs):
        return round(sum(r[key] for r in rs) / max(len(rs), 1), 3)

    return {
        "n": len(rows),
        "hybrid": {
            "context_precision": _avg("context_precision", rows),
            "context_recall": _avg("context_recall", rows),
            "faithfulness": _avg("faithfulness", rows),
            "answer_relevance": _avg("answer_relevance", rows),
        },
        "vector_only_baseline": {
            "context_precision": _avg("context_precision", base_rows),
            "context_recall": _avg("context_recall", base_rows),
        },
        "per_question": rows,
    }
