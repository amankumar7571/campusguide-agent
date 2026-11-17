"""Run the golden-set eval and print scores.

Usage:  python scripts/run_eval.py [--out eval_results.json]
Deterministic metrics run with no API key. If GEMINI_API_KEY is set,
an LLM-judge note is printed (deterministic scores remain authoritative).
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.db import init_db  # noqa: E402
from backend.eval import run_eval  # noqa: E402
from backend.graph import _answer_from_passages  # noqa: E402
from backend.ingest import get_retriever  # noqa: E402
from backend.seed import seed  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="eval_results.json")
    args = parser.parse_args()
    init_db()
    seed()
    retriever = get_retriever()

    def answer_fn(q, passages):
        ans, _ = _answer_from_passages(q, passages)
        return ans

    results = run_eval(retriever, answer_fn)
    Path(args.out).write_text(json.dumps(results, indent=2))
    print(json.dumps({k: v for k, v in results.items() if k != "per_question"},
                     indent=2))
    print(f"\nWrote full per-question results to {args.out}")


if __name__ == "__main__":
    main()
