# postgres_tool

A read-only CrewAI tool suite for connecting to any PostgreSQL database, inspecting schemas, and executing SELECT queries. Works with any Postgres-compatible host: Neon, Supabase, RDS, Aurora, or self-hosted.

## Tools

| Class | CrewAI tool name | Description |
|---|---|---|
| `PostgresListDatabasesTool` | `postgres_list_databases` | List all databases on the server |
| `PostgresListSchemasTool` | `postgres_list_schemas` | List non-system schemas in the current database |
| `PostgresListTablesTool` | `postgres_list_tables` | List tables and views in a schema |
| `PostgresDescribeTableTool` | `postgres_describe_table` | Get column definitions for a table or view |
| `PostgresQueryTool` | `postgres_query` | Execute a read-only SELECT query |
| `PostgresTool` | `postgres_query` | Alias for `PostgresQueryTool` (used by CrewAI AMP) |

All tools are **read-only**. `PostgresQueryTool` enforces this at two layers: a keyword blocklist (applied after comment stripping) and a read-only transaction wrapper on every execution.

---

## Publishing

### Prerequisites

```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install the CrewAI CLI
uv tool install crewai
```

### Build

```bash
uv build
```

This produces `dist/postgres_tool-<version>.tar.gz` and `dist/postgres_tool-<version>-py3-none-any.whl`.

### Publish to PyPI

```bash
uv publish
```

You'll need a PyPI account and an API token. Set it once:

```bash
uv publish --token pypi-YOUR_TOKEN_HERE
# or store it permanently:
export UV_PUBLISH_TOKEN=pypi-YOUR_TOKEN_HERE
```

### Releasing a new version

1. Bump `version` in `pyproject.toml`
2. Run `uv lock` to update `uv.lock`
3. Commit and push
4. Run `uv build && uv publish`

---

## Installing into a CrewAI AMP Crew

AMP crews install tools as standard Python packages. There are three ways to reference this tool:

### Option 1 — From PyPI (after publishing)

In your crew's `pyproject.toml`:

```toml
[project]
dependencies = [
    "postgres_tool>=1.0.1",
]
```

### Option 2 — Directly from GitHub (before PyPI or for private repos)

```toml
[project]
dependencies = [
    "postgres_tool @ git+https://github.com/your-org/postgres_tool.git",
]
```

To pin a specific version or commit:

```toml
"postgres_tool @ git+https://github.com/your-org/postgres_tool.git@v1.0.1"
"postgres_tool @ git+https://github.com/your-org/postgres_tool.git@abc1234"
```

### Option 3 — Via the CrewAI CLI tool installer

```bash
crewai tool add postgres_tool          # from PyPI
crewai tool add postgres_tool --git https://github.com/your-org/postgres_tool.git
```

After adding the dependency, sync and lock:

```bash
uv sync
uv lock
```

Commit `uv.lock` — AMP requires it to reproduce the exact environment.

### AMP environment variables

Set these in the AMP dashboard under your crew's environment configuration:

```
DATABASE_URL=postgresql://user:password@host:5432/dbname?sslmode=require
```

Or individually:

```
PG_HOST=your-host
PG_DATABASE=your-database
PG_USER=your-user
PG_PASSWORD=your-password
```

### Importing in your crew

AMP generates crew code that imports `PostgresTool` (derived from the package name). This is an alias for `PostgresQueryTool`:

```python
from postgres_tool.tool import PostgresTool

# or import the full suite:
from postgres_tool import (
    PostgresListDatabasesTool,
    PostgresListSchemasTool,
    PostgresListTablesTool,
    PostgresDescribeTableTool,
    PostgresQueryTool,
)
```

---

## Local Installation

```bash
git clone https://github.com/your-org/postgres_tool.git
cd postgres_tool
uv pip install -e .
```

---

## Configuration

Set connection details via environment variables. Two modes are supported:

### Option 1 — Full DSN (recommended)

```bash
DATABASE_URL=postgresql://user:password@host:5432/dbname?sslmode=require
```

