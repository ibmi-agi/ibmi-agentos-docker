"""IBMiCLITools — Agno Toolkit for the ``ibmi`` CLI.

All methods return an :class:`Envelope` — a ``dict[str, Any]`` subclass
whose ``__str__`` emits canonical JSON at the Agno wire boundary.
Python callers access fields directly via ``env["ok"]``, ``env["data"]``,
etc.

SECURITY: SQL literals are escaped in :mod:`.sql`; subprocess calls
are list-of-args with ``shell=False`` always; ``list_tools`` refuses
paths outside the workspace.
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import yaml
from agno.exceptions import AgentRunException
from agno.tools import Toolkit

from agents.config import (
    IBMI_CLI,
    IBMI_CLI_TIMEOUT,
    PROJECT_TOOLS_DIR,
    USER_TOOLS_DIR,
)
from agents.utils.tools import get_toolsets, get_toolsets_inventory, list_toolsets

from ._env import _scrub_child_env
from .dispatch import CommandSpec, _parse_cli_envelope
from .envelope import (
    PREFLIGHT_AMBIGUOUS_DISCOVERY,
    PREFLIGHT_FILE_NOT_FOUND,
    PREFLIGHT_INVALID_YAML,
    PREFLIGHT_NO_DISCOVERY_SOURCE,
    PREFLIGHT_SCHEMA_NOT_DISCLOSED,
    PREFLIGHT_UNKNOWN_TOOLSET,
    RUNTIME_CLI_NOT_FOUND,
    RUNTIME_CLI_TIMEOUT,
    Envelope,
    PreflightError,
    _error_envelope,
    _python_success_envelope,
)
from .preflight import (
    parse_tool_parameters,
    require_absolute_path,
    require_inquiry_verb,
    require_length_bounds,
    require_pase_enabled,
    require_toolset_scope,
    require_workspace_path,
)
from .sql import (
    pase_call_wrap,
    qcmdexc_wrap,
    services_info_query,
)

logger = logging.getLogger(__name__)


def _require_schema_disclosed(fc: Any, run_context: Any) -> None:
    """Pre-hook enforcing the list → describe → run workflow.

    Agno fires this before ``run_tool`` executes. It inspects the
    pending call's arguments and the per-session described-tool set
    carried in ``run_context.session_state``. If the target tool has
    not been described in this session, it raises
    :class:`AgentRunException` — Agno catches that, converts it to a
    recoverable tool failure, and surfaces it to the LLM so the model
    can correct course by calling ``describe_tool`` first.
    """
    arguments = getattr(fc, "arguments", None) or {}
    tool_name = arguments.get("tool_name")
    if not tool_name or not isinstance(tool_name, str):
        raise AgentRunException(
            f"{PREFLIGHT_SCHEMA_NOT_DISCLOSED}: run_tool requires a "
            f"'tool_name' argument. Call describe_tool(tool_name) "
            f"first to obtain the parameter schema, then call "
            f"run_tool(tool_name, parameters)."
        )

    session_state = getattr(run_context, "session_state", None)
    described: Any = None
    if isinstance(session_state, dict):
        described = session_state.get("ibmi_described")

    # ``ibmi_described`` is persisted to the DB via JSON, so it must
    # be a list — sets are not JSON-serializable. Accept set/frozenset
    # too for the direct-Python test path where nothing round-trips.
    if not isinstance(described, (list, set, frozenset)) or tool_name not in described:
        raise AgentRunException(
            f"{PREFLIGHT_SCHEMA_NOT_DISCLOSED}: run_tool('{tool_name}', ...) "
            f"was called before describe_tool('{tool_name}'). "
            f"Call describe_tool('{tool_name}') first to see the "
            f"parameter schema (name, type, default, description), "
            f"then call run_tool with informed arguments."
        )


class IBMiCLITools(Toolkit):
    """IBM i CLI toolkit for database introspection and SQL execution.

    All methods return an :class:`Envelope` — a ``dict[str, Any]``
    subclass whose ``__str__`` emits canonical JSON at the Agno wire
    boundary. Python callers access fields directly.
    """

    def __init__(
        self,
        *,
        tools_dir: str | None = None,
        system: str | None = None,
        toolsets: list[str] | None = None,
        enable_yaml_tools: bool = True,
        enable_pase: bool = False,
        **kwargs: Any,
    ) -> None:
        self.tools_dir = tools_dir
        # --system: explicit param > IBMI_SYSTEM env > None (CLI default).
        self.system = system or os.environ.get("IBMI_SYSTEM") or None
        # Construction-time scope is the **static-agent** path —
        # agents like ``system_health_cli`` pass a curated ``toolsets``
        # list at __init__ and share a single instance. Per-call
        # dynamic scope (builder-registered agents) comes from
        # ``run_context.dependencies`` via :meth:`_resolve_scope` and
        # overrides these instance defaults when present.
        self.toolsets: tuple[str, ...] = tuple(toolsets) if toolsets else ()
        allowed: set[str] = set()
        if self.toolsets:
            try:
                allowed.update(get_toolsets(*self.toolsets))
            except KeyError as exc:
                bad = exc.args[0] if exc.args else "?"
                raise ValueError(f"Unknown toolset: {bad!r}. Available: {sorted(list_toolsets())}") from exc
        self.allowed_tools: frozenset[str] = frozenset(allowed)
        # PASE shell execution — opt-in because ``sample.pase_call`` can
        # install packages, modify IFS, start/stop services, and run
        # arbitrary scripts. Unlike ``run_cl``, there is no verb
        # allowlist that cleanly separates reads from writes for PASE.
        self.enable_pase = enable_pase

        # NOTE: ``self.run_sql`` is intentionally NOT registered with the
        # toolkit. It remains defined on the class so internal callers and
        # tests can invoke it directly, but the LLM-facing surface uses
        # ``validate_and_run_sql`` exclusively — that path runs ``validate_sql``
        # first and is gated by ``requires_confirmation_tools``. Exposing
        # both would let the model bypass validation + confirmation by
        # picking the simpler entrypoint.
        tools: list[Any] = [
            self.run_cl,
            self.list_schemas,
            self.list_tables,
            self.list_columns,
            self.describe,
            self.validate_sql,
            self.discover_services,
            self.validate_and_run_sql,
        ]
        if enable_yaml_tools:
            tools.extend(
                [
                    self.describe_tool,
                    self.run_tool,
                    self.list_tools,
                ]
            )

        confirmation_tools: list[str] = ["validate_and_run_sql", "run_cl"]
        if self.enable_pase:
            tools.append(self.run_pase)
            confirmation_tools.append("run_pase")

        super().__init__(
            name="ibmi_cli",
            tools=tools,
            requires_confirmation_tools=confirmation_tools,
            **kwargs,
        )

        # Hard gate: run_tool must be preceded by describe_tool in the
        # same session. Agno fires pre_hook before the entrypoint;
        # raising AgentRunException from the hook produces a recoverable
        # tool failure the LLM can correct by calling describe_tool first.
        run_tool_fn = self.functions.get("run_tool")
        if run_tool_fn is not None:
            run_tool_fn.pre_hook = _require_schema_disclosed

    # ------------------------------------------------------------------
    # Internal: per-call scope resolution
    # ------------------------------------------------------------------

    def _resolve_scope(
        self,
        run_context: Any,
    ) -> tuple[tuple[str, ...], frozenset[str], tuple[dict[str, Any], ...]]:
        """Resolve per-call (toolsets, allowed_tools, extra_inventory).

        Precedence:

        1. **Builder-registered agents**: ``run_context.dependencies``
           carries ``ibmi_toolsets`` / ``ibmi_extra_tools`` /
           ``ibmi_extra_inventory`` keys — Agno copies these fresh
           from the agent's stored ``dependencies`` dict on every
           run, so LLM mutations can't leak across runs.
        2. **Static agents** (no ``run_context`` or no ibmi deps):
           fall back to ``self.toolsets`` / ``self.allowed_tools``
           from __init__.

        Returns a 3-tuple:

        - ``toolsets``: the tuple of curated toolset names in scope
        - ``allowed_tools``: the flat set of tool names the scope
          gate accepts (curated toolset contents + flat extras)
        - ``extra_inventory``: full per-tool metadata for extras
          (name, description, parameters) — used by ``list_tools``
          for the extras fallback
        """
        deps: dict[str, Any] = {}
        if run_context is not None:
            candidate = getattr(run_context, "dependencies", None)
            if isinstance(candidate, dict):
                deps = candidate

        has_ibmi_dep = any(key in deps for key in ("ibmi_toolsets", "ibmi_extra_tools", "ibmi_extra_inventory"))
        if not has_ibmi_dep:
            return self.toolsets, self.allowed_tools, ()

        raw_toolsets = deps.get("ibmi_toolsets") or []
        raw_extras = deps.get("ibmi_extra_tools") or []
        raw_inventory = deps.get("ibmi_extra_inventory") or []

        toolsets: tuple[str, ...] = tuple(str(t) for t in raw_toolsets if isinstance(t, str))
        inventory_entries: list[dict[str, Any]] = [dict(e) for e in raw_inventory if isinstance(e, dict)]
        extras: list[str] = [str(n) for n in raw_extras if isinstance(n, str)]
        # Inventory entries implicitly extend the flat extras list so
        # the scope gate and the inventory stay in sync.
        for entry in inventory_entries:
            name = entry.get("name")
            if isinstance(name, str) and name not in extras:
                extras.append(name)

        allowed: set[str] = set(extras)
        if toolsets:
            try:
                allowed.update(get_toolsets(*toolsets))
            except KeyError:
                # Malformed scope — let require_toolset_scope surface
                # it as PREFLIGHT_TOOL_NOT_IN_SCOPE at gate time.
                pass
        return toolsets, frozenset(allowed), tuple(inventory_entries)

    # ------------------------------------------------------------------
    # Internal: tools path + dispatcher
    # ------------------------------------------------------------------

    def _resolve_tools_path(self) -> str | None:
        """Resolve ``--tools <path>`` for CLI subcommands that need YAML lookup.

        Precedence: explicit ``tools_dir`` wins. Otherwise return a
        comma-separated path list that the CLI accepts natively —
        project tools first (where repo YAML lives), then user tools
        (where the agent builder writes new YAML at runtime). Both are
        optional; whichever exists contributes to the list.
        """
        if self.tools_dir:
            return self.tools_dir
        candidates: list[str] = []
        if PROJECT_TOOLS_DIR.is_dir():
            candidates.append(str(PROJECT_TOOLS_DIR))
        if USER_TOOLS_DIR.is_dir():
            candidates.append(str(USER_TOOLS_DIR))
        return ",".join(candidates) if candidates else None

    def _dispatch(self, spec: CommandSpec) -> Envelope:
        """Run the CLI subprocess for ``spec`` and normalize the response.

        Owns argv assembly, env scrubbing, elapsed-time tracking, one
        structured log line, and CLI envelope parsing into an
        :class:`Envelope`.
        """
        cmd: list[str] = [IBMI_CLI, *spec.argv, "--format", "json"]
        if self.system:
            cmd.extend(["--system", self.system])
        if spec.use_tools_path:
            tools_path = self._resolve_tools_path()
            if tools_path:
                cmd.extend(["--tools", tools_path])

        start = time.monotonic()
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=IBMI_CLI_TIMEOUT,
                shell=False,  # explicit: never spawn a shell
                env=_scrub_child_env(),
            )
        except FileNotFoundError:
            elapsed_ms = (time.monotonic() - start) * 1000
            self._log(spec, None, elapsed_ms, False, RUNTIME_CLI_NOT_FOUND, "error")
            return _error_envelope(
                spec.tool_name,
                RUNTIME_CLI_NOT_FOUND,
                f"CLI binary not found: {IBMI_CLI}",
                source="runtime",
                elapsed_ms=elapsed_ms,
            )
        except subprocess.TimeoutExpired:
            elapsed_ms = (time.monotonic() - start) * 1000
            self._log(spec, None, elapsed_ms, False, RUNTIME_CLI_TIMEOUT, "error")
            return _error_envelope(
                spec.tool_name,
                RUNTIME_CLI_TIMEOUT,
                f"Command timed out after {IBMI_CLI_TIMEOUT}s",
                source="runtime",
                elapsed_ms=elapsed_ms,
            )

        elapsed_ms = (time.monotonic() - start) * 1000
        envelope, parse_err = _parse_cli_envelope(
            result.stdout,
            result.stderr,
            result.returncode,
            spec.tool_name,
            elapsed_ms,
        )

        ok = bool(envelope.get("ok", False))
        err_obj = envelope.get("error")
        error_code: str | None = None
        if isinstance(err_obj, dict):
            code_val = err_obj.get("code")
            error_code = str(code_val) if code_val is not None else None
        self._log(
            spec,
            result.returncode,
            elapsed_ms,
            parse_err is None,
            error_code,
            "info" if ok else "warning",
        )
        return envelope

    def _log(
        self,
        spec: CommandSpec,
        exit_code: int | None,
        elapsed_ms: float,
        envelope_parsed: bool,
        error_code: str | None,
        level: str,
    ) -> None:
        """Structured log line per dispatch. Never logs raw SQL or params."""
        extra = {
            "ibmi_tool": spec.tool_name,
            "ibmi_subcommand": spec.argv[0] if spec.argv else "",
            "ibmi_argc": len(spec.argv),
            "ibmi_system": self.system,
            "ibmi_exit_code": exit_code,
            "ibmi_elapsed_ms": round(elapsed_ms, 2),
            "ibmi_envelope_parsed": envelope_parsed,
            "ibmi_error_code": error_code,
        }
        getattr(logger, level)("ibmi_cli.invoke", extra=extra)

    # ------------------------------------------------------------------
    # §G  Tool wrappers
    # ------------------------------------------------------------------

    def run_sql(self, statement: str) -> Envelope:
        """Execute a SQL statement against the IBM i system (read-only).

        NOT registered with the toolkit — see the ``__init__`` note.
        The LLM-facing surface is :meth:`validate_and_run_sql`, which
        runs ``validate_sql`` first and is gated by confirmation.
        Kept for internal callers and tests that need direct dispatch.

        Args:
            statement: The SQL statement to execute.

        Returns:
            Envelope with rows on success or a canonical error on
            failure.
        """
        return self._dispatch(
            CommandSpec(
                tool_name="run_sql",
                argv=("sql", statement, "--read-only"),
            )
        )

    def validate_and_run_sql(self, statement: str) -> Envelope:
        """Validate a SQL statement and execute it if valid (read-only).

        Runs :meth:`validate_sql` first. If validation fails, returns
        the validation envelope unchanged and skips execution. If it
        succeeds, dispatches the statement in read-only mode. Requires
        user confirmation. Two subprocess calls per invocation on the
        happy path; one on the failure path.

        Args:
            statement: The SQL statement to validate and execute.

        Returns:
            Envelope with rows on success, the validation error envelope
            if validation fails, or a canonical error on dispatch failure.
        """
        validation_env = self.validate_sql(statement)
        if not validation_env.get("ok", False):
            return validation_env

        return self._dispatch(
            CommandSpec(
                tool_name="run_sql",
                argv=("sql", statement, "--read-only"),
            )
        )

    def run_tool(
        self,
        tool_name: str,
        parameters: dict[str, Any] | str | None = None,
        run_context: Any = None,
    ) -> Envelope:
        """Execute a named YAML-defined tool.

        **You MUST call describe_tool(tool_name) first in the same session.**
        Calling run_tool before describe_tool for a given tool_name raises
        PREFLIGHT_SCHEMA_NOT_DISCLOSED. The workflow is:
        list_tools → describe_tool(name) → run_tool(name, parameters).

        Per-call scope is resolved from ``run_context.dependencies``
        (for builder-registered agents) with fallback to the
        construction-time ``toolsets`` scope (for static agents).

        Args:
            tool_name: Name of the YAML tool to run.
            parameters: Key-value pairs for the tool's parameters.
                Accepts either a native dict (preferred — e.g.
                ``{"limit": 10, "schema": "QSYS2"}``) or a JSON
                string (legacy). Defaults to ``None`` / no params.

        Returns:
            Envelope with the tool execution result on success or a
            canonical error on failure.
        """
        toolsets, allowed, _ = self._resolve_scope(run_context)
        scope_err = require_toolset_scope(tool_name, toolsets, allowed)
        if scope_err is not None:
            return scope_err.to_envelope("run_tool")

        params: dict[str, Any] = {}
        if parameters is None or parameters == "":
            params = {}
        elif isinstance(parameters, dict):
            params = parameters
        else:
            # Legacy JSON-string input: delegate to the existing parser.
            parsed, parse_err = parse_tool_parameters(parameters)
            if parse_err is not None:
                return parse_err.to_envelope("run_tool")
            params = parsed or {}

        argv: list[str] = ["tool", tool_name]
        for key, value in params.items():
            argv.extend([f"--{key.replace('_', '-')}", str(value)])

        return self._dispatch(
            CommandSpec(
                tool_name="run_tool",
                argv=tuple(argv),
                use_tools_path=True,
            )
        )

    def describe_tool(
        self,
        tool_name: str,
        run_context: Any = None,
    ) -> Envelope:
        """Return the parameter schema for a YAML-defined IBM i tool.

        **You MUST call this before calling run_tool for the same tool name.**
        run_tool enforces this via a pre-hook gate. The workflow is:

            1. list_tools(...)              # get available names
            2. describe_tool(name)          # get parameter schema
            3. run_tool(name, parameters)   # execute with informed arguments

        Internally wraps ``ibmi tools show <name>`` and returns the CLI
        envelope unchanged. The response's ``data`` field contains:
        ``{name, description, source, toolsets, readOnly, parameters, sql}``
        where ``parameters`` is a list of ``{name, type, default, description}``
        objects describing each argument run_tool expects.

        Args:
            tool_name: Name of the YAML tool to describe.

        Returns:
            Envelope with the tool's schema on success or a canonical
            error on failure.
        """
        toolsets, allowed, _ = self._resolve_scope(run_context)
        scope_err = require_toolset_scope(tool_name, toolsets, allowed)
        if scope_err is not None:
            return scope_err.to_envelope("describe_tool")

        envelope = self._dispatch(
            CommandSpec(
                tool_name="describe_tool",
                argv=("tools", "show", tool_name),
                use_tools_path=True,
            )
        )

        # Side effect: record successful disclosure so the run_tool
        # pre_hook gate can verify the schema was seen this session.
        # ``ibmi_described`` is a list (not a set) because session_state
        # is JSON-serialized to the DB on pause/resume, and sets aren't
        # JSON. Guarded so a missing/None run_context or session_state
        # is a safe no-op (direct Python tests construct without one).
        if envelope.get("ok") is True and run_context is not None:
            session_state = getattr(run_context, "session_state", None)
            if isinstance(session_state, dict):
                described = session_state.get("ibmi_described")
                if not isinstance(described, list):
                    described = []
                if tool_name not in described:
                    described.append(tool_name)
                session_state["ibmi_described"] = described

        return envelope

    def list_schemas(self, filter_pattern: str = "") -> Envelope:
        """List database schemas (optional SQL LIKE pattern).

        Args:
            filter_pattern: SQL LIKE pattern (OBJECT%) to filter schema names.
                Defaults to ``""`` (no filter).

        Returns:
            Envelope with the list of schemas on success or a canonical
            error on failure.
        """
        argv: tuple[str, ...] = ("schemas",)
        if filter_pattern:
            argv = ("schemas", "--filter", filter_pattern)
        return self._dispatch(CommandSpec(tool_name="list_schemas", argv=argv))

    def list_tables(self, schema: str) -> Envelope:
        """List tables in a database schema.

        Args:
            schema: The schema name to list tables for.

        Returns:
            Envelope with the list of tables on success or a canonical
            error on failure.
        """
        return self._dispatch(CommandSpec(tool_name="list_tables", argv=("tables", schema)))

    def list_columns(self, schema: str, table: str) -> Envelope:
        """List columns for a table.

        Args:
            schema: The schema name.
            table: The table name.

        Returns:
            Envelope with the list of columns on success or a canonical
            error on failure.
        """
        return self._dispatch(
            CommandSpec(
                tool_name="list_columns",
                argv=("columns", schema, table),
            )
        )

    def describe(
        self,
        object_name: str,
        object_type: str = "TABLE",
    ) -> Envelope:
        """Generate DDL for a database object.

        Args:
            object_name: Fully qualified name (SCHEMA.OBJECT).
            object_type: TABLE, VIEW, INDEX, PROCEDURE, ...
                Defaults to ``"TABLE"``.

        Returns:
            Envelope with the object's DDL on success or a canonical
            error on failure.
        """
        return self._dispatch(
            CommandSpec(
                tool_name="describe",
                argv=("describe", object_name, "--type", object_type),
            )
        )

    def validate_sql(self, statement: str) -> Envelope:
        """Validate a SQL statement without executing it.

        Args:
            statement: The SQL statement to validate.

        Returns:
            Envelope with validation results on success or a canonical
            error on failure.
        """
        return self._dispatch(
            CommandSpec(
                tool_name="validate_sql",
                argv=("validate", statement),
            )
        )

    def run_cl(self, command: str, *, read_only: bool = True) -> Envelope:
        """Execute an IBM i CL command via ``QSYS2.QCMDEXC``.

        Read-only by default — rejects CL verbs outside the inquiry
        allowlist (DSP/RTV/PRT/CHK) at the Python boundary. Requires
        user confirmation. QCMDEXC returns ``1`` on success; raw CL
        output goes to the joblog — QCMDEXC limitation, acceptable
        for R&D.

        Args:
            command: CL command text (e.g. ``"DSPSYSVAL SYSVAL(QMODEL)"``).
            read_only: If True, enforce the inquiry allowlist. Defaults
                to ``True``.

        Returns:
            Envelope with the command execution result on success or a
            canonical error on failure.
        """
        if read_only:
            err = require_inquiry_verb(command)
            if err is not None:
                return err.to_envelope("run_cl")
        # QCMDEXC is write-classified by the CLI gate; --no-read-only
        # is required. Python-side read-only is enforced above.
        return self._dispatch(
            CommandSpec(
                tool_name="run_cl",
                argv=("sql", qcmdexc_wrap(command), "--no-read-only"),
            )
        )

    def run_pase(self, pase_command: str) -> Envelope:
        """Execute a shell command in IBM i PASE via ``sample.pase_call``.

        WRITE operation — requires confirmation at the agent layer.
        Only exposed when constructed with ``enable_pase=True``.

        **Prerequisite:** the ``sample.pase_call`` UDTF must be
        installed on the target system. If missing, the underlying SQL
        call fails with a Db2 catalog error — surface that error to the
        user so they know to install the UDTF.

        **PASE has no PATH set**, so commands MUST use absolute paths
        (e.g. ``/QOpenSys/pkgs/bin/yum list installed``). Relative
        commands fail silently — rejected at the Python boundary.

        Args:
            pase_command: Full path to the PASE command. 1-5000 chars.
                Must begin with ``/``.

        Returns:
            Envelope with the PASE command output on success or a
            canonical error on failure.
        """
        pase_err = require_pase_enabled(self.enable_pase)
        if pase_err is not None:
            return pase_err.to_envelope("run_pase")

        trimmed = pase_command.strip()
        length_err = require_length_bounds(trimmed, min_len=1, max_len=5000)
        if length_err is not None:
            return length_err.to_envelope("run_pase")

        path_err = require_absolute_path(trimmed)
        if path_err is not None:
            return path_err.to_envelope("run_pase")

        # sample.pase_call is write-classified by the CLI gate because
        # it can mutate system state; ``--no-read-only`` is required.
        return self._dispatch(
            CommandSpec(
                tool_name="run_pase",
                argv=(
                    "sql",
                    pase_call_wrap(trimmed),
                    "--no-read-only",
                ),
            )
        )

    def discover_services(self, service_name_filter: str = "") -> Envelope:
        """Enumerate IBM i SQL Services via ``QSYS2.SERVICES_INFO``.

        Progressive disclosure primitive — agent-facing "grep" for IBM i
        capabilities without a hand-curated tool registry. Pure read.

        Args:
            service_name_filter: SQL LIKE pattern for ``SERVICE_NAME``
                (e.g., ``'SYSTEM_%'``). Defaults to ``""`` (no filter).

        Returns:
            Envelope with the list of SQL Services on success or a
            canonical error on failure.
        """
        query = services_info_query(service_name_filter or None)
        return self._dispatch(
            CommandSpec(
                tool_name="discover_services",
                argv=("sql", query, "--read-only"),
            )
        )

    def list_tools(
        self,
        tool_path: str | None = None,
        toolsets: list[str] | None = None,
        run_context: Any = None,
    ) -> Envelope:
        """List available YAML-defined IBM i tools.

        Sources (``tool_path`` and ``toolsets`` are mutually exclusive):

        - ``tool_path``: inspect a specific YAML file. Returns full
          inventory with names, descriptions, and parameter schemas.
        - ``toolsets``: enumerate tools in one or more named toolsets.

        When neither is given, the fallback resolves scope via
        :meth:`_resolve_scope`:

        - Curated toolsets (from ``run_context.dependencies`` or
          instance ``self.toolsets``) → enumerate each toolset's
          canonical tool list
        - Extras inventory (from
          ``run_context.dependencies['ibmi_extra_inventory']``) →
          flat list with description + parameter names
        - Empty → ``PREFLIGHT_NO_DISCOVERY_SOURCE``

        Args:
            tool_path: Path to a YAML tool file inside the workspace.
                Defaults to ``None``.
            toolsets: One or more toolset names to enumerate. Defaults
                to ``None`` (falls back to resolved scope).

        Returns:
            Envelope with ``data.source`` (``"file"``, ``"scope"``,
            or ``"extras"``) and ``data.tools`` on success or a
            canonical error on failure.
        """
        start = time.monotonic()

        if tool_path and toolsets:
            return PreflightError(
                code=PREFLIGHT_AMBIGUOUS_DISCOVERY,
                message="Provide tool_path or toolsets, not both.",
                details={
                    "tool_path": tool_path,
                    "toolsets": list(toolsets),
                },
            ).to_envelope(
                "list_tools",
                elapsed_ms=(time.monotonic() - start) * 1000,
            )

        if tool_path:
            return self._list_tools_from_file(tool_path, start=start)

        if toolsets is not None:
            return self._list_tools_from_scope(list(toolsets), start=start)

        resolved_toolsets, _allowed, extra_inventory = self._resolve_scope(run_context)

        if resolved_toolsets:
            return self._list_tools_from_scope(list(resolved_toolsets), start=start)

        if extra_inventory:
            inventory = sorted(
                (dict(entry) for entry in extra_inventory),
                key=lambda t: str(t.get("name", "")),
            )
            return _python_success_envelope(
                "list_tools",
                data={
                    "source": "extras",
                    "tools": inventory,
                },
                rows=len(inventory),
                elapsed_ms=(time.monotonic() - start) * 1000,
            )

        return PreflightError(
            code=PREFLIGHT_NO_DISCOVERY_SOURCE,
            message=("list_tools requires tool_path or toolsets (or an instance-level scope)."),
        ).to_envelope(
            "list_tools",
            elapsed_ms=(time.monotonic() - start) * 1000,
        )

    def _list_tools_from_file(
        self,
        tool_path: str,
        *,
        start: float,
    ) -> Envelope:
        """Inspect a YAML tool file inside the workspace."""
        target = Path(tool_path).resolve()
        cwd = Path.cwd().resolve()

        def _env(err: PreflightError) -> Envelope:
            return err.to_envelope(
                "list_tools",
                elapsed_ms=(time.monotonic() - start) * 1000,
            )

        path_err = require_workspace_path(target, cwd)
        if path_err is not None:
            return _env(path_err)

        if not target.is_file():
            return _env(
                PreflightError(
                    code=PREFLIGHT_FILE_NOT_FOUND,
                    message=f"File not found: {tool_path}",
                )
            )

        try:
            with target.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
        except yaml.YAMLError as exc:
            return _env(
                PreflightError(
                    code=PREFLIGHT_INVALID_YAML,
                    message=f"Invalid YAML: {exc}",
                    details={"file": str(target)},
                )
            )

        tools_section = data.get("tools") or {}
        if not isinstance(tools_section, dict):
            return _env(
                PreflightError(
                    code=PREFLIGHT_INVALID_YAML,
                    message="tools section must be a mapping",
                    details={"file": str(target)},
                )
            )

        inventory: list[dict[str, Any]] = []
        for name, body in tools_section.items():
            if not isinstance(body, dict):
                continue
            params_obj = body.get("parameters") or {}
            if isinstance(params_obj, dict):
                param_names = list(params_obj.keys())
            elif isinstance(params_obj, list):
                param_names = [str(p) for p in params_obj]
            else:
                param_names = []
            inventory.append(
                {
                    "name": str(body.get("name", name)),
                    "description": body.get("description", ""),
                    "parameters": param_names,
                }
            )

        return _python_success_envelope(
            "list_tools",
            data={
                "source": "file",
                "file": str(target),
                "tools": inventory,
            },
            rows=len(inventory),
            elapsed_ms=(time.monotonic() - start) * 1000,
        )

    def _list_tools_from_scope(
        self,
        toolsets: list[str],
        *,
        start: float,
    ) -> Envelope:
        """Enumerate tools from one or more named toolsets."""
        try:
            inventory = get_toolsets_inventory(*toolsets)
        except KeyError as exc:
            bad = exc.args[0] if exc.args else "?"
            return PreflightError(
                code=PREFLIGHT_UNKNOWN_TOOLSET,
                message=f"Unknown toolset: {bad!r}",
                details={
                    "requested": list(toolsets),
                    "available": sorted(list_toolsets()),
                },
            ).to_envelope(
                "list_tools",
                elapsed_ms=(time.monotonic() - start) * 1000,
            )

        inventory.sort(key=lambda t: t["name"])

        return _python_success_envelope(
            "list_tools",
            data={
                "source": "scope",
                "toolsets": list(toolsets),
                "tools": inventory,
            },
            rows=len(inventory),
            elapsed_ms=(time.monotonic() - start) * 1000,
        )
