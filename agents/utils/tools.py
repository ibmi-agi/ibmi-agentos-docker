"""
IBM i Agent Tool Definitions — loaded from generated tools/toolsets.json

Single source of truth: YAML files in tools/ define tools and toolsets.
Run `python parse_mcp_tools.py` to regenerate tools/toolsets.json after
editing any YAML file.

Usage:
    from agents.utils.tools import get_toolset, get_toolsets

    # Single toolset
    MCPTools(include_tools=get_toolset("performance"))

    # Combine multiple toolsets (deduplicated, order-preserving)
    MCPTools(include_tools=get_toolsets("security_vulnerability_assessment", "security_audit"))
"""

import json
from pathlib import Path
from typing import Any, NotRequired, TypedDict


class ToolInventoryEntry(TypedDict):
    """A tool entry enriched with description metadata."""

    name: str
    description: str


class _ToolsetEntry(TypedDict):
    """Shape of a single toolset entry in ``tools/toolsets.json``.

    Mirrors the structure produced by ``parse_mcp_tools.py``: every entry
    has ``tools`` and ``source``; metadata fields are optional.
    """

    tools: list[str]
    source: str
    title: NotRequired[str]
    description: NotRequired[str]
    tool_metadata: NotRequired[dict[str, dict[str, Any]]]


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_TOOLSETS_FILE = _PROJECT_ROOT / "tools" / "toolsets.json"

try:
    _TOOLSETS: dict[str, _ToolsetEntry] = json.loads(_TOOLSETS_FILE.read_text())
except FileNotFoundError as exc:
    raise RuntimeError(
        f"Toolsets manifest not found at {_TOOLSETS_FILE}. "
        "Run `uv run python parse_mcp_tools.py` to generate it from the "
        "YAML files in tools/."
    ) from exc


def get_toolset(name: str) -> list[str]:
    """Get tool names for a toolset. Raises KeyError if not found."""
    return list(_TOOLSETS[name]["tools"])


def get_toolset_inventory(name: str) -> list[ToolInventoryEntry]:
    """Get tool entries (name + description) for a toolset.

    Reads descriptions from ``tool_metadata`` in ``toolsets.json``. Falls
    back to an empty string when a tool has no recorded description.
    Raises ``KeyError`` if the toolset is not found.
    """
    toolset = _TOOLSETS[name]
    metadata = toolset.get("tool_metadata", {})
    return [
        ToolInventoryEntry(
            name=tool,
            description=metadata.get(tool, {}).get("description", ""),
        )
        for tool in toolset["tools"]
    ]


def get_toolsets(*names: str) -> list[str]:
    """Combine multiple toolsets into a single deduplicated tool list."""
    seen = set()
    result = []
    for name in names:
        for tool in get_toolset(name):
            if tool not in seen:
                seen.add(tool)
                result.append(tool)
    return result


def get_toolsets_inventory(*names: str) -> list[ToolInventoryEntry]:
    """Combine multiple toolsets into a single deduplicated inventory.

    Deduplication is by tool name (first occurrence wins), preserving
    input order across toolsets. Mirrors ``get_toolsets`` semantics.
    """
    seen: set[str] = set()
    result: list[ToolInventoryEntry] = []
    for name in names:
        for entry in get_toolset_inventory(name):
            if entry["name"] not in seen:
                seen.add(entry["name"])
                result.append(entry)
    return result


def list_toolsets() -> list[str]:
    """Return all available toolset names."""
    return list(_TOOLSETS.keys())
