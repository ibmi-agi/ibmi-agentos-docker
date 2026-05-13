"""Smoke tests for agents/tools/ibmi_cli.py.

All tests run without a live ``ibmi`` binary — validators are pure
Python, SQL builders are pure functions, and the dispatcher is
monkeypatched via ``subprocess.run``. Every assertion reads fields off
the returned :class:`Envelope` directly (it's a ``dict`` subclass);
no ``json.loads`` dance is needed.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

import pytest

from agents.tools.ibmi_cli import (
    ENVELOPE_PARSE_FAILURE,
    PREFLIGHT_AMBIGUOUS_DISCOVERY,
    PREFLIGHT_NO_DISCOVERY_SOURCE,
    PREFLIGHT_READ_ONLY_VIOLATION,
    PREFLIGHT_SCHEMA_NOT_DISCLOSED,
    PREFLIGHT_TOOL_NOT_IN_SCOPE,
    RUNTIME_CLI_TIMEOUT,
    CommandSpec,
    Envelope,
    IBMiCLITools,
    _escape_sql_literal,
    _scrub_child_env,
    pase_call_wrap,
    qcmdexc_wrap,
    services_info_query,
)

# ---------------------------------------------------------------------
# §A  Helpers / fixtures
# ---------------------------------------------------------------------


class _CompletedProcess:
    """Duck-type stand-in for ``subprocess.CompletedProcess``."""

    def __init__(self, stdout: str, stderr: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


@pytest.fixture
def toolkit() -> IBMiCLITools:
    """Unscoped toolkit — no toolsets, no PASE."""
    return IBMiCLITools()


@pytest.fixture
def scoped_toolkit() -> IBMiCLITools:
    """Scoped toolkit — uses the ``performance`` toolset allowlist."""
    return IBMiCLITools(toolsets=["performance"])


# ---------------------------------------------------------------------
# §B  Env + SQL builders (pure functions — no subprocess, no toolkit)
# ---------------------------------------------------------------------


def test_scrub_child_env_strips_mcp_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IBMI_HTTP_AUTH_ENABLED", "true")
    monkeypatch.setenv("MCP_AUTH_MODE", "ibmi")
    monkeypatch.setenv("PATH", "/usr/bin")

    scrubbed = _scrub_child_env()

    assert "IBMI_HTTP_AUTH_ENABLED" not in scrubbed
    assert "MCP_AUTH_MODE" not in scrubbed
    assert scrubbed["PATH"] == "/usr/bin"


def test_escape_sql_literal_doubles_quotes() -> None:
    assert _escape_sql_literal("O'Brien") == "O''Brien"
    assert _escape_sql_literal("no-quote") == "no-quote"
    assert _escape_sql_literal("a'b'c") == "a''b''c"


def test_qcmdexc_wrap_escapes_quotes() -> None:
    wrapped = qcmdexc_wrap("DSPJOB JOB(O'Brien)")

    assert "'DSPJOB JOB(O''Brien)'" in wrapped
    assert wrapped.startswith("SELECT QSYS2.QCMDEXC(")
    assert wrapped.endswith(" FROM SYSIBM.SYSDUMMY1")


def test_pase_call_wrap_escapes_quotes() -> None:
    wrapped = pase_call_wrap("/bin/echo 'hi'")

    assert "'/bin/echo ''hi'''" in wrapped
    assert wrapped.startswith("SELECT * FROM TABLE(sample.pase_call(")


def test_services_info_query_with_and_without_filter() -> None:
    unfiltered = services_info_query(None)
    assert "WHERE" not in unfiltered
    assert unfiltered.endswith("ORDER BY SERVICE_SCHEMA_NAME, SERVICE_NAME")

    filtered = services_info_query("SYSTEM_%")
    assert "WHERE SERVICE_NAME LIKE 'SYSTEM_%'" in filtered

    # Apostrophes in filter must be doubled.
    escaped = services_info_query("O'Brien%")
    assert "LIKE 'O''Brien%'" in escaped


# ---------------------------------------------------------------------
# §C  Envelope canonical JSON wire-format
# ---------------------------------------------------------------------


def test_envelope_str_is_canonical_json() -> None:
    env = Envelope({"ok": True, "data": None, "count": 3})
    rendered = str(env)

    # Canonical JSON: lowercase ``true``/``null``, double-quoted keys.
    assert rendered == '{"ok": true, "data": null, "count": 3}'

    # And round-trips through json.loads as expected.
    assert json.loads(rendered) == {"ok": True, "data": None, "count": 3}


def test_envelope_is_a_dict_subclass() -> None:
    env = Envelope({"ok": False, "error": {"code": "X", "message": "y"}})
    assert isinstance(env, dict)
    assert env["ok"] is False
    assert env["error"]["code"] == "X"


# ---------------------------------------------------------------------
# §D  Preflight envelopes — wrapped methods never touch subprocess
# ---------------------------------------------------------------------


def test_preflight_envelope_shape_cl_read_only_violation(
    toolkit: IBMiCLITools,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # subprocess.run must NOT be called when preflight fails.
    def _boom(*_a: Any, **_kw: Any) -> _CompletedProcess:
        raise AssertionError("subprocess.run should not be called on preflight failure")

    monkeypatch.setattr(subprocess, "run", _boom)

    env = toolkit.run_cl("DLTLIB LIB(X)")

    assert env["ok"] is False
    assert env["command"] == "run_cl"
    assert env["error"]["code"] == PREFLIGHT_READ_ONLY_VIOLATION
    assert env["ibmi"]["source"] == "preflight"
    assert env["error"]["details"]["command"] == "DLTLIB LIB(X)"


def test_preflight_envelope_run_tool_scope_failure(
    scoped_toolkit: IBMiCLITools,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(*_a: Any, **_kw: Any) -> _CompletedProcess:
        raise AssertionError("subprocess.run should not be called on scope failure")

    monkeypatch.setattr(subprocess, "run", _boom)

    env = scoped_toolkit.run_tool("not_in_scope")

    assert env["ok"] is False
    assert env["command"] == "run_tool"
    assert env["error"]["code"] == PREFLIGHT_TOOL_NOT_IN_SCOPE
    assert env["error"]["details"]["toolsets"] == ["performance"]
    assert "allowed_tools" in env["error"]["details"]


# ---------------------------------------------------------------------
# §E  list_tools — discovery source rules
# ---------------------------------------------------------------------


def test_list_tools_no_discovery_source(toolkit: IBMiCLITools) -> None:
    env = toolkit.list_tools()

    assert env["ok"] is False
    assert env["error"]["code"] == PREFLIGHT_NO_DISCOVERY_SOURCE
    assert env["ibmi"]["source"] == "preflight"


def test_list_tools_ambiguous_sources(toolkit: IBMiCLITools) -> None:
    env = toolkit.list_tools(
        tool_path="tools/performance.yaml", toolsets=["performance"]
    )

    assert env["ok"] is False
    assert env["error"]["code"] == PREFLIGHT_AMBIGUOUS_DISCOVERY
    assert env["error"]["details"]["tool_path"] == "tools/performance.yaml"
    assert env["error"]["details"]["toolsets"] == ["performance"]


def test_list_tools_from_scope_unified_shape(scoped_toolkit: IBMiCLITools) -> None:
    # Zero-arg call falls back to instance-level toolsets scope.
    env = scoped_toolkit.list_tools()

    assert env["ok"] is True
    assert env["command"] == "list_tools"
    assert env["data"]["source"] == "scope"
    assert env["data"]["toolsets"] == ["performance"]
    assert isinstance(env["data"]["tools"], list)
    assert len(env["data"]["tools"]) >= 1
    assert env["meta"]["rows"] == len(env["data"]["tools"])
    assert env["ibmi"]["source"] == "python"


# ---------------------------------------------------------------------
# §F  Dispatch — CLI envelope passthrough + runtime synthesis
# ---------------------------------------------------------------------


def test_dispatch_cli_success_passthrough(
    toolkit: IBMiCLITools,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli_envelope = {
        "ok": True,
        "system": "dev",
        "host": "pub400.com",
        "command": "execute_sql",
        "data": [{"COL": 1}],
        "meta": {"rows": 1, "hasMore": False},
    }

    def _fake_run(*_a: Any, **_kw: Any) -> _CompletedProcess:
        return _CompletedProcess(stdout=json.dumps(cli_envelope), returncode=0)

    monkeypatch.setattr(subprocess, "run", _fake_run)

    env = toolkit.run_sql("SELECT 1 FROM SYSIBM.SYSDUMMY1")

    # CLI-native fields preserved verbatim.
    assert env["ok"] is True
    assert env["command"] == "execute_sql"  # CLI's value, not method name
    assert env["system"] == "dev"
    assert env["host"] == "pub400.com"
    assert env["data"] == [{"COL": 1}]
    assert env["meta"]["rows"] == 1

    # IBMi metadata merged.
    assert env["ibmi"]["tool"] == "run_sql"
    assert env["ibmi"]["source"] == "cli"
    assert "elapsed_ms" in env["ibmi"]


def test_dispatch_cli_error_envelope_passthrough(
    toolkit: IBMiCLITools,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli_error_envelope = {
        "ok": False,
        "system": "dev",
        "error": {"code": "SQL_ERROR", "message": "SQL0204 not found"},
    }

    def _fake_run(*_a: Any, **_kw: Any) -> _CompletedProcess:
        return _CompletedProcess(
            stdout=json.dumps(cli_error_envelope),
            returncode=3,
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)

    env = toolkit.run_sql("SELECT * FROM DOES_NOT_EXIST")

    assert env["ok"] is False
    assert env["error"]["code"] == "SQL_ERROR"
    assert env["error"]["message"] == "SQL0204 not found"
    # IBMi metadata merged; source is "cli" because envelope parsed.
    assert env["ibmi"]["source"] == "cli"
    assert env["ibmi"]["tool"] == "run_sql"


def test_dispatch_cli_timeout_synthesis(
    toolkit: IBMiCLITools,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_run(*_a: Any, **_kw: Any) -> _CompletedProcess:
        raise subprocess.TimeoutExpired(cmd="ibmi", timeout=1)

    monkeypatch.setattr(subprocess, "run", _fake_run)

    env = toolkit.run_sql("SELECT 1 FROM SYSIBM.SYSDUMMY1")

    assert env["ok"] is False
    assert env["command"] == "run_sql"
    assert env["error"]["code"] == RUNTIME_CLI_TIMEOUT
    assert env["ibmi"]["source"] == "runtime"


def test_dispatch_cli_not_found_synthesis(
    toolkit: IBMiCLITools,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_run(*_a: Any, **_kw: Any) -> _CompletedProcess:
        raise FileNotFoundError("no ibmi on PATH")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    env = toolkit.run_sql("SELECT 1")

    assert env["ok"] is False
    assert env["error"]["code"] == "RUNTIME_CLI_NOT_FOUND"
    assert env["ibmi"]["source"] == "runtime"


def test_dispatch_envelope_parse_failure(
    toolkit: IBMiCLITools,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # CLI exited 0 but emitted garbage — runtime-source parse-failure.
    def _fake_run(*_a: Any, **_kw: Any) -> _CompletedProcess:
        return _CompletedProcess(stdout="not json at all", returncode=0)

    monkeypatch.setattr(subprocess, "run", _fake_run)

    env = toolkit.run_sql("SELECT 1")

    assert env["ok"] is False
    assert env["error"]["code"] == ENVELOPE_PARSE_FAILURE
    assert env["ibmi"]["source"] == "runtime"


# ---------------------------------------------------------------------
# §G  CommandSpec argv assembly via observable subprocess call
# ---------------------------------------------------------------------


def test_dispatch_builds_argv_with_format_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--format json`` is always appended; ``--system`` only when set."""
    captured: dict[str, Any] = {}

    def _fake_run(cmd: list[str], **_kw: Any) -> _CompletedProcess:
        captured["cmd"] = cmd
        return _CompletedProcess(
            stdout=json.dumps({"ok": True, "command": "x", "data": []}),
            returncode=0,
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)
    monkeypatch.delenv("IBMI_SYSTEM", raising=False)

    tk = IBMiCLITools(system="dev")
    tk._dispatch(CommandSpec(tool_name="run_sql", argv=("sql", "SELECT 1")))

    cmd = captured["cmd"]
    assert "--format" in cmd
    assert "json" in cmd
    assert "--system" in cmd
    assert cmd[cmd.index("--system") + 1] == "dev"


