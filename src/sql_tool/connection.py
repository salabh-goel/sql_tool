"""PostgreSQL connection management and query execution."""

import os
from typing import Optional

try:
    from sqlalchemy import create_engine, text
    SQLALCHEMY_AVAILABLE = True
except ImportError:
    SQLALCHEMY_AVAILABLE = False


class ConfigurationError(Exception):
    pass


def resolve_dsn() -> str:
    """Build a SQLAlchemy DSN from environment variables.

    Priority:
      1. DATABASE_URL  (full DSN, used as-is)
      2. Individual PG_* variables

    Raises ConfigurationError if neither is fully configured.
    """
    dsn = os.environ.get("DATABASE_URL")
    if dsn:
        return dsn

    host = os.environ.get("PG_HOST")
    database = os.environ.get("PG_DATABASE")
    user = os.environ.get("PG_USER")
    password = os.environ.get("PG_PASSWORD")

    missing = [
        name for name, val in [
            ("PG_HOST", host),
            ("PG_DATABASE", database),
            ("PG_USER", user),
            ("PG_PASSWORD", password),
        ]
        if not val
    ]

    if missing:
        raise ConfigurationError(
            "PostgreSQL connection is not configured. Set either:\n"
            "  DATABASE_URL=postgresql://user:password@host:5432/dbname\n"
            "or all of:\n"
            "  PG_HOST, PG_DATABASE, PG_USER, PG_PASSWORD\n"
            f"Missing: {', '.join(missing)}"
        )

    port = os.environ.get("PG_PORT", "5432")
    sslmode = os.environ.get("PG_SSLMODE", "prefer")

    return f"postgresql://{user}:{password}@{host}:{port}/{database}?sslmode={sslmode}"


class PostgresConnectionManager:
    """Manages a shared SQLAlchemy engine with connection pooling.

    The engine is created lazily on first access. All tools share
    the same manager instance (module-level singleton by default),
    so they share the connection pool.
    """

    def __init__(self):
        self._engine = None

    @property
    def engine(self):
        if not SQLALCHEMY_AVAILABLE:
            raise ImportError(
                "sqlalchemy is not installed. Run: pip install sqlalchemy psycopg2-binary"
            )
        if self._engine is None:
            self._engine = create_engine(
                resolve_dsn(),
                pool_size=5,
                max_overflow=10,
                # Test connection before returning from pool.
                # Critical for serverless Postgres (Neon, Supabase) which
                # close idle connections — without this you get
                # "SSL connection has been closed unexpectedly" errors.
                pool_pre_ping=True,
                # Recycle connections after 30 min to stay under Neon's
                # default idle timeout on the wire.
                pool_recycle=1800,
                connect_args={"connect_timeout": 10},
            )
        return self._engine

    def dispose(self):
        """Close all pooled connections. Useful in tests."""
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None


def execute_query(
    manager: PostgresConnectionManager,
    sql: str,
    params: Optional[dict] = None,
) -> list[dict]:
    """Execute a SQL query and return all rows as a list of dicts."""
    with manager.engine.connect() as conn:
        result = conn.execute(text(sql), params or {})
        columns = list(result.keys())
        return [dict(zip(columns, row)) for row in result.fetchall()]


def execute_readonly_query(
    manager: PostgresConnectionManager,
    sql: str,
    max_rows: int,
) -> tuple[list[dict], bool]:
    """Execute a SELECT in a read-only transaction.

    Fetches max_rows + 1 to detect truncation without over-fetching.
    Returns (rows, truncated).
    """
    with manager.engine.connect() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        result = conn.execute(text(sql))
        columns = list(result.keys())
        raw_rows = result.fetchmany(max_rows + 1)

    truncated = len(raw_rows) > max_rows
    rows = [dict(zip(columns, row)) for row in raw_rows[:max_rows]]
    return rows, truncated


# Module-level singleton shared by all tools when no custom manager is injected.
default_manager = PostgresConnectionManager()
