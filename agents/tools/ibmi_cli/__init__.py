"""IBM i CLI toolkit — wraps the ``ibmi`` binary for DB and CL interaction.

SECURITY: SQL literals are escaped by doubling single quotes (Db2 rule);
f-string SQL is prohibited. Subprocess calls are list-of-args with
``shell`` disabled. ``list_tools`` refuses paths outside the workspace.

Every tool returns an :class:`Envelope` — a ``dict[str, Any]`` subclass
that stringifies to canonical JSON at the Agno wire boundary. Every
failure path produces the same nested shape:
``{ok: False, command, error: {code, message, details?}, ibmi}``.
``ibmi.source`` is one of ``"preflight"``, ``"cli"``, ``"runtime"``, or ``"python"``.

Package layout (one concern per submodule):

- :mod:`._env` — child-process env scrubbing (§A)
- :mod:`.envelope` — Envelope, PreflightError, error codes, factories (§B)
- :mod:`.sql` — pure SQL builders (§C)
- :mod:`.preflight` — pure validators returning ``PreflightError | None`` (§D)
- :mod:`.dispatch` — CommandSpec + CLI envelope parser (§E)
- :mod:`.toolkit` — :class:`IBMiCLITools` Agno Toolkit class (§F + §G)
"""

from __future__ import annotations

# --- Environment (§A) ------------------------------------------------
from ._env import _scrub_child_env

# --- Dispatch primitives (§E) ----------------------------------------
from .dispatch import CommandSpec

# --- Envelope types + error codes (§B) -------------------------------
from .envelope import (
    ENVELOPE_MISSING_OK,
    ENVELOPE_PARSE_FAILURE,
    PREFLIGHT_AMBIGUOUS_DISCOVERY,
    PREFLIGHT_FILE_NOT_FOUND,
    PREFLIGHT_INVALID_JSON,
    PREFLIGHT_INVALID_YAML,
    PREFLIGHT_NO_DISCOVERY_SOURCE,
    PREFLIGHT_PASE_DISABLED,
    PREFLIGHT_PASE_LENGTH,
    PREFLIGHT_PASE_RELATIVE_PATH,
    PREFLIGHT_PATH_OUTSIDE_WORKSPACE,
    PREFLIGHT_READ_ONLY_VIOLATION,
    PREFLIGHT_SCHEMA_NOT_DISCLOSED,
    PREFLIGHT_TOOL_NOT_IN_SCOPE,
    PREFLIGHT_UNKNOWN_TOOLSET,
    RUNTIME_CLI_NOT_FOUND,
    RUNTIME_CLI_TIMEOUT,
    RUNTIME_EXIT_CODE,
    Envelope,
    PreflightError,
)

# --- SQL builders (§C) ------------------------------------------------
from .sql import (
    _escape_sql_literal,
    pase_call_wrap,
    qcmdexc_wrap,
    services_info_query,
)

# --- Toolkit class (§F + §G) -----------------------------------------
from .toolkit import IBMiCLITools

__all__ = [
    # Toolkit — the primary export, used by all production consumers
    "IBMiCLITools",
    # Envelope types
    "Envelope",
    "CommandSpec",
    "PreflightError",
    # Env helper — imported by tests
    "_scrub_child_env",
    # SQL builders — pure functions, imported by tests
    "_escape_sql_literal",
    "qcmdexc_wrap",
    "pase_call_wrap",
    "services_info_query",
    # Error codes — imported by tests + referenced internally
    "ENVELOPE_MISSING_OK",
    "ENVELOPE_PARSE_FAILURE",
    "PREFLIGHT_AMBIGUOUS_DISCOVERY",
    "PREFLIGHT_FILE_NOT_FOUND",
    "PREFLIGHT_INVALID_JSON",
    "PREFLIGHT_INVALID_YAML",
    "PREFLIGHT_NO_DISCOVERY_SOURCE",
    "PREFLIGHT_PASE_DISABLED",
    "PREFLIGHT_PASE_LENGTH",
    "PREFLIGHT_PASE_RELATIVE_PATH",
    "PREFLIGHT_PATH_OUTSIDE_WORKSPACE",
    "PREFLIGHT_READ_ONLY_VIOLATION",
    "PREFLIGHT_SCHEMA_NOT_DISCLOSED",
    "PREFLIGHT_TOOL_NOT_IN_SCOPE",
    "PREFLIGHT_UNKNOWN_TOOLSET",
    "RUNTIME_CLI_NOT_FOUND",
    "RUNTIME_CLI_TIMEOUT",
    "RUNTIME_EXIT_CODE",
]
