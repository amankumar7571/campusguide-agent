"""SQL agent: read-only, allow-listed queries over placement_stats.

Anything that is not a single SELECT over the allow-listed table/columns
is rejected with a safe error — including DROP/DELETE/INSERT/UPDATE,
multi-statement input, comments, and injection strings. Validation is
done BEFORE the query ever reaches the database.
"""
import re
from sqlalchemy import text as sql_text

ALLOWED_TABLES = {"placement_stats"}
ALLOWED_COLUMNS = {
    "placement_stats": {
        "id", "company", "year", "role", "offers", "ctc_lpa", "is_sample",
    }
}
FORBIDDEN = {
    "insert", "update", "delete", "drop", "alter", "create", "truncate",
    "replace", "merge", "grant", "revoke", "pragma", "attach", "detach",
    "vacuum", "call", "exec", "execute", "union", "into", "outfile",
    "dumpfile", "load_file", "benchmark", "sleep", "pg_sleep",
}
AGGREGATES = {"count", "sum", "avg", "min", "max"}


class SQLValidationError(ValueError):
    pass


def validate_sql(query: str) -> str:
    q = (query or "").strip()
    if not q:
        raise SQLValidationError("Empty query.")
    if q.count(";") > 1 or (q.count(";") == 1 and not q.rstrip().endswith(";")):
        raise SQLValidationError("Only a single statement is allowed.")
    q = q.rstrip(";").strip()
    if "--" in q or "/*" in q or "*/" in q:
        raise SQLValidationError("SQL comments are not allowed.")
    tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", q.lower())
    if not tokens or tokens[0] != "select":
        raise SQLValidationError("Only SELECT queries are allowed.")
    bad = sorted(set(tokens) & FORBIDDEN)
    if bad:
        raise SQLValidationError(
            f"Forbidden keyword(s) in query: {', '.join(bad)}")
    m = re.search(r"\bfrom\s+([A-Za-z_][A-Za-z0-9_]*)", q, re.I)
    if not m or m.group(1).lower() not in ALLOWED_TABLES:
        raise SQLValidationError(
            "Only the placement_stats table may be queried.")
    table = m.group(1).lower()
    # Column check on the SELECT list (allow * and known aggregates).
    select_list = q[:m.start()].strip()
    select_list = re.sub(r"^select\s+", "", select_list, flags=re.I)
    select_list = re.sub(r"\bAS\s+[A-Za-z_][A-Za-z0-9_]*", "", select_list,
                         flags=re.I)  # drop column aliases
    if select_list.strip() != "*":
        cols = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", select_list)
        unknown = [c for c in cols
                   if c.lower() not in ALLOWED_COLUMNS[table]
                   and c.lower() not in AGGREGATES
                   and c.lower() not in {"as", "distinct"}]
        if unknown:
            raise SQLValidationError(
                f"Unknown column(s): {', '.join(sorted(set(unknown)))}")
    return q


def run_sql(session, query: str):
    """Validate then execute. Returns (columns, rows-as-dicts)."""
    clean = validate_sql(query)
    result = session.execute(sql_text(clean))
    cols = list(result.keys())
    rows = [dict(r._mapping) for r in result.fetchall()]
    return cols, rows


def natural_language_to_sql(question: str) -> str:
    """Tiny deterministic NL->SQL for placement questions (no LLM needed).

    Examples: "how many offers did <company> make", "highest CTC",
    "offers in 2025", "list companies". Falls back to a safe aggregate.
    """
    q = question.lower()
    year_m = re.search(r"\b(20\d{2})\b", q)
    year_clause = f" WHERE year = {year_m.group(1)}" if year_m else ""
    company_m = re.search(r"(?:company|from|at|by)\s+([a-z][a-z0-9 &.'-]{2,40})", q)
    if "highest ctc" in q or "top ctc" in q or "max ctc" in q:
        return ("SELECT company, role, ctc_lpa, offers FROM placement_stats"
                f"{year_clause} ORDER BY ctc_lpa DESC LIMIT 5")
    if "total offers" in q or "how many offers" in q or "offers in total" in q:
        return f"SELECT SUM(offers) AS total_offers FROM placement_stats{year_clause}"
    if "average ctc" in q or "avg ctc" in q:
        return f"SELECT AVG(ctc_lpa) AS avg_ctc FROM placement_stats{year_clause}"
    if company_m:
        name = company_m.group(1).strip().strip("'\"")
        safe = re.sub(r"[^a-z0-9 &.'-]", "", name)
        return (f"SELECT company, year, role, offers, ctc_lpa "
                f"FROM placement_stats WHERE LOWER(company) LIKE '%{safe}%'")
    if "list" in q or "companies" in q or "which companies" in q:
        return ("SELECT company, year, role, offers, ctc_lpa "
                f"FROM placement_stats{year_clause} ORDER BY offers DESC LIMIT 20")
    return ("SELECT company, year, role, offers, ctc_lpa "
            f"FROM placement_stats{year_clause} ORDER BY offers DESC LIMIT 10")
