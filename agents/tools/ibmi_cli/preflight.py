"""Preflight validators — pure functions returning ``PreflightError | None``.

Each ``require_*`` function checks one invariant without touching a
subprocess. The call site converts a non-None return into an
:class:`Envelope` via :meth:`PreflightError.to_envelope`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .envelope import (
    PREFLIGHT_INVALID_JSON,
    PREFLIGHT_PASE_DISABLED,
    PREFLIGHT_PASE_LENGTH,
    PREFLIGHT_PASE_RELATIVE_PATH,
    PREFLIGHT_PATH_OUTSIDE_WORKSPACE,
    PREFLIGHT_READ_ONLY_VIOLATION,
    PREFLIGHT_TOOL_NOT_IN_SCOPE,
    PreflightError,
)

_CL_INQUIRY_PREFIXES = ("DSP", "RTV", "PRT", "CHK")


def _is_inquiry_cl(command: str) -> bool:
    token = command.strip().upper().split(None, 1)[0] if command.strip() else ""
    return any(token.startswith(pref) for pref in _CL_INQUIRY_PREFIXES)


def require_toolset_scope(
    tool_name: str,
    toolsets: tuple[str, ...],
    allowed: frozenset[str],
) -> PreflightError | None:
    # Unrestricted legacy default: no toolsets AND no flat allowlist.
    if not toolsets and not allowed:
        return None
    if tool_name in allowed:
        return None
    return PreflightError(
        code=PREFLIGHT_TOOL_NOT_IN_SCOPE,
        message=(
            f"Tool '{tool_name}' is not in the configured scope "
            f"(toolsets={list(toolsets)}). Call list_tools() to "
            f"see the allowed set."
        ),
        details={
            "toolsets": list(toolsets),
            "allowed_tools": sorted(allowed),
        },
    )


def require_inquiry_verb(command: str) -> PreflightError | None:
    if _is_inquiry_cl(command):
        return None
    return PreflightError(
        code=PREFLIGHT_READ_ONLY_VIOLATION,
        message=(
            "Read-only mode: CL command does not match inquiry verb "
            "allowlist. Set read_only=False to override."
        ),
        details={"command": command},
    )


def require_pase_enabled(enabled: bool) -> PreflightError | None:
    if enabled:
        return None
    return PreflightError(
        code=PREFLIGHT_PASE_DISABLED,
        message=(
            "run_pase is disabled on this IBMiCLITools instance. "
            "Construct with enable_pase=True to allow PASE shell execution."
        ),
    )


def require_length_bounds(
    value: str,
    *,
    min_len: int,
    max_len: int,
) -> PreflightError | None:
    if min_len <= len(value) <= max_len:
        return None
    return PreflightError(
        code=PREFLIGHT_PASE_LENGTH,
        message=f"pase_command must be {min_len}-{max_len} characters.",
    )


def require_absolute_path(value: str) -> PreflightError | None:
    if value.startswith("/"):
        return None
    return PreflightError(
        code=PREFLIGHT_PASE_RELATIVE_PATH,
        message=(
            "pase_command must be an absolute path — PASE has no "
            "PATH set, so relative commands silently fail."
        ),
        details={
            "hint": (
                "Use full paths like '/QOpenSys/pkgs/bin/yum "
                "list installed' or '/QOpenSys/usr/bin/ls "
                "/QOpenSys/pkgs/bin'."
            ),
        },
    )


def require_workspace_path(path: Path, cwd: Path) -> PreflightError | None:
    try:
        path.relative_to(cwd)
    except ValueError:
        return PreflightError(
            code=PREFLIGHT_PATH_OUTSIDE_WORKSPACE,
            message=f"Path outside workspace: {path}",
        )
    return None


def parse_tool_parameters(
    parameters: str,
) -> tuple[dict[str, Any] | None, PreflightError | None]:
    """Parse ``run_tool`` parameters JSON. Returns ``(params, error)``."""
    if not parameters:
        return {}, None
    try:
        parsed = json.loads(parameters)
    except json.JSONDecodeError:
        return None, PreflightError(
            code=PREFLIGHT_INVALID_JSON,
            message=f"Invalid parameters JSON: {parameters}",
        )
    if not isinstance(parsed, dict):
        return None, PreflightError(
            code=PREFLIGHT_INVALID_JSON,
            message="Parameters must be a JSON object (mapping).",
        )
    return parsed, None