This is the standard connection string format used by Neon, Supabase, Railway, Heroku, and Render — paste your provider's connection string directly.

### Option 2 — Individual parameters

```bash
PG_HOST=your-host
PG_DATABASE=your-database
PG_USER=your-user
PG_PASSWORD=your-password
PG_PORT=5432          # optional, defaults to 5432
PG_SSLMODE=require    # optional, defaults to prefer
```

`DATABASE_URL` takes precedence if both are set. Copy `.env.example` to `.env` to get started:

```bash
cp .env.example .env
```

---

## Quick Start

```python
from postgres_tool import (
    PostgresListDatabasesTool,
    PostgresListSchemasTool,
    PostgresListTablesTool,
    PostgresDescribeTableTool,
    PostgresQueryTool,
)

tools = [
    PostgresListDatabasesTool(),
    PostgresListSchemasTool(),
    PostgresListTablesTool(),
    PostgresDescribeTableTool(),
    PostgresQueryTool(),
]

analyst = Agent(
    role="Database Analyst",
    goal="Answer business questions by querying the PostgreSQL database",
    backstory="Expert SQL analyst — always inspects schema before writing queries",
    tools=tools,
)
```

All five tools share a single connection pool via a module-level singleton — no duplicate connections.

---

## Single-File Agent Example

The following is a complete, self-contained CrewAI agent that explores and queries any connected database. See [`examples/database_analyst_agent.py`](examples/database_analyst_agent.py) for the full version.

```python
from crewai import Agent, Task, Crew, Process
from postgres_tool import (
    PostgresListDatabasesTool,
    PostgresListSchemasTool,
    PostgresListTablesTool,
    PostgresDescribeTableTool,
    PostgresQueryTool,
)

pg_tools = [
    PostgresListDatabasesTool(),
    PostgresListSchemasTool(),
    PostgresListTablesTool(),
    PostgresDescribeTableTool(),
    PostgresQueryTool(),
]

database_analyst = Agent(
    role="Senior Database Analyst",
    goal=(
        "Explore and query the connected PostgreSQL database to extract accurate, "
        "actionable insights. Always inspect the schema before writing SQL."
    ),
    backstory=(
        "You are a meticulous senior data analyst with 10+ years of experience. "
        "You never write SQL against a schema you haven't inspected first.\n\n"
        "Your workflow is non-negotiable:\n"
        "1. Call postgres_list_schemas to understand the database layout.\n"
        "2. Call postgres_list_tables for the relevant schema.\n"
        "3. Call postgres_describe_table for every table you plan to query.\n"
        "4. Write a precise SELECT using the exact column names you confirmed.\n"
        "5. Check the 'truncated' flag — if true, refine the query before reporting."
    ),
    tools=pg_tools,
    verbose=True,
    allow_delegation=False,
    respect_context_window=True,
)

task = Task(
    description=(
        "Find the top 5 tables by row count in the public schema "
        "and return a summary of what each table appears to contain."
    ),
    expected_output=(
        "A ranked list of the 5 largest tables with their row estimates "
        "and a brief description of each based on column names."
    ),
    agent=database_analyst,
)

crew = Crew(
    agents=[database_analyst],
    tasks=[task],
    process=Process.sequential,
    verbose=True,
)

result = crew.kickoff()
print(result.raw)
```

Run it:

```bash
DATABASE_URL=postgresql://user:pass@host/dbname python examples/database_analyst_agent.py
```

---

## Tool Reference

### `PostgresListDatabasesTool`

No input required. Returns a JSON array of database names.

```json
["analytics", "postgres", "staging"]
```

### `PostgresListSchemasTool`

No input required. Returns a JSON array of schema names (system schemas excluded).

```json
["public", "analytics", "raw"]
```

### `PostgresListTablesTool`

| Parameter | Type | Default | Description |
|---|---|---|---|
| `schema_name` | str | `"public"` | Schema to inspect |
| `include_views` | bool | `true` | Include views alongside tables |

Returns a JSON object with `schema` and `tables` array, each entry having `name`, `type`, and `row_estimate`.