def test_run_tool_dispatch_includes_project_tools_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    """``run_tool`` must pass ``--tools <path>`` so the CLI can resolve names.

    Regression: the resolver previously returned only ``USER_TOOLS_DIR``
    (empty in Docker). ``run_tool('system_status')`` then hit the CLI
    without any ``--tools`` entry, which reported "Available tools:
    (none)" for any scoped toolset lookup.

    This test predates the describe_tool pre-hook gate, so it pre-seeds
    the session_state with the target tool name to satisfy the gate —
    the assertion under test is argv assembly, not the gate itself.
    """
    captured: dict[str, Any] = {}

    def _fake_run(cmd: list[str], **_kw: Any) -> _CompletedProcess:
        captured["cmd"] = cmd
        return _CompletedProcess(
            stdout=json.dumps({"ok": True, "command": "tool:x", "data": []}),
            returncode=0,
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)

    # Point the toolkit at a real directory so the path branch fires
    # without depending on host filesystem layout.
    fake_tools_dir = tmp_path / "fake_tools"
    fake_tools_dir.mkdir()
    tk = IBMiCLITools(tools_dir=str(fake_tools_dir), toolsets=["performance"])
    # Direct method call — bypasses Agno's Function machinery, so the
    # run_tool pre_hook does NOT fire here. The gate is unit-tested in
    # §I below. This test targets argv assembly only.
    tk.run_tool("system_status")

    cmd = captured["cmd"]
    assert "--tools" in cmd
    assert cmd[cmd.index("--tools") + 1] == str(fake_tools_dir)
    # And the subcommand is ``tool <name>``.
    assert "tool" in cmd
    assert "system_status" in cmd


