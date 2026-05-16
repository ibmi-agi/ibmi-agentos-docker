"""Interactive CLI for running the template's IBM i agents from the terminal.

Usage:
    uv run python cli.py                       # REPL with default agent
    uv run python cli.py --agent text2sql      # REPL with a specific agent
    uv run python cli.py --agent text2sql \\
        --prompt "list schemas containing QSYS" # one-shot, then exit
    uv run python cli.py --list                # list available agents and exit

The CLI overrides ``MCP_URL`` to ``http://localhost:3010/mcp`` so it can
reach the docker-published port from the host (compose's default is the
internal docker hostname).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import uuid
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv

load_dotenv()
# This CLI runs outside Docker, so override MCP_URL to the host-exposed
# port. Must happen before any agents.* imports so the URL is picked up.
os.environ["MCP_URL"] = os.environ.get("MCP_URL_CLI", "http://localhost:3010/mcp")


@dataclass(frozen=True)
class AgentSpec:
    module: str
    attr: str
    label: str


AGENTS: dict[str, AgentSpec] = {
    "text2sql": AgentSpec("agents.text2sql", "text2sql_agent", "IBM i Text-to-SQL Agent"),
    "sql-service-guide": AgentSpec(
        "agents.sql_service_guide",
        "sql_service_guide_agent",
        "IBM i SQL Service Guide",
    ),
    "system-health": AgentSpec(
        "agents.system_health",
        "system_health_agent",
        "IBM i System Health Agent",
    ),
}

DEFAULT_AGENT = "text2sql"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run IBM i agents interactively from the terminal.")
    parser.add_argument(
        "-a",
        "--agent",
        default=DEFAULT_AGENT,
        choices=sorted(AGENTS.keys()),
        help="Agent key to start with.",
    )
    parser.add_argument(
        "-p",
        "--prompt",
        help="Optional one-shot prompt. If set, runs once and exits.",
    )
    parser.add_argument("--list", action="store_true", help="List available agents and exit.")
    return parser.parse_args()


def list_agents() -> None:
    print("Available agents:")
    for key in sorted(AGENTS.keys()):
        print(f"  - {key:<20} {AGENTS[key].label}")


def load_agent(agent_key: str) -> Any:
    import importlib

    spec = AGENTS[agent_key]
    module = importlib.import_module(spec.module)
    return getattr(module, spec.attr)


def print_help() -> None:
    print("Commands:")
    print("  /agents           List available agents")
    print("  /use <agent-key>  Switch active agent")
    print("  /help             Show this help")
    print("  /quit             Exit")


async def run_once(agent: Any, prompt: str, session_id: str) -> None:
    """Run a single prompt against an agent with proper async MCP lifecycle."""
    await agent.aprint_response(prompt, stream=True, session_id=session_id)


async def run_repl(start_agent_key: str) -> None:
    active_key = start_agent_key
    active_agent = load_agent(active_key)
    session_id = str(uuid.uuid4())

    print(f"Interactive Agent CLI (active: {active_key})")
    print("Type /help for commands.")

    loop = asyncio.get_running_loop()

    while True:
        try:
            prompt = await loop.run_in_executor(None, lambda: input(f"[{active_key}] > ").strip())
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if not prompt:
            continue
        if prompt == "/quit":
            print("Exiting.")
            break
        if prompt == "/help":
            print_help()
            continue
        if prompt == "/agents":
            list_agents()
            continue
        if prompt.startswith("/use "):
            next_key = prompt.split(maxsplit=1)[1].strip()
            if next_key not in AGENTS:
                print(f"Unknown agent '{next_key}'. Use /agents to see valid keys.")
                continue
            active_key = next_key
            active_agent = load_agent(active_key)
            session_id = str(uuid.uuid4())
            print(f"Switched to: {active_key}")
            continue

        await run_once(active_agent, prompt, session_id)


def main() -> None:
    args = parse_args()

    if args.list:
        list_agents()
        return

    agent = load_agent(args.agent)
    if args.prompt:
        session_id = str(uuid.uuid4())
        asyncio.run(run_once(agent, args.prompt, session_id))
        return

    asyncio.run(run_repl(args.agent))


if __name__ == "__main__":
    main()
