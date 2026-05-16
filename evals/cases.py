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

NOTE: SAMPLE-flavored cases for the ``ibmi-data-agent`` will land in a
follow-up PR. The runner framework is preserved here so the eval entry
point keeps working; ``CASES`` is intentionally empty until then.
"""

from dataclasses import dataclass

from agno.agent import Agent

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


# TODO: re-author SAMPLE-flavored eval cases for ``ibmi-data-agent``.
CASES: tuple[Case, ...] = ()