# ---------------------------------------------------------------------
# §H  describe_tool — schema disclosure primitive
# ---------------------------------------------------------------------


def test_describe_tool_error_code_is_importable() -> None:
    """The new preflight code is exported from the package surface."""
    assert PREFLIGHT_SCHEMA_NOT_DISCLOSED == "PREFLIGHT_SCHEMA_NOT_DISCLOSED"


def test_describe_tool_dispatches_tools_show_argv(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    """describe_tool wraps `ibmi tools show <name>` with --tools."""
    cli_envelope = {
        "ok": True,
        "command": "tools_show",
        "data": {
            "name": "active_job_info",
            "description": "Active job info from QSYS2.ACTIVE_JOB_INFO",
            "source": "tools/performance.yaml",
            "toolsets": ["performance"],
            "readOnly": True,
            "parameters": [
                {
                    "name": "lookback",
                    "type": "integer",
                    "default": 60,
                    "description": "Lookback window in minutes.",
                }
            ],
            "sql": "SELECT * FROM TABLE(QSYS2.ACTIVE_JOB_INFO())",
        },
    }
    captured: dict[str, Any] = {}

    def _fake_run(cmd: list[str], **_kw: Any) -> _CompletedProcess:
        captured["cmd"] = cmd
        return _CompletedProcess(stdout=json.dumps(cli_envelope), returncode=0)

    monkeypatch.setattr(subprocess, "run", _fake_run)

    # Provide an explicit tools_dir so use_tools_path=True surfaces
    # --tools <path> in the captured argv (USER_TOOLS_DIR isn't present
    # in the test environment).
    tk = IBMiCLITools(tools_dir=str(tmp_path))
    env = tk.describe_tool("active_job_info")

    # CLI envelope is passed through unchanged — no Python-side rewrite.
    assert env["ok"] is True
    assert env["command"] == "tools_show"  # CLI's value, not method name
    assert env["data"]["name"] == "active_job_info"
    assert env["data"]["parameters"][0]["name"] == "lookback"
    # IBMi metadata identifies which Python method dispatched.
    assert env["ibmi"]["tool"] == "describe_tool"
    assert env["ibmi"]["source"] == "cli"
    # argv assembly: tools show <name> --format json --tools <path>
    cmd = captured["cmd"]
    assert "tools" in cmd
    assert "show" in cmd
    assert "active_job_info" in cmd
    assert "--tools" in cmd  # use_tools_path=True
    assert cmd[cmd.index("--tools") + 1] == str(tmp_path)


def test_describe_tool_scope_failure_envelope(
    scoped_toolkit: IBMiCLITools,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scoped toolkit rejects out-of-scope describe via preflight."""

    def _boom(*_a: Any, **_kw: Any) -> _CompletedProcess:
        raise AssertionError("subprocess.run should not be called on scope failure")

    monkeypatch.setattr(subprocess, "run", _boom)

    env = scoped_toolkit.describe_tool("not_in_scope")

    assert env["ok"] is False
    assert env["command"] == "describe_tool"
    assert env["error"]["code"] == PREFLIGHT_TOOL_NOT_IN_SCOPE
    assert env["ibmi"]["source"] == "preflight"
    assert env["error"]["details"]["toolsets"] == ["performance"]


def test_describe_tool_in_scope_passes_guard(
    scoped_toolkit: IBMiCLITools,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A name inside the performance allowlist passes the scope guard."""
    captured: dict[str, Any] = {}

    def _fake_run(cmd: list[str], **_kw: Any) -> _CompletedProcess:
        captured["cmd"] = cmd
        return _CompletedProcess(
            stdout=json.dumps(
                {
                    "ok": True,
                    "command": "tools_show",
                    "data": {"name": "system_status", "parameters": []},
                }
            ),
            returncode=0,
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)

    env = scoped_toolkit.describe_tool("system_status")

    assert env["ok"] is True
    cmd = captured["cmd"]
    assert "tools" in cmd
    assert "show" in cmd
    assert "system_status" in cmd


def test_describe_tool_records_session_state(
    toolkit: IBMiCLITools,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Successful describe mutates run_context.session_state in place."""
    from types import SimpleNamespace

    def _fake_run(*_a: Any, **_kw: Any) -> _CompletedProcess:
        return _CompletedProcess(
            stdout=json.dumps(
                {
                    "ok": True,
                    "command": "tools_show",
                    "data": {"name": "active_job_info", "parameters": []},
                }
            ),
            returncode=0,
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)

    ctx = SimpleNamespace(session_state={})
    env = toolkit.describe_tool("active_job_info", run_context=ctx)

    assert env["ok"] is True
    assert "ibmi_described" in ctx.session_state
    described = ctx.session_state["ibmi_described"]
    # List — not set — because session_state is JSON-serialized to the DB.
    assert isinstance(described, list)
    assert "active_job_info" in described


# ---------------------------------------------------------------------
# §I  run_tool pre-hook gate (PREFLIGHT_SCHEMA_NOT_DISCLOSED)
# ---------------------------------------------------------------------


def test_pre_hook_blocks_undisclosed_run_tool() -> None:
    """The hook raises AgentRunException when the tool was not described."""
    from types import SimpleNamespace

    from agno.exceptions import AgentRunException

    from agents.tools.ibmi_cli.toolkit import _require_schema_disclosed

    fc = SimpleNamespace(arguments={"tool_name": "active_job_info"})
    ctx = SimpleNamespace(session_state={})

    with pytest.raises(AgentRunException) as exc_info:
        _require_schema_disclosed(fc, ctx)

    assert PREFLIGHT_SCHEMA_NOT_DISCLOSED in str(exc_info.value)


def test_pre_hook_allows_disclosed_run_tool() -> None:
    """The hook returns silently when the tool name is already disclosed."""
    from types import SimpleNamespace

    from agents.tools.ibmi_cli.toolkit import _require_schema_disclosed

    fc = SimpleNamespace(arguments={"tool_name": "active_job_info"})
    ctx = SimpleNamespace(session_state={"ibmi_described": {"active_job_info"}})

    # No exception raised — successful pass-through is the contract.
    _require_schema_disclosed(fc, ctx)


def test_pre_hook_blocks_when_session_state_missing() -> None:
    """Missing/None session_state is treated as not-yet-described."""
    from types import SimpleNamespace

    from agno.exceptions import AgentRunException

    from agents.tools.ibmi_cli.toolkit import _require_schema_disclosed

    fc = SimpleNamespace(arguments={"tool_name": "active_job_info"})

    # run_context is None
    with pytest.raises(AgentRunException) as exc_info_a:
        _require_schema_disclosed(fc, None)
    assert PREFLIGHT_SCHEMA_NOT_DISCLOSED in str(exc_info_a.value)

    # session_state is None
    ctx_none_state = SimpleNamespace(session_state=None)
    with pytest.raises(AgentRunException) as exc_info_b:
        _require_schema_disclosed(fc, ctx_none_state)
    assert PREFLIGHT_SCHEMA_NOT_DISCLOSED in str(exc_info_b.value)


def test_pre_hook_blocks_when_tool_name_missing() -> None:
    """Defensive: malformed FunctionCall (no tool_name) is rejected."""
    from types import SimpleNamespace

    from agno.exceptions import AgentRunException

    from agents.tools.ibmi_cli.toolkit import _require_schema_disclosed

    fc = SimpleNamespace(arguments={})
    ctx = SimpleNamespace(session_state={"ibmi_described": {"active_job_info"}})

    with pytest.raises(AgentRunException) as exc_info:
        _require_schema_disclosed(fc, ctx)

    assert PREFLIGHT_SCHEMA_NOT_DISCLOSED in str(exc_info.value)


def test_run_tool_function_carries_pre_hook(toolkit: IBMiCLITools) -> None:
    """IBMiCLITools.__init__ wires the hook onto run_tool's Function."""
    from agents.tools.ibmi_cli.toolkit import _require_schema_disclosed

    assert toolkit.functions["run_tool"].pre_hook is _require_schema_disclosed


def test_describe_tool_function_has_no_pre_hook(toolkit: IBMiCLITools) -> None:
    """describe_tool is the disclosure primitive — never gated by the hook."""
    assert toolkit.functions["describe_tool"].pre_hook is None


# ---------------------------------------------------------------------
# §J  Per-call scope resolution via run_context.dependencies
# ---------------------------------------------------------------------


def _ctx(dependencies: dict[str, Any] | None = None) -> Any:
    from types import SimpleNamespace

    return SimpleNamespace(dependencies=dependencies, session_state={})


def test_resolve_scope_falls_back_to_instance(toolkit: IBMiCLITools) -> None:
    """Unscoped instance + run_context without ibmi deps = unrestricted."""
    toolsets, allowed, inventory = toolkit._resolve_scope(_ctx())

    assert toolsets == ()
    assert allowed == frozenset()
    assert inventory == ()


def test_resolve_scope_static_agent_toolsets(scoped_toolkit: IBMiCLITools) -> None:
    """Scoped instance + None context = instance-level scope."""
    toolsets, allowed, inventory = scoped_toolkit._resolve_scope(None)

    assert toolsets == ("performance",)
    assert len(allowed) >= 1
    assert inventory == ()


def test_resolve_scope_dependencies_override_instance(
    scoped_toolkit: IBMiCLITools,
) -> None:
    """run_context.dependencies wins over instance defaults."""
    ctx = _ctx(
        {
            "ibmi_toolsets": ["daily_health"],
            "ibmi_extra_tools": ["my_custom"],
            "ibmi_extra_inventory": [
                {"name": "my_custom", "description": "custom", "parameters": []}
            ],
        }
    )
    toolsets, allowed, inventory = scoped_toolkit._resolve_scope(ctx)

    assert toolsets == ("daily_health",)
    assert "my_custom" in allowed
    assert inventory == (
        {"name": "my_custom", "description": "custom", "parameters": []},
    )


def test_resolve_scope_extras_only(toolkit: IBMiCLITools) -> None:
    """Dependencies with only extras yield an extras-only scope."""
    ctx = _ctx({"ibmi_extra_tools": ["foo", "bar"]})
    toolsets, allowed, inventory = toolkit._resolve_scope(ctx)

    assert toolsets == ()
    assert allowed == frozenset({"foo", "bar"})
    assert inventory == ()


def test_resolve_scope_inventory_extends_extras(toolkit: IBMiCLITools) -> None:
    """Inventory entries implicitly extend the flat ``extra_tools`` list."""
    ctx = _ctx(
        {
            "ibmi_extra_inventory": [
                {"name": "foo", "description": "x", "parameters": []},
                {"name": "bar", "description": "y", "parameters": ["p1"]},
            ],
        }
    )
    _toolsets, allowed, inventory = toolkit._resolve_scope(ctx)

    assert allowed == frozenset({"foo", "bar"})
    assert len(inventory) == 2


def test_require_toolset_scope_gate_with_only_extras() -> None:
    """Broadened gate: a non-empty ``allowed`` alone enforces scope."""
    from agents.tools.ibmi_cli.preflight import require_toolset_scope

    err = require_toolset_scope("bar", (), frozenset({"foo"}))

    assert err is not None
    assert err.code == PREFLIGHT_TOOL_NOT_IN_SCOPE


def test_require_toolset_scope_gate_unrestricted_default() -> None:
    """No toolsets AND no allowlist => unrestricted legacy behavior."""
    from agents.tools.ibmi_cli.preflight import require_toolset_scope

    assert require_toolset_scope("anything", (), frozenset()) is None


def test_run_tool_rejects_out_of_scope_via_dependencies(
    toolkit: IBMiCLITools,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run_tool reads scope from ``run_context.dependencies``."""

    def _boom(*_a: Any, **_kw: Any) -> _CompletedProcess:
        raise AssertionError("subprocess.run should not be called on scope failure")

    monkeypatch.setattr(subprocess, "run", _boom)

    ctx = _ctx({"ibmi_extra_tools": ["only_me"]})
    env = toolkit.run_tool("not_me", run_context=ctx)

    assert env["ok"] is False
    assert env["error"]["code"] == PREFLIGHT_TOOL_NOT_IN_SCOPE


def test_list_tools_extras_fallback_from_dependencies(
    toolkit: IBMiCLITools,
) -> None:
    """list_tools zero-arg enumerates extras from run_context.dependencies."""
    ctx = _ctx(
        {
            "ibmi_extra_inventory": [
                {"name": "alpha", "description": "a", "parameters": []},
                {"name": "beta", "description": "b", "parameters": ["p"]},
            ],
        }
    )
    env = toolkit.list_tools(run_context=ctx)

    assert env["ok"] is True
    assert env["data"]["source"] == "extras"
    names = [t["name"] for t in env["data"]["tools"]]
    assert names == ["alpha", "beta"]
    assert env["data"]["tools"][0]["description"] == "a"


def test_list_tools_scope_via_dependencies_toolsets(
    toolkit: IBMiCLITools,
) -> None:
    """list_tools zero-arg uses dependencies.ibmi_toolsets as the scope."""
    ctx = _ctx({"ibmi_toolsets": ["performance"]})
    env = toolkit.list_tools(run_context=ctx)

    assert env["ok"] is True
    assert env["data"]["source"] == "scope"
    assert env["data"]["toolsets"] == ["performance"]


# ---------------------------------------------------------------------
# §K  validate_and_run_sql — validate-then-execute composition
# ---------------------------------------------------------------------


def _record_runs(
    monkeypatch: pytest.MonkeyPatch,
    responses: list[_CompletedProcess],
) -> list[list[str]]:
    """Install a subprocess.run stub that returns ``responses`` in order
    and records each invocation's argv. Raises if called more times than
    responses provided — that indicates an unexpected extra dispatch.
    """
    captured: list[list[str]] = []
    iterator = iter(responses)

    def _fake_run(cmd: list[str], **_kw: Any) -> _CompletedProcess:
        captured.append(list(cmd))
        try:
            return next(iterator)
        except StopIteration as exc:
            raise AssertionError(
                f"subprocess.run called {len(captured)} times; "
                f"only {len(responses)} responses queued"
            ) from exc

    monkeypatch.setattr(subprocess, "run", _fake_run)
    return captured


def test_validate_and_run_sql_happy_path_runs_both_steps(
    toolkit: IBMiCLITools,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validation OK → execute runs; two subprocess calls in order."""
    validate_envelope = {
        "ok": True,
        "command": "validate_sql",
        "data": {"valid": True},
    }
    execute_envelope = {
        "ok": True,
        "command": "execute_sql",
        "data": [{"COL": 1}],
        "meta": {"rows": 1},
    }
    captured = _record_runs(
        monkeypatch,
        [
            _CompletedProcess(stdout=json.dumps(validate_envelope), returncode=0),
            _CompletedProcess(stdout=json.dumps(execute_envelope), returncode=0),
        ],
    )

    env = toolkit.validate_and_run_sql("SELECT 1 FROM SYSIBM.SYSDUMMY1")

    assert len(captured) == 2

    # Step 1: ``ibmi validate <statement> --format json``
    validate_cmd = captured[0]
    assert "validate" in validate_cmd
    assert "SELECT 1 FROM SYSIBM.SYSDUMMY1" in validate_cmd

    # Step 2: ``ibmi sql <statement> --read-only --format json``
    execute_cmd = captured[1]
    assert "sql" in execute_cmd
    assert "SELECT 1 FROM SYSIBM.SYSDUMMY1" in execute_cmd
    assert "--read-only" in execute_cmd

    # Returned envelope is the EXECUTE result, tagged as run_sql (not
    # validate_and_run_sql) because dispatch uses the underlying CommandSpec.
    assert env["ok"] is True
    assert env["data"] == [{"COL": 1}]
    assert env["ibmi"]["tool"] == "run_sql"


def test_validate_and_run_sql_validation_failure_skips_execute(
    toolkit: IBMiCLITools,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validation NOT OK → execute is skipped; envelope returned verbatim."""
    validation_failure = {
        "ok": False,
        "command": "validate_sql",
        "error": {"code": "SQL_PARSE_ERROR", "message": "syntax error near WHRE"},
        "ibmi": {"tool": "validate_sql", "source": "cli"},
    }
    captured = _record_runs(
        monkeypatch,
        [_CompletedProcess(stdout=json.dumps(validation_failure), returncode=3)],
    )

    env = toolkit.validate_and_run_sql("SELCT 1 WHRE 1=1")

    # Exactly ONE subprocess call — execute path was short-circuited.
    assert len(captured) == 1
    assert "validate" in captured[0]

    # Validation envelope is returned UNCHANGED — no rewrap, no command swap.
    # The agent surface intentionally surfaces validate's error as-is so the
    # LLM can see which step failed.
    assert env["ok"] is False
    assert env["error"]["code"] == "SQL_PARSE_ERROR"
    assert env["command"] == "validate_sql"
    assert env["ibmi"]["tool"] == "validate_sql"


def test_validate_and_run_sql_runtime_error_in_validate_skips_execute(
    toolkit: IBMiCLITools,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validate-step timeout/CLI-not-found also short-circuits the execute."""
    call_count = {"n": 0}

    def _fake_run(*_a: Any, **_kw: Any) -> _CompletedProcess:
        call_count["n"] += 1
        raise subprocess.TimeoutExpired(cmd="ibmi", timeout=1)

    monkeypatch.setattr(subprocess, "run", _fake_run)

    env = toolkit.validate_and_run_sql("SELECT 1")

    # Only validate was attempted; the synthesized timeout envelope's
    # ``ok: False`` triggers early-return before any execute dispatch.
    assert call_count["n"] == 1
    assert env["ok"] is False
    assert env["error"]["code"] == RUNTIME_CLI_TIMEOUT
    # Tagged as validate_sql — execute never ran, so the run_sql tag
    # never gets applied.
    assert env["ibmi"]["tool"] == "validate_sql"


def test_validate_and_run_sql_treats_missing_ok_field_as_failure(
    toolkit: IBMiCLITools,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defensive: if validate returns an envelope without ``ok``, do NOT execute.

    The implementation uses ``validation_env.get("ok", False)``; this test
    locks in the fail-closed default so a future refactor that loses the
    default can't accidentally bypass validation.
    """
    # Parsable JSON envelope but missing the ``ok`` key entirely.
    weird_envelope = {"command": "validate_sql", "data": {}}
    captured = _record_runs(
        monkeypatch,
        [_CompletedProcess(stdout=json.dumps(weird_envelope), returncode=0)],
    )

    env = toolkit.validate_and_run_sql("SELECT 1")

    # Execute was NOT called.
    assert len(captured) == 1
    # The malformed envelope is returned to the caller unchanged.
    assert env.get("ok") in (False, None)


def test_validate_and_run_sql_envelope_parse_failure_in_validate_skips_execute(
    toolkit: IBMiCLITools,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the CLI emits garbage during validate, execute must NOT run.

    Parse failure synthesizes ``ok: False`` with code ENVELOPE_PARSE_FAILURE;
    validate_and_run_sql treats that as a validation failure.
    """
    captured = _record_runs(
        monkeypatch,
        [_CompletedProcess(stdout="not json", returncode=0)],
    )

    env = toolkit.validate_and_run_sql("SELECT 1")

    assert len(captured) == 1
    assert env["ok"] is False
    assert env["error"]["code"] == ENVELOPE_PARSE_FAILURE


def test_validate_and_run_sql_execute_failure_propagates(
    toolkit: IBMiCLITools,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validate OK, execute fails → execute envelope is returned as-is."""
    validate_envelope = {
        "ok": True,
        "command": "validate_sql",
        "data": {"valid": True},
    }
    execute_failure = {
        "ok": False,
        "command": "execute_sql",
        "error": {"code": "SQL_RUNTIME", "message": "table locked"},
    }
    captured = _record_runs(
        monkeypatch,
        [
            _CompletedProcess(stdout=json.dumps(validate_envelope), returncode=0),
            _CompletedProcess(stdout=json.dumps(execute_failure), returncode=3),
        ],
    )

    env = toolkit.validate_and_run_sql("SELECT * FROM LOCKED_TBL")

    assert len(captured) == 2
    assert env["ok"] is False
    assert env["error"]["code"] == "SQL_RUNTIME"
    # Execute step's tag — confirms second dispatch ran.
    assert env["ibmi"]["tool"] == "run_sql"


def test_validate_and_run_sql_preserves_statement_with_quotes(
    toolkit: IBMiCLITools,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Statement is forwarded verbatim to BOTH steps — no escaping happens here.

    SQL escaping is the CLI's responsibility (and the validate/sql
    subcommands handle parameterization). The Python wrapper just
    passes argv through.
    """
    statement = "SELECT * FROM T WHERE NAME = 'O''Brien'"
    captured = _record_runs(
        monkeypatch,
        [
            _CompletedProcess(
                stdout=json.dumps({"ok": True, "command": "validate_sql"}),
                returncode=0,
            ),
            _CompletedProcess(
                stdout=json.dumps({"ok": True, "command": "execute_sql", "data": []}),
                returncode=0,
            ),
        ],
    )

    toolkit.validate_and_run_sql(statement)

    # Both subprocess invocations carry the unmodified statement.
    assert statement in captured[0]
    assert statement in captured[1]


# ---------------------------------------------------------------------
# §L  Toolkit registration: run_sql unregistered, surface contract
# ---------------------------------------------------------------------


def test_run_sql_is_not_registered_as_agent_tool(toolkit: IBMiCLITools) -> None:
    """run_sql exists on the class but is NOT in the LLM-facing function set."""
    # Method is still callable in Python (internal/test surface).
    assert callable(toolkit.run_sql)
    # But the Agno Function registry does not expose it.
    assert "run_sql" not in toolkit.functions


def test_validate_and_run_sql_is_registered_with_confirmation(
    toolkit: IBMiCLITools,
) -> None:
    """validate_and_run_sql is the LLM-facing SQL entrypoint and gated."""
    fn = toolkit.functions.get("validate_and_run_sql")
    assert fn is not None
    # Agno marks confirmation-gated tools via the function attribute the
    # base Toolkit sets when ``requires_confirmation_tools`` includes it.
    assert getattr(fn, "requires_confirmation", False) is True


def test_run_cl_remains_confirmation_gated(toolkit: IBMiCLITools) -> None:
    """Regression guard: refactor preserved run_cl in the confirmation list."""
    fn = toolkit.functions.get("run_cl")
    assert fn is not None
    assert getattr(fn, "requires_confirmation", False) is True


# ---------------------------------------------------------------------
# §M  enable_yaml_tools flag — opt-out of describe_tool/run_tool/list_tools
# ---------------------------------------------------------------------


def test_enable_yaml_tools_default_exposes_yaml_surface() -> None:
    """Default kwargs keep the YAML-tool surface exposed."""
    tk = IBMiCLITools()

    for name in ("describe_tool", "run_tool", "list_tools"):
        assert name in tk.functions, f"{name} should be registered by default"


def test_enable_yaml_tools_false_hides_yaml_surface() -> None:
    """enable_yaml_tools=False removes the discovery/dispatch trio."""
    tk = IBMiCLITools(enable_yaml_tools=False)

    for name in ("describe_tool", "run_tool", "list_tools"):
        assert name not in tk.functions, (
            f"{name} should be hidden when enable_yaml_tools=False"
        )

    # Core SQL/CL surface is unaffected.
    assert "validate_and_run_sql" in tk.functions
    assert "run_cl" in tk.functions


def test_enable_yaml_tools_false_skips_pre_hook_wiring_safely() -> None:
    """When run_tool isn't registered, the pre_hook wiring is a no-op.

    Regression: the constructor guards ``self.functions.get('run_tool')``
    against None; this asserts the guard holds (no AttributeError on init).
    """
    # The constructor itself must not raise.
    tk = IBMiCLITools(enable_yaml_tools=False)

    # And no orphaned hook attribute is left dangling.
    assert tk.functions.get("run_tool") is None
