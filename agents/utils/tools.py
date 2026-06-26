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
from typing import List

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_TOOLSETS_FILE = _PROJECT_ROOT / "tools" / "toolsets.json"
_TOOLSETS: dict = json.loads(_TOOLSETS_FILE.read_text())


def get_toolset(name: str) -> List[str]:
    """Get tool names for a toolset. Raises KeyError if not found."""
    return list(_TOOLSETS[name]["tools"])


def get_toolsets(*names: str) -> List[str]:
    """Combine multiple toolsets into a single deduplicated tool list."""
    seen = set()
    result = []
    for name in names:
        for tool in get_toolset(name):
            if tool not in seen:
                seen.add(tool)
                result.append(tool)
    return result


def list_toolsets() -> List[str]:
    """Return all available toolset names."""
    return list(_TOOLSETS.keys())
