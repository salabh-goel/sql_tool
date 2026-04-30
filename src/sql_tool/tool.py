"""PostgreSQL Explorer Tool suite.

Five read-only tools for inspecting and querying any PostgreSQL database:

  PostgresListDatabasesTool — list databases on the server
  PostgresListSchemasTool   — list non-system schemas
  PostgresListTablesTool    — list tables/views in a schema
  PostgresDescribeTableTool — column definitions for a table or view
  PostgresQueryTool         — execute SELECT queries
"""

import json
from typing import Optional, Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from .connection import (
    PostgresConnectionManager,
    default_manager,
    execute_query,
    execute_readonly_query,
)
from .safety import validate_select_only

_SYSTEM_SCHEMAS = {"information_schema", "pg_catalog", "pg_toast"}


def _is_system_schema(name: str) -> bool:
    return name in _SYSTEM_SCHEMAS or name.startswith("pg_")


# ---------------------------------------------------------------------------
# Tool 1: List Databases
# ---------------------------------------------------------------------------

class PostgresListDatabasesTool(BaseTool):
    name: str = "postgres_list_databases"
    description: str = """
    List all databases available on the connected PostgreSQL server.

    Use this as the starting point when you don't know what databases exist.
    Template databases (used internally by PostgreSQL) are excluded.

    Returns: JSON array of database name strings.
    """

    _manager: PostgresConnectionManager = None

    def __init__(self, manager: Optional[PostgresConnectionManager] = None, **kwargs):
        super().__init__(**kwargs)
        object.__setattr__(self, "_manager", manager or default_manager)

    def _run(self) -> str:
        try:
            rows = execute_query(
                self._manager,
                "SELECT datname FROM pg_database WHERE datistemplate = false ORDER BY datname;",
            )
            return json.dumps([r["datname"] for r in rows])
        except Exception as e:
            return f"Error listing databases: {e}"


# ---------------------------------------------------------------------------
# Tool 2: List Schemas
# ---------------------------------------------------------------------------

class PostgresListSchemasTool(BaseTool):
    name: str = "postgres_list_schemas"
    description: str = """
    List all user-created schemas in the connected PostgreSQL database.

    Use this first to understand the high-level structure of the database
    before drilling into tables. System schemas (pg_catalog, information_schema)
    are excluded.

    Returns: JSON array of schema name strings.
    """

    _manager: PostgresConnectionManager = None

    def __init__(self, manager: Optional[PostgresConnectionManager] = None, **kwargs):
        super().__init__(**kwargs)
        object.__setattr__(self, "_manager", manager or default_manager)

    def _run(self) -> str:
        try:
            rows = execute_query(
                self._manager,
                "SELECT schema_name FROM information_schema.schemata ORDER BY schema_name;",
            )
            schemas = [r["schema_name"] for r in rows if not _is_system_schema(r["schema_name"])]
            return json.dumps(schemas)
        except Exception as e:
            return f"Error listing schemas: {e}"


# ---------------------------------------------------------------------------
# Tool 3: List Tables
# ---------------------------------------------------------------------------

class ListTablesInput(BaseModel):
    schema_name: str = Field(
        default="public",
        description="Schema to list tables from (default: 'public'). "
                    "Use postgres_list_schemas to find available schemas.",
    )
    include_views: bool = Field(
        default=True,
        description="Include views alongside tables (default: true).",
    )


class PostgresListTablesTool(BaseTool):
    name: str = "postgres_list_tables"
    description: str = """
    List tables (and optionally views) in a PostgreSQL schema.

    Use postgres_list_schemas first if you don't know which schema to use.
    Returns each object's name, type (table or view), and an approximate
    row count for tables (views show null).

    Returns: JSON object with schema name and tables array.
    """
    args_schema: Type[BaseModel] = ListTablesInput

    _manager: PostgresConnectionManager = None

    def __init__(self, manager: Optional[PostgresConnectionManager] = None, **kwargs):
        super().__init__(**kwargs)
        object.__setattr__(self, "_manager", manager or default_manager)

    def _run(self, schema_name: str = "public", include_views: bool = True) -> str:
        try:
            table_types = "('BASE TABLE', 'VIEW')" if include_views else "('BASE TABLE')"
            rows = execute_query(
                self._manager,
                f"""
                SELECT
                    t.table_name AS name,
                    CASE t.table_type
                        WHEN 'BASE TABLE' THEN 'table'
                        WHEN 'VIEW'       THEN 'view'
                        ELSE lower(t.table_type)
                    END AS type,
                    s.n_live_tup AS row_estimate
                FROM information_schema.tables t
                LEFT JOIN pg_stat_user_tables s
                       ON s.schemaname = t.table_schema
                      AND s.relname    = t.table_name
                WHERE t.table_schema = :schema
                  AND t.table_type IN {table_types}
                ORDER BY t.table_name;
                """,
                {"schema": schema_name},
            )
            if not rows:
                return json.dumps({
                    "schema": schema_name,
                    "tables": [],
                    "message": f"No tables found in schema '{schema_name}'. "
                               "Check the schema name with postgres_list_schemas.",
                })
            return json.dumps({"schema": schema_name, "tables": rows})
        except Exception as e:
            return f"Error listing tables in schema '{schema_name}': {e}"


