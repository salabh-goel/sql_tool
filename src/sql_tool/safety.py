"""SELECT-only query safety enforcement."""

import re

BLOCKED_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER",
    "TRUNCATE", "GRANT", "REVOKE", "EXEC", "EXECUTE", "CALL",
    "MERGE", "UPSERT", "REPLACE", "COPY",
}

_LINE_COMMENT_RE = re.compile(r"--[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


def strip_comments(sql: str) -> str:
    sql = _LINE_COMMENT_RE.sub("", sql)
    sql = _BLOCK_COMMENT_RE.sub("", sql)
    return sql.strip()


def validate_select_only(sql: str) -> None:
    """Raise ValueError if sql is not a plain SELECT statement."""
    clean = strip_comments(sql)

    if not clean:
        raise ValueError("SQL query is empty.")

    tokens = re.split(r"[\s;,()\[\]]+", clean.upper())
    tokens = [t for t in tokens if t]

    if not tokens:
        raise ValueError("SQL query is empty after stripping comments.")

    first = tokens[0]
    if first not in ("SELECT", "WITH"):
        raise ValueError(
            f"Only SELECT queries are allowed. "
            f"Got '{first}' as the first keyword. "
            f"If this is a CTE, start with WITH ... AS (...) SELECT ..."
        )

    blocked_found = BLOCKED_KEYWORDS.intersection(tokens)
    if blocked_found:
        raise ValueError(
            f"Query contains disallowed keyword(s): {', '.join(sorted(blocked_found))}. "
            f"Only read-only SELECT queries are permitted."
        )
