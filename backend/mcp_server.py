"""MCP server (FastMCP) exposing CampusGuide tools to MCP clients.

Tools:
- search_notices(query): hybrid search over the college documents
- placement_stats(question): natural-language placement query via the
  read-only SQL agent (same validation as the HTTP API)

Run:  python -m backend.mcp_server   (stdio transport)
"""
from fastmcp import FastMCP

from .db import SessionLocal, init_db
from .ingest import get_retriever
from .sql_agent import natural_language_to_sql, run_sql

mcp = FastMCP("campusguide")


@mcp.tool
def search_notices(query: str, top_k: int = 5) -> list:
    """Search official KIET documents (ordinances, fee structure, hostel
    rules, placement records, FAQ). Returns passages
    with document title, section and citation."""
    init_db()
    passages = get_retriever().search(query, top_k=top_k)
    return [{"doc_title": p["doc_title"], "section": p["section"],
             "text": p["text"][:500], "citation": p["citation"],
             "score": p["score"]} for p in passages]


@mcp.tool
def placement_stats(question: str) -> dict:
    """Answer a placement-statistics question from the sample
    placement_stats table (read-only, allow-listed SELECT only)."""
    init_db()
    sql = natural_language_to_sql(question)
    db = SessionLocal()
    try:
        cols, rows = run_sql(db, sql)
    finally:
        db.close()
    return {"sql": sql, "columns": cols, "rows": rows,
            "note": "Sample placement data — not real figures."}


if __name__ == "__main__":
    mcp.run()
