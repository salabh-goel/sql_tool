"""
Single-file example: Database Analyst Agent using postgres_tool.

This example shows how to wire up a CrewAI agent that can explore and
query any PostgreSQL database. The agent follows a disciplined workflow:
inspect schema first, then write precise SQL — never guessing column names.

Setup:
  1. Install dependencies:
       pip install crewai postgres_tool

  2. Set your database connection (choose one):
       export DATABASE_URL=postgresql://user:password@host:5432/dbname

     Or individual variables:
       export PG_HOST=your-host
       export PG_DATABASE=your-database
       export PG_USER=your-user
       export PG_PASSWORD=your-password

  3. Set your LLM API key, e.g.:
       export OPENAI_API_KEY=sk-...

  4. Run:
       python examples/database_analyst_agent.py
"""

import os
from crewai import Agent, Task, Crew, Process
from postgres_tool import (
    PostgresListDatabasesTool,
    PostgresListSchemasTool,
    PostgresListTablesTool,
    PostgresDescribeTableTool,
    PostgresQueryTool,
)

# ---------------------------------------------------------------------------
# Tool setup — all five tools share a single connection pool
# ---------------------------------------------------------------------------

pg_tools = [
    PostgresListDatabasesTool(),
    PostgresListSchemasTool(),
    PostgresListTablesTool(),
    PostgresDescribeTableTool(),
    PostgresQueryTool(),
]

# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------

database_analyst = Agent(
    role="Senior Database Analyst",
    goal=(
        "Explore and query the connected PostgreSQL database to extract accurate, "
        "actionable insights. Always inspect the schema before writing SQL. "
        "Verify that query results are complete and correctly scoped before reporting."
    ),
    backstory=(
        "You are a meticulous senior data analyst with 10+ years of experience across "
        "industries — from e-commerce and SaaS to finance and logistics. You have seen "
        "the damage caused by analysts who write SQL against schemas they don't understand: "
        "wrong column names, mismatched joins, silent data truncation. That has made you "
        "disciplined about process.\n\n"
        "Your standard workflow is non-negotiable:\n"
        "1. Call postgres_list_schemas to understand the database layout.\n"
        "2. Call postgres_list_tables for the schema you care about.\n"
        "3. Call postgres_describe_table for every table you plan to query — "
        "   never assume you know column names or types.\n"
        "4. Write a precise SELECT query using the exact column names you just confirmed.\n"
        "5. Check the 'truncated' flag in the response. If true, refine the query "
        "   with WHERE or LIMIT before reporting results.\n\n"
        "You write clean, readable SQL with meaningful aliases. You never fabricate "
        "column names. When results seem off, you go back and re-inspect the schema "
        "rather than guessing. Your analysis is always grounded in what the data "
        "actually says, not what you expect it to say."
    ),
    tools=pg_tools,
    verbose=True,
    allow_delegation=False,
    respect_context_window=True,
)

# ---------------------------------------------------------------------------
# Task definition
# ---------------------------------------------------------------------------

# Change this question to whatever you want the agent to investigate.
QUESTION = "What are the 10 most recent records in the largest table in the public schema?"

analysis_task = Task(
    description=(
        f"Answer the following question by querying the PostgreSQL database:\n\n"
        f"  {QUESTION}\n\n"
        "Follow your standard workflow: list schemas, list tables, describe relevant "
        "tables, then write your query. Report the results clearly and note any "
        "caveats about data completeness or truncation."
    ),
    expected_output=(
        "A clear answer to the question with supporting data from the database. "
        "Include the SQL query used, the row count returned, and any relevant "
        "observations about the data (e.g., nulls, unexpected values, truncation)."
    ),
    agent=database_analyst,
)

# ---------------------------------------------------------------------------
# Crew
# ---------------------------------------------------------------------------

crew = Crew(
    agents=[database_analyst],
    tasks=[analysis_task],
    process=Process.sequential,
    verbose=True,
)

if __name__ == "__main__":
    result = crew.kickoff()
    print("\n" + "=" * 60)
    print("RESULT")
    print("=" * 60)
    print(result.raw)
