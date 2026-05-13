"""CLI invocation contract + envelope parser.

:class:`CommandSpec` captures the invariants of one ``ibmi`` CLI call
(tool name, argv, whether the ``--tools`` flag is needed).
:func:`_parse_cli_envelope` turns raw stdout/stderr/returncode into
an :class:`Envelope`, trusting the CLI's own ``ok`` field when present
and synthesizing a runtime/envelope error only when the CLI produced
nothing parseable.

The ``subprocess.run`` call itself lives on the Toolkit class
(:meth:`IBMiCLITools._dispatch`) because it needs instance state like
``self.system`` and ``self._resolve_tools_path()``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from .envelope import (
    ENVELOPE_MISSING_OK,
    ENVELOPE_PARSE_FAILURE,
    RUNTIME_EXIT_CODE,
    Envelope,
    _error_envelope,
)

_EXIT_SUCCESS = 0


@dataclass(frozen=True)
class CommandSpec:
    """The invariants of one ``ibmi`` CLI invocation."""

    tool_name: str
    argv: tuple[str, ...]
    use_tools_path: bool = False


def _parse_cli_envelope(
    stdout: str,
    stderr: str,
    returncode: int,
    tool_name: str,
    elapsed_ms: float,
) -> tuple[Envelope, str | None]:
    """Parse CLI stdout into an Envelope, trust its ``ok`` field.

    Returns ``(envelope, parse_error_code_or_None)``. The CLI emits an
    envelope on both success and failure — we trust stdout when it
    contains one and only synthesize a runtime/envelope error when the
    CLI produced nothing parseable.
    """
    stripped = stdout.strip()

    if not stripped:
        if returncode == _EXIT_SUCCESS:
            return (
                Envelope(
                    {
                        "ok": True,
                        "command": tool_name,
                        "data": None,
                        "meta": {"rows": 0},
                        "ibmi": {
                            "tool": tool_name,
                            "elapsed_ms": round(elapsed_ms, 2),
                            "source": "cli",
                        },
                    }
                ),
                None,
            )
        return (
            _error_envelope(
                tool_name,
                RUNTIME_EXIT_CODE,
                stderr.strip() or f"CLI exited with code {returncode} and no output",
                source="runtime",
                elapsed_ms=elapsed_ms,
                details={"exit_code": returncode},
            ),
            RUNTIME_EXIT_CODE,
        )

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return (
            _error_envelope(
                tool_name,
                ENVELOPE_PARSE_FAILURE,
                "CLI output was not valid JSON",
                source="runtime",
                elapsed_ms=elapsed_ms,
                details={
                    "stdout": stripped[:500],
                    "stderr": stderr.strip()[:500],
                },
            ),
            ENVELOPE_PARSE_FAILURE,
        )

    if not isinstance(parsed, dict):
        return (
            _error_envelope(
                tool_name,
                ENVELOPE_PARSE_FAILURE,
                "CLI output was not a JSON object",
                source="runtime",
                elapsed_ms=elapsed_ms,
                details={"stdout": stripped[:500]},
            ),
            ENVELOPE_PARSE_FAILURE,
        )

    if "ok" not in parsed:
        return (
            _error_envelope(
                tool_name,
                ENVELOPE_MISSING_OK,
                "CLI envelope missing 'ok' field",
                source="runtime",
                elapsed_ms=elapsed_ms,
                details={"stdout": stripped[:500]},
            ),
            ENVELOPE_MISSING_OK,
        )

    # Merge IBMi metadata without disturbing CLI-native fields.
    parsed["ibmi"] = {
        "tool": tool_name,
        "elapsed_ms": round(elapsed_ms, 2),
        "source": "cli",
    }
    return Envelope(parsed), None
