"""IBM i agents — registered in ``app/main.py``."""

from __future__ import annotations

from typing import Any

# Defaults applied to every agent so they share consistent session/memory
# behavior. Override per agent by passing the kwargs explicitly.
AGENT_DEFAULTS: dict[str, Any] = dict(
    markdown=True,
    add_datetime_to_context=True,
    search_session_history=True,
    num_history_sessions=2,
    add_history_to_context=True,
    num_history_runs=3,
    read_chat_history=True,
    read_tool_call_history=True,
    retries=3,
    enable_agentic_memory=True,
)