# ---------------------------------------------------------------------------
# Tool 4: Describe Table
# ---------------------------------------------------------------------------

class DescribeTableInput(BaseModel):
    table_name: str = Field(
        ...,
        description="Name of the table or view to describe.",
    )
    schema_name: str = Field(
        default="public",
        description="Schema containing the table (default: 'public').",
    )


class PostgresDescribeTableTool(BaseTool):
    name: str = "postgres_describe_table"
    description: str = """
    Get column definitions for a PostgreSQL table or view.

    Returns each column's name, data type, nullability, and whether it
    is part of the primary key. Use this before writing a SELECT query
    to understand the available fields and their types.

    Returns: JSON object with schema, table name, and columns array.
    """
    args_schema: Type[BaseModel] = DescribeTableInput

    _manager: PostgresConnectionManager = None

    def __init__(self, manager: Optional[PostgresConnectionManager] = None, **kwargs):
        super().__init__(**kwargs)
        object.__setattr__(self, "_manager", manager or default_manager)

    def _run(self, table_name: str, schema_name: str = "public") -> str:
        try:
            rows = execute_query(
                self._manager,
                """
                SELECT
                    c.column_name                          AS name,
                    c.data_type                            AS type,
                    c.character_maximum_length             AS max_length,
                    c.is_nullable = 'YES'                  AS nullable,
                    c.column_default                       AS default_value,
                    EXISTS (
                        SELECT 1
                        FROM   information_schema.table_constraints tc
                        JOIN   information_schema.key_column_usage kcu
                               ON  kcu.constraint_name = tc.constraint_name
                               AND kcu.table_schema    = tc.table_schema
                        WHERE  tc.constraint_type = 'PRIMARY KEY'
                          AND  tc.table_schema     = c.table_schema
                          AND  tc.table_name       = c.table_name
                          AND  kcu.column_name     = c.column_name
                    ) AS primary_key
                FROM information_schema.columns c
                WHERE c.table_schema = :schema
                  AND c.table_name   = :table
                ORDER BY c.ordinal_position;
                """,
                {"schema": schema_name, "table": table_name},
            )
            if not rows:
                return json.dumps({
                    "error": f"Table '{schema_name}.{table_name}' not found. "
                             "Use postgres_list_tables to see available tables.",
                })
            for col in rows:
                if col.get("max_length") is not None:
                    col["type"] = f"{col['type']}({col['max_length']})"
                col.pop("max_length", None)

            return json.dumps({
                "schema": schema_name,
                "table": table_name,
                "columns": rows,
            })
        except Exception as e:
            return f"Error describing table '{schema_name}.{table_name}': {e}"


# ---------------------------------------------------------------------------
# Tool 5: Query
# ---------------------------------------------------------------------------

class QueryInput(BaseModel):
    sql: str = Field(
        ...,
        description=(
            "A read-only SELECT query to execute. "
            "Only SELECT statements are permitted — no INSERT, UPDATE, DELETE, DROP, etc. "
            "CTEs (WITH ... AS (...) SELECT ...) are supported."
        ),
    )
    max_rows: int = Field(
        default=500,
        ge=1,
        le=1000,
        description="Maximum rows to return (1–1000, default 500). "
                    "If the result is truncated, 'truncated: true' is set in the response.",
    )


class PostgresQueryTool(BaseTool):
    name: str = "postgres_query"
    description: str = """
    Execute a read-only SELECT query against the PostgreSQL database.

    Only SELECT statements are allowed. The query is wrapped in a
    read-only transaction as an additional safety layer.

    Use postgres_describe_table first to understand column names and types
    before writing your query.

    Returns: JSON object with row_count, rows array, and a truncated flag.
    If truncated is true, refine your query with WHERE or LIMIT clauses.
    """
    args_schema: Type[BaseModel] = QueryInput

    _manager: PostgresConnectionManager = None

    def __init__(self, manager: Optional[PostgresConnectionManager] = None, **kwargs):
        super().__init__(**kwargs)
        object.__setattr__(self, "_manager", manager or default_manager)

    def _run(self, sql: str, max_rows: int = 500) -> str:
        try:
            validate_select_only(sql)
        except ValueError as e:
            return f"Query rejected: {e}"

        try:
            rows, truncated = execute_readonly_query(self._manager, sql, max_rows)
            return json.dumps({
                "row_count": len(rows),
                "truncated": truncated,
                "rows": rows,
            }, default=str)  # handles date/decimal/UUID serialisation
        except Exception as e:
            return (
                f"Query failed: {e}\n"
                f"Use postgres_list_schemas, postgres_list_tables, and "
                f"postgres_describe_table to verify table and column names."
            )


# AMP derives the expected class name from the package name (postgres_tool → PostgresTool).
PostgresTool = PostgresQueryTool
