"""Envelope types, error codes, and failure-envelope factories.

Every tool returns an :class:`Envelope` — a ``dict[str, Any]`` subclass
whose ``__str__`` emits canonical JSON at the Agno wire boundary.
Every failure path produces the same nested shape:
``{ok: False, command, error: {code, message, details?}, ibmi}``.
``ibmi.source`` is one of ``"preflight"``, ``"cli"``, ``"runtime"``, or ``"python"``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

# Python-synthesized error codes. CLI-origin codes (SQL_ERROR, AUTH_ERROR,
# etc.) pass through unchanged on the envelope. The LLM can branch on the
# prefix: PREFLIGHT_* = Python-side mistake; RUNTIME_* = subprocess itself
# failed; ENVELOPE_* = CLI spoke but in a malformed shape.

PREFLIGHT_TOOL_NOT_IN_SCOPE = "PREFLIGHT_TOOL_NOT_IN_SCOPE"
PREFLIGHT_INVALID_JSON = "PREFLIGHT_INVALID_JSON"
PREFLIGHT_READ_ONLY_VIOLATION = "PREFLIGHT_READ_ONLY_VIOLATION"
PREFLIGHT_PASE_DISABLED = "PREFLIGHT_PASE_DISABLED"
PREFLIGHT_PASE_RELATIVE_PATH = "PREFLIGHT_PASE_RELATIVE_PATH"
PREFLIGHT_PASE_LENGTH = "PREFLIGHT_PASE_LENGTH"
PREFLIGHT_PATH_OUTSIDE_WORKSPACE = "PREFLIGHT_PATH_OUTSIDE_WORKSPACE"
PREFLIGHT_NO_DISCOVERY_SOURCE = "PREFLIGHT_NO_DISCOVERY_SOURCE"
PREFLIGHT_AMBIGUOUS_DISCOVERY = "PREFLIGHT_AMBIGUOUS_DISCOVERY"
PREFLIGHT_UNKNOWN_TOOLSET = "PREFLIGHT_UNKNOWN_TOOLSET"
PREFLIGHT_FILE_NOT_FOUND = "PREFLIGHT_FILE_NOT_FOUND"
PREFLIGHT_INVALID_YAML = "PREFLIGHT_INVALID_YAML"
PREFLIGHT_SCHEMA_NOT_DISCLOSED = "PREFLIGHT_SCHEMA_NOT_DISCLOSED"

RUNTIME_CLI_NOT_FOUND = "RUNTIME_CLI_NOT_FOUND"
RUNTIME_CLI_TIMEOUT = "RUNTIME_CLI_TIMEOUT"
RUNTIME_EXIT_CODE = "RUNTIME_EXIT_CODE"

ENVELOPE_PARSE_FAILURE = "ENVELOPE_PARSE_FAILURE"
ENVELOPE_MISSING_OK = "ENVELOPE_MISSING_OK"


class Envelope(dict):
    """Dict subclass that stringifies to canonical JSON.

    Agno calls ``str(result)`` at ``models/base.py:2186``, which invokes
    this ``__str__`` override and emits canonical JSON. Python callers
    get native dict access (``env["ok"]``, ``env["data"]``).
    """

    __slots__ = ()

    def __str__(self) -> str:
        return json.dumps(self, ensure_ascii=False, default=str)


def _error_envelope(
    command: str,
    code: str,
    message: str,
    *,
    source: str,
    elapsed_ms: float = 0.0,
    details: Mapping[str, Any] | None = None,
) -> Envelope:
    """Build a canonical failure envelope (source: preflight/runtime/cli)."""
    error_obj: dict[str, Any] = {"code": code, "message": message}
    if details:
        error_obj["details"] = dict(details)
    return Envelope(
        {
            "ok": False,
            "command": command,
            "error": error_obj,
            "ibmi": {
                "tool": command,
                "elapsed_ms": round(elapsed_ms, 2),
                "source": source,
            },
        }
    )


def _python_success_envelope(
    command: str,
    data: Any,
    *,
    rows: int,
    elapsed_ms: float,
) -> Envelope:
    """Build a success envelope for Python-only code paths (no subprocess)."""
    return Envelope(
        {
            "ok": True,
            "command": command,
            "data": data,
            "meta": {"rows": rows},
            "ibmi": {
                "tool": command,
                "elapsed_ms": round(elapsed_ms, 2),
                "source": "python",
            },
        }
    )


@dataclass(frozen=True)
class PreflightError:
    """Validator return value — converted to an Envelope at the call site."""

    code: str
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_envelope(self, command: str, *, elapsed_ms: float = 0.0) -> Envelope:
        return _error_envelope(
            command,
            self.code,
            self.message,
            source="preflight",
            elapsed_ms=elapsed_ms,
            details=self.details,
        )
