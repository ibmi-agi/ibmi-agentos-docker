"""
Run Evals
=========

python -m evals                         # run all cases (concise UI)
python -m evals --tag smoke             # run a tagged subset
python -m evals --name <case>           # run one case
python -m evals --json-output out.json  # write machine-readable results
python -m evals -v                      # stream the agent's run with full panels

Agno's eval runner runs each case and evaluates the response with `AgentAsJudgeEval`
(when `criteria` is set) and/or `ReliabilityEval` (when `expected_tool_calls` is set).

Cases run the agents in-process on the host against the live stack: they need the
`agentos-db` and `ibmi-mcp-server` containers up, a model API key in `.env`, and real
IBM i credentials — every case exercises real (read-only) SQL against the configured
system.

Results log to Postgres through `eval_db`. Connect your AgentOS at os.agno.com to see
history.
"""

# Hydrate os.environ from .env before any module that reads env at import time
# (db_url, model factories, MCP_URL, etc.). Pre-existing shell vars take precedence.
from os import environ
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# Host-side runs reach the MCP server through its published port, not the
# compose-network hostname the containers use. .env or the shell still wins.
environ.setdefault("MCP_URL", "http://localhost:3010/mcp")

import sys  # noqa: E402

from agno.eval import cli  # noqa: E402

from evals.cases import CASES, eval_db  # noqa: E402

sys.exit(cli(CASES, db=eval_db))
