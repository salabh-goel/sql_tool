# PostgreSQL Explorer Tool — Specification

## Overview

A read-only CrewAI tool suite for connecting to any PostgreSQL database, inspecting schemas, and executing SELECT queries. Built on SQLAlchemy with environment-variable-driven configuration.

Inspired by `crewai_tools.NL2SQLTool` but with: connection pooling, SELECT enforcement, individual tools per action, and flexible connection config.

---

## Design Decisions

### Why multiple tools instead of one?

The NL2SQL tool does everything in a single `_run`. This forces the agent to always carry full schema context. Splitting into discrete tools lets agents:
- Fetch only the schema info they need
- Minimize context window usage
- Have clearer, auditable action logs

### NL2SQL gaps we're fixing

| NL2SQL behavior | Our behavior |
|---|---|
| New DB engine per query | Shared engine with connection pool |
| No SELECT enforcement | Block anything that isn't a SELECT |
| Schema loaded eagerly at init | Schema fetched on demand (lazy) |
| Single monolithic tool | Five focused tools |
| No row limit | Configurable `max_rows` (default 500) |
| No SSL config | `sslmode` supported via env var |

---

## Connection Configuration

Two modes, checked in priority order:

### Mode 1 — Full DSN (takes precedence if set)

```bash
DATABASE_URL=postgresql://user:password@host:5432/dbname?sslmode=require
```

Any SQLAlchemy-compatible Postgres DSN works. The env var name `DATABASE_URL` is the standard used by Heroku, Railway, Neon, Supabase, Render, etc., so this should be the first thing most users try.

### Mode 2 — Individual parameters

```bash
PG_HOST=ep-noisy-pine-a4ghnpre.us-east-1.aws.neon.tech
PG_PORT=5432                   # optional, defaults to 5432
PG_DATABASE=neondb
PG_USER=neondb_owner
PG_PASSWORD=your_password
PG_SSLMODE=require             # optional, defaults to prefer
```

### Config resolution logic

```
if DATABASE_URL is set → use it directly
elif PG_HOST + PG_DATABASE + PG_USER + PG_PASSWORD are all set → build DSN
else → raise ConfigurationError with clear message listing what's missing
```

The tool reads config at instantiation time (not at import time), so environment variables set after import are picked up correctly.

---

## Tool Suite

### 1. `postgres_list_databases`

Lists all non-template databases on the connected PostgreSQL server. The starting point when you don't know what databases exist.

**Input:** none
**Returns:** JSON array of database name strings

```json
["neondb", "postgres"]
```

---

### 2. `postgres_list_schemas`

Lists all non-system schemas in the database.

**Input:** none
**Returns:** JSON array of schema names
**Excludes:** `information_schema`, `pg_catalog`, `pg_toast`, `pg_temp_*`

```json
["public", "analytics", "raw"]
```

---

### 3. `postgres_list_tables`

Lists tables (and views) in a given schema.

**Input:**
- `schema_name: str` — schema to inspect (default: `"public"`)
- `include_views: bool` — include views in results (default: `true`)

**Returns:** JSON object with schema name and tables array

```json
{
  "schema": "public",
  "tables": [
    {"name": "orders", "type": "table", "row_estimate": 14200},
    {"name": "order_summary", "type": "view", "row_estimate": null}
  ]
}
```

---

### 4. `postgres_describe_table`

Returns column definitions for a specific table or view.

**Input:**
- `table_name: str` — table or view name
- `schema_name: str` — schema containing the table (default: `"public"`)

**Returns:** JSON object with table metadata and column list

```json
{
  "schema": "public",
  "table": "orders",
  "columns": [
    {"name": "id", "type": "integer", "nullable": false, "primary_key": true},
    {"name": "customer_id", "type": "integer", "nullable": false, "primary_key": false},
    {"name": "total", "type": "numeric", "nullable": true, "primary_key": false}
  ]
}
```

---

### 5. `postgres_query`

Executes a read-only SQL SELECT query and returns results.

**Input:**
- `sql: str` — the SELECT query to run
- `max_rows: int` — result limit, 1–1000 (default: `500`)

**Returns:** JSON object with row count and data