```json
{
  "schema": "public",
  "tables": [
    {"name": "orders", "type": "table", "row_estimate": 142000},
    {"name": "order_summary", "type": "view", "row_estimate": null}
  ]
}
```

### `PostgresDescribeTableTool`

| Parameter | Type | Default | Description |
|---|---|---|---|
| `table_name` | str | required | Table or view to describe |
| `schema_name` | str | `"public"` | Schema containing the table |

Returns a JSON object with `schema`, `table`, and `columns` array. Each column has `name`, `type`, `nullable`, `primary_key`, and `default_value`.

```json
{
  "schema": "public",
  "table": "orders",
  "columns": [
    {"name": "id", "type": "integer", "nullable": false, "primary_key": true, "default_value": null},
    {"name": "customer_id", "type": "integer", "nullable": false, "primary_key": false, "default_value": null},
    {"name": "total", "type": "numeric", "nullable": true, "primary_key": false, "default_value": null},
    {"name": "created_at", "type": "timestamp without time zone", "nullable": false, "primary_key": false, "default_value": "now()"}
  ]
}
```

### `PostgresQueryTool` / `PostgresTool`

| Parameter | Type | Default | Description |
|---|---|---|---|
| `sql` | str | required | SELECT query to execute; CTEs (`WITH ... AS`) supported |
| `max_rows` | int | `500` | Row limit (1–1000); response includes a `truncated` flag |

Returns a JSON object with `row_count`, `truncated`, and `rows`.

```json
{
  "row_count": 3,
  "truncated": false,
  "rows": [
    {"id": 1, "name": "Widget A", "total": "49.99"},
    {"id": 2, "name": "Widget B", "total": "24.99"},
    {"id": 3, "name": "Widget C", "total": "9.99"}
  ]
}
```

If `truncated` is `true`, the query matched more rows than `max_rows`. Refine with `WHERE` or `LIMIT` clauses.

---

## Safety

`PostgresQueryTool` enforces read-only access at two independent layers:

1. **Keyword blocklist** — SQL comments are stripped first, then the statement is parsed. Any query that doesn't start with `SELECT` or `WITH` is rejected. Blocked keywords: `INSERT`, `UPDATE`, `DELETE`, `DROP`, `CREATE`, `ALTER`, `TRUNCATE`, `GRANT`, `REVOKE`, `EXEC`, `EXECUTE`, `CALL`, `MERGE`, `UPSERT`, `REPLACE`, `COPY`.

2. **Read-only transaction** — Every query runs inside `SET TRANSACTION READ ONLY`, so even if a keyword slipped through, the database itself would reject it.

---

## Connection Pooling Notes

- `pool_pre_ping=True` — tests connections before use, automatically reconnecting stale ones. Critical for serverless Postgres providers (Neon, Supabase) that close idle connections. Without this you get `SSL connection has been closed unexpectedly` errors.
- `pool_recycle=1800` — recycles connections after 30 minutes to stay under provider idle timeouts.
- `default=str` on JSON serialization — dates, decimals, and UUIDs serialize without errors.

---

## Custom Connection Manager

For testing or multi-database setups, inject a custom `PostgresConnectionManager`:

```python
from postgres_tool import PostgresConnectionManager, PostgresQueryTool

manager = PostgresConnectionManager()  # reads env vars on first query
tool = PostgresQueryTool(manager=manager)

# Tear down pool when done (useful in tests)
manager.dispose()
```

---

## Environment Variable Reference

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | If not using individual vars | Full SQLAlchemy DSN |
| `PG_HOST` | If not using `DATABASE_URL` | Hostname |
| `PG_PORT` | No | Port (default: `5432`) |
| `PG_DATABASE` | If not using `DATABASE_URL` | Database name |
| `PG_USER` | If not using `DATABASE_URL` | Username |
| `PG_PASSWORD` | If not using `DATABASE_URL` | Password |
| `PG_SSLMODE` | No | `disable`, `allow`, `prefer`, `require`, `verify-ca`, `verify-full` (default: `prefer`) |
