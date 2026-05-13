"""
Eval Cases
==========

Each case sends one input to one agent and (optionally) checks two things:

- **judge** — ``AgentAsJudgeEval`` scores the response against ``criteria``
  (binary pass/fail) using an LLM.
- **reliability** — ``ReliabilityEval`` checks which tools fired against
  ``expected_tool_calls``.

Both check primitives are built-ins from Agno.
Results are stored in Postgres via ``eval_db`` (visible at os.agno.com).

Add a case below, then run ``uv run python -m evals``.
"""

from dataclasses import dataclass

from agno.agent import Agent

from agents.sql_service_guide import sql_service_guide_agent
from agents.system_health import system_health_agent
from agents.text2sql import text2sql_agent
from db import get_postgres_db

# Single eval DB instance — every case logs through it.
eval_db = get_postgres_db()


@dataclass(frozen=True)
class Case:
    """One eval case: an input to one agent + optional judge/reliability checks."""

    name: str
    agent: Agent
    input: str

    # Judge check (LLM judge against a rubric, binary pass/fail). Set ``criteria`` to enable.
    criteria: str | None = None

    # Reliability check (tool-call assertion). Set ``expected_tool_calls`` to enable.
    expected_tool_calls: tuple[str, ...] | None = None
    allow_additional_tool_calls: bool = True


CASES: tuple[Case, ...] = (
    # text2sql — inspects schema before composing a SELECT.
    Case(
        name="text2sql_inspects_schema_first",
        agent=text2sql_agent,
        input="List the first 5 rows of QSYS2.SYSTABLES",
        criteria=(
            "The response shows the agent inspected the table's columns (via "
            "describe_sql_object or get_table_columns) before writing the SELECT. "
            "The final SQL uses fully qualified names and applies FETCH FIRST 5 ROWS ONLY."
        ),
        expected_tool_calls=("describe_sql_object",),
    ),
    # text2sql — validates SQL before executing it.
    Case(
        name="text2sql_validates_before_execute",
        agent=text2sql_agent,
        input="Run `SELECT COUNT(*) FROM QSYS2.SYSTABLES`",
        criteria=(
            "The response includes the row count from QSYS2.SYSTABLES. "
            "The agent ran validate_query before execute_sql."
        ),
        expected_tool_calls=("validate_query", "execute_sql"),
    ),
    # system_health — uses the performance toolset for CPU questions.
    Case(
        name="system_health_uses_performance_toolset",
        agent=system_health_agent,
        input="What is current CPU utilization on this system?",
        criteria=(
            "The response includes a concrete CPU percentage value and explains "
            "the reading. The agent called the performance toolset (not a generic "
            "SQL query) to retrieve the metric."
        ),
    ),
    # sql_service_guide — uses sysadmin_browse to discover services by category.
    Case(
        name="sql_service_guide_browses_by_category",
        agent=sql_service_guide_agent,
        input="What SQL Services exist for performance monitoring?",
        criteria=(
            "The response lists at least three SQL Services with a one-line "
            "description for each. The agent used the sysadmin_browse or "
            "sysadmin_discovery toolset rather than improvising with ad-hoc SQL."
        ),
    ),
)