```json
{
  "row_count": 3,
  "truncated": false,
  "rows": [
    {"id": 1, "name": "Widget A", "total": 49.99},
    {"id": 2, "name": "Widget B", "total": 24.99},
    {"id": 3, "name": "Widget C", "total": 9.99}
  ]
}
```

**Safety enforcement:**
- Strip SQL comments (`--` and `/* */`) before parsing
- Reject any statement that is not a `SELECT` (case-insensitive, after stripping)
- Specifically block: `INSERT`, `UPDATE`, `DELETE`, `DROP`, `CREATE`, `ALTER`, `TRUNCATE`, `GRANT`, `REVOKE`, `EXEC`, `EXECUTE`, `CALL`, `MERGE`, `UPSERT`, `REPLACE`, `COPY`
- Wrap execution in a read-only transaction (`SET TRANSACTION READ ONLY`)
- Fetch `max_rows + 1` to detect truncation without over-fetching

---

## Shared Infrastructure

### Connection Manager (internal, not a tool)

A `PostgresConnectionManager` class manages the SQLAlchemy engine:

```python
class PostgresConnectionManager:
    def __init__(self):
        self._engine = None  # lazy init

    @property
    def engine(self):
        if self._engine is None:
            self._engine = create_engine(
                _resolve_dsn(),
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True,     # detect stale connections
                pool_recycle=1800,      # recycle after 30 min (Neon idle timeout)
                connect_args={"connect_timeout": 10},
            )
        return self._engine
```

All five tools hold a reference to a shared `PostgresConnectionManager` instance. Tools instantiated without arguments share a module-level singleton; you can also inject a custom one (useful for testing).

### `pool_pre_ping=True` — why this matters for serverless Postgres

Neon, Supabase, and similar serverless providers close idle connections. `pool_pre_ping` causes SQLAlchemy to test the connection before using it from the pool, automatically reconnecting if it's gone cold. Without this, agents fail with `SSL connection has been closed unexpectedly` after a few seconds of inactivity.

---

## File Layout

```
src/postgres_tool/
├── __init__.py          # exports all five tool classes
├── tool.py              # all five BaseTool subclasses (self-contained)
├── connection.py        # re-exports from tool.py for direct imports
└── _safety.py           # re-exports from tool.py for direct imports
```

`tool.py` is intentionally self-contained so it can be dropped into any crew's `tools/` directory without sibling modules.

---

## Dependencies

```toml
dependencies = [
    "crewai[tools]>=1.13.0",
    "sqlalchemy>=2.0",
    "psycopg2-binary>=2.9",
]
```

`psycopg2-binary` is the most portable PostgreSQL driver for SQLAlchemy and works with Neon, RDS, Aurora, and self-hosted Postgres out of the box.

---

## Environment Variable Summary

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | If not using individual vars | Full SQLAlchemy DSN |
| `PG_HOST` | If not using `DATABASE_URL` | Hostname |
| `PG_PORT` | No | Port (default: `5432`) |
| `PG_DATABASE` | If not using `DATABASE_URL` | Database name |
| `PG_USER` | If not using `DATABASE_URL` | Username |
| `PG_PASSWORD` | If not using `DATABASE_URL` | Password |
| `PG_SSLMODE` | No | `disable`, `allow`, `prefer`, `require`, `verify-ca`, `verify-full` (default: `prefer`) |

---

## Best Practices Checklist

- [x] SELECT-only enforcement with comment stripping
- [x] Read-only transaction wrapper (defense in depth)
- [x] Connection pooling with `pool_pre_ping` for serverless Postgres
- [x] Row limits to prevent runaway queries
- [x] Lazy connection (no DB call at import time)
- [x] Actionable error messages (tell agent exactly what's wrong)
- [x] Schema introspection excludes system schemas
- [x] `pool_recycle` for Neon/Supabase idle connection timeouts
- [ ] Schema allowlist/denylist (future: `PG_ALLOWED_SCHEMAS`, `PG_DENIED_SCHEMAS`)
- [ ] Query timeout (`statement_timeout`) via connection arg (future)
- [ ] Async support via `asyncpg` (future)
