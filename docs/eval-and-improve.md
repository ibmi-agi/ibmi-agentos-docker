# Eval and Improve an IBM i Agent

> Claude Code prompt. Open Claude Code in this repo and paste:
> `Run docs/eval-and-improve.md`

You are running the IBM i eval suite, diagnosing failures, and editing the smallest possible diff to make it pass. Repeat until green.

This loop is narrower than [`docs/improve-agent.md`](improve-agent.md) — that one is broad probe-based exploration; this one validates a fixed contract written down in `evals/cases.py`.

## 0. Preconditions

Stack is up (`curl -sSf http://localhost:8000/healthz` returns 200). `.env` has working IBM i creds and an LLM provider key.

## 1. Run the suite

```bash
uv run python -m evals -v
```

This runs every `Case` in `evals/cases.py`. Each case can assert:
- **`criteria`** — an LLM judge rubric, binary pass / fail
- **`expected_tool_calls`** — exact tool names that must have been called (reliability check)

Capture the verbose output. Note which cases fail and the failure mode (judge rejected the response vs. wrong tool called).

## 2. Add coverage if missing

The IBM i contract is rich — every "must" in `agents/instructions/*.md` and in `agents/utils/common.py::SQL_POLICY` deserves a case. If a critical behavior has no test, **add it now** before fixing anything else.

Patterns for IBM i evals:

```python
from agno.eval.case import Case

Case(
    name="text2sql-validates-before-execute",
    agent="ibmi-text2sql",
    input="Run SELECT * FROM QSYS2.SYSTABLES FETCH FIRST 5 ROWS ONLY",
    expected_tool_calls=["validate_query", "execute_sql"],
    criteria="The response must show the SQL was validated before execution.",
)

Case(
    name="text2sql-inspects-schema-first",
    agent="ibmi-text2sql",
    input="What's the average ORDER_TOTAL in QGPL.ORDERS?",
    expected_tool_calls=["describe_sql_object"],  # or get_table_columns
    criteria="The agent must inspect the schema before composing the aggregation SQL.",
)

Case(
    name="system-health-uses-performance-toolset",
    agent="ibmi-system-health",
    input="What is current CPU utilization?",
    expected_tool_calls=["get_system_status_detail"],  # from the performance toolset
    criteria="The response must include a numeric CPU percentage.",
)

Case(
    name="sql-guide-uses-discovery",
    agent="ibmi-sql-service-guide",
    input="What SQL Services exist for security auditing?",
    expected_tool_calls=["list_services_by_category"],  # from sysadmin_browse
    criteria="The response must list at least 3 service names, each with a one-line description.",
)
```

Resist over-specifying tool calls — only assert tools that are load-bearing for the contract. Don't assert `describe_sql_object` if you only care about `execute_sql`'s correctness.

## 3. Diagnose failures

For each failing case, classify the symptom:

| Symptom | Likely fix location |
|---|---|
| Wrong tool called (or tool not called) | Sharpen routing in `agents/instructions/ibmi-<slug>.md` |
| Right tool, malformed SQL | `agents/utils/common.py::SQL_POLICY` or `DOMAIN_RULES` — add an example |
| Right tool, judge rejected the prose | The agent's mission file is too vague about output format — add an example block |
| Tool called but result not surfaced | The agent is summarizing too aggressively — relax FORMATTING or override in mission |
| Hallucinated table/column names | Schema-inspection rule is being skipped — strengthen `SQL_POLICY` (move earlier, add explicit "before any SQL" wording) |
| Auth / connection error | Not an agent bug — surface to the user, check `.env` and the MCP server logs |

## 4. Edit minimally

Touch only the file that contains the failure mode. Don't sweep adjacent instructions.

## 5. Re-run only the failing cases

```bash
uv run python -m evals -v --case <case-name>
```

When that case passes, re-run the full suite:

```bash
uv run python -m evals -v
```

Check nothing regressed.

## 6. Loop

Repeat 1-5 until clean. If a case keeps failing after three attempts, the case itself might be wrong — re-read the contract and decide whether the case asserts something the system actually promises.

## 7. Commit
Summarize for the user: which cases were added, which were already there and failed, what fixed each one. Let them commit.
