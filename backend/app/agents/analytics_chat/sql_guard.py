"""Validation for LLM-generated SQL before tenant databases see it."""

from __future__ import annotations

import re

try:
    import sqlparse
except ImportError:  # pragma: no cover - only used if dependency is missing.
    sqlparse = None


FORBIDDEN_KEYWORDS = {
    "ALTER",
    "CALL",
    "COMMIT",
    "COPY",
    "CREATE",
    "DELETE",
    "DO",
    "DROP",
    "EXECUTE",
    "GRANT",
    "INSERT",
    "LOCK",
    "MERGE",
    "REPLACE",
    "REVOKE",
    "ROLLBACK",
    "SET",
    "TRUNCATE",
    "UPDATE",
    "VACUUM",
}


def validate_query(query: str) -> tuple[bool, str]:
    """Return whether a query is safe enough to run against a tenant DB."""
    sql = (query or "").strip()
    if not sql:
        return False, "Query is empty."

    if _contains_forbidden_keyword(sql):
        blocked = _first_forbidden_keyword(sql)
        return False, f"Blocked unsafe SQL keyword: {blocked}."

    if sqlparse is None:
        return _validate_without_sqlparse(sql)

    statements = [stmt for stmt in sqlparse.parse(sql) if str(stmt).strip()]
    if len(statements) != 1:
        return False, "Only one SQL statement is allowed."

    statement_type = statements[0].get_type().upper()
    if statement_type != "SELECT":
        return False, f"Only SELECT queries are allowed. Got: {statement_type}."

    return True, ""


def _validate_without_sqlparse(sql: str) -> tuple[bool, str]:
    upper = sql.lstrip().upper()
    if not (upper.startswith("SELECT ") or upper.startswith("WITH ")):
        return False, "Only SELECT queries are allowed."
    if ";" in sql.rstrip(";"):
        return False, "Only one SQL statement is allowed."
    return True, ""


def _contains_forbidden_keyword(sql: str) -> bool:
    return _first_forbidden_keyword(sql) is not None


def _first_forbidden_keyword(sql: str) -> str | None:
    upper = sql.upper()
    for keyword in sorted(FORBIDDEN_KEYWORDS):
        if re.search(rf"\b{keyword}\b", upper):
            return keyword
    return None
