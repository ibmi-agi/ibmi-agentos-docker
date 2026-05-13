"""
Connection Admin CLI
====================

Lightweight CLI for managing IBM i system connections via the /auth/connections endpoints.

Usage::

    uv run connections list
    uv run connections create --name "Production" --host ibmi.example.com --user MYUSER --default
    uv run connections test <connection-id>
    uv run connections set-default <connection-id>
    uv run connections delete <connection-id>

Configuration (env vars or .env file)::

    AGENTOS_URL=http://localhost:8000    # API base URL
    AUTH_MASTER_KEY=ixr_...            # Admin API key
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from os import getenv

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

load_dotenv()

console = Console()
err = Console(stderr=True)


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------


def _client():  # type: ignore[no-untyped-def]
    import httpx

    base_url = getenv("AGENTOS_URL", "http://localhost:8000")
    api_key = getenv("AUTH_MASTER_KEY", "")
    if not api_key:
        err.print("[red]AUTH_MASTER_KEY not set. Export it or add to .env[/red]")
        sys.exit(1)
    return httpx.Client(
        base_url=base_url,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=15,
    )


def _handle_error(resp) -> None:  # type: ignore[no-untyped-def]
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        err.print(f"[red]Error {resp.status_code}:[/red] {detail}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------


def _ts(val: str | None) -> str:
    if not val:
        return "-"
    return val[:16].replace("T", " ")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_list(args: argparse.Namespace) -> None:
    """List all connections for the authenticated API key."""
    with _client() as c:
        resp = c.get("/auth/connections")
    _handle_error(resp)
    connections = resp.json()

    if not connections:
        console.print("[dim]No connections found.[/dim]")
        return

    if args.json:
        console.print_json(json.dumps(connections, default=str))
        return

    t = Table(title="IBM i Connections")
    t.add_column("ID", style="dim", max_width=36)
    t.add_column("Name", style="cyan")
    t.add_column("Host", style="green")
    t.add_column("Port", style="dim")
    t.add_column("User")
    t.add_column("Default", style="bold")
    t.add_column("Active", style="bold")
    t.add_column("Last Connected", style="dim", max_width=16)

    for c in connections:
        default = "[green]yes[/green]" if c.get("is_default") else "-"
        active = "[green]yes[/green]" if c.get("is_active") else "[red]no[/red]"
        t.add_row(
            str(c["id"]),
            c["name"],
            c["host"],
            str(c.get("port", 8076)),
            c.get("ibmi_user", "***"),
            default,
            active,
            _ts(c.get("last_connected")),
        )

    console.print(t)
    console.print(f"[dim]{len(connections)} connection(s)[/dim]")


def cmd_create(args: argparse.Namespace) -> None:
    """Register a new IBM i connection."""
    password = args.password
    if not password:
        password = getpass.getpass(f"Password for {args.user}@{args.host}: ")
        if not password:
            err.print("[red]Password is required[/red]")
            sys.exit(1)

    body: dict[str, object] = {
        "name": args.name,
        "host": args.host,
        "port": args.port,
        "user": args.user,
        "password": password,
        "is_default": args.default,
    }

    with _client() as c:
        resp = c.post("/auth/connections", json=body)
    _handle_error(resp)
    data = resp.json()

    if args.json:
        console.print_json(json.dumps(data, default=str))
        return

    default_label = (
        " [bold green](default)[/bold green]" if data.get("is_default") else ""
    )
    console.print(
        Panel(
            f"[bold cyan]{data['name']}[/bold cyan] — {data['host']}:{data.get('port', 8076)}{default_label}",
            title="Connection Created",
            border_style="green",
        )
    )
    console.print(f"  [dim]ID:[/dim]   {data['id']}")
    console.print(f"  [dim]User:[/dim] {data.get('ibmi_user', '***')}")
    console.print()
    console.print("[dim]Test with:[/dim] uv run connections test " + str(data["id"]))


def cmd_get(args: argparse.Namespace) -> None:
    """Get details of a single connection."""
    with _client() as c:
        resp = c.get(f"/auth/connections/{args.connection_id}")
    _handle_error(resp)
    data = resp.json()

    if args.json:
        console.print_json(json.dumps(data, default=str))
        return

    default = "[green]yes[/green]" if data.get("is_default") else "no"
    active = "[green]active[/green]" if data.get("is_active") else "[red]inactive[/red]"
    console.print(f"  [dim]ID:[/dim]             {data['id']}")
    console.print(f"  [dim]Name:[/dim]           {data['name']}")
    console.print(
        f"  [dim]Host:[/dim]           {data['host']}:{data.get('port', 8076)}"
    )
    console.print(f"  [dim]User:[/dim]           {data.get('ibmi_user', '***')}")
    console.print(f"  [dim]Default:[/dim]        {default}")
    console.print(f"  [dim]Status:[/dim]         {active}")
    console.print(f"  [dim]Created:[/dim]        {_ts(data.get('created_at'))}")
    console.print(f"  [dim]Last Connected:[/dim] {_ts(data.get('last_connected'))}")


def cmd_test(args: argparse.Namespace) -> None:
    """Test a connection by attempting MCP server authentication."""
    console.print(f"Testing connection {args.connection_id}...")

    with _client() as c:
        resp = c.post(f"/auth/connections/{args.connection_id}/test")
    _handle_error(resp)
    data = resp.json()

    if args.json:
        console.print_json(json.dumps(data, default=str))
        return

    if data.get("success"):
        console.print(
            f"[bold green]OK[/bold green] — {data.get('message', 'Connection successful')}"
        )
    else:
        console.print(
            f"[bold red]FAILED[/bold red] — {data.get('message', 'Unknown error')}"
        )
        sys.exit(1)


def cmd_set_default(args: argparse.Namespace) -> None:
    """Set a connection as the default."""
    with _client() as c:
        resp = c.put(f"/auth/connections/{args.connection_id}/default")
    _handle_error(resp)
    data = resp.json()

    if args.json:
        console.print_json(json.dumps(data, default=str))
        return

    console.print(f"[green]Default set to:[/green] {data['name']} ({data['id']})")


def cmd_update(args: argparse.Namespace) -> None:
    """Update a connection's settings or credentials."""
    body: dict[str, object] = {}
    if args.name is not None:
        body["name"] = args.name
    if args.host is not None:
        body["host"] = args.host
    if args.port is not None:
        body["port"] = args.port
    if args.user is not None:
        body["user"] = args.user
    if args.password is not None:
        body["password"] = args.password

    if not body:
        err.print("[yellow]Nothing to update. Specify at least one field.[/yellow]")
        sys.exit(1)

    with _client() as c:
        resp = c.put(f"/auth/connections/{args.connection_id}", json=body)
    _handle_error(resp)
    data = resp.json()

    if args.json:
        console.print_json(json.dumps(data, default=str))
        return

    console.print(f"[green]Updated:[/green] {data['name']} ({data['id']})")


def cmd_delete(args: argparse.Namespace) -> None:
    """Delete a connection."""
    with _client() as c:
        resp = c.delete(f"/auth/connections/{args.connection_id}")
    _handle_error(resp)
    console.print(f"[green]Connection {args.connection_id} deleted.[/green]")


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="connections",
        description="Manage IBM i system connections",
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    sub = parser.add_subparsers(dest="command", required=True)

    # list
    sub.add_parser("list", aliases=["ls"], help="List all connections")

    # create
    p_create = sub.add_parser(
        "create", aliases=["new"], help="Register a new connection"
    )
    p_create.add_argument(
        "--name",
        "-n",
        required=True,
        help="Human-readable label (e.g., 'Production LPAR')",
    )
    p_create.add_argument("--host", "-H", required=True, help="IBM i hostname or IP")
    p_create.add_argument("--user", "-u", required=True, help="IBM i user profile")
    p_create.add_argument(
        "--password", "-p", default=None, help="IBM i password (prompts if omitted)"
    )
    p_create.add_argument(
        "--port", type=int, default=8076, help="Mapepire port (default: 8076)"
    )
    p_create.add_argument(
        "--default", action="store_true", help="Set as the default connection"
    )

    # get
    p_get = sub.add_parser("get", help="Get connection details")
    p_get.add_argument("connection_id", help="Connection UUID")

    # test
    p_test = sub.add_parser("test", help="Test a connection")
    p_test.add_argument("connection_id", help="Connection UUID")

    # set-default
    p_default = sub.add_parser("set-default", help="Set a connection as the default")
    p_default.add_argument("connection_id", help="Connection UUID")

    # update
    p_update = sub.add_parser("update", help="Update a connection")
    p_update.add_argument("connection_id", help="Connection UUID")
    p_update.add_argument("--name", "-n", default=None, help="New name")
    p_update.add_argument("--host", "-H", default=None, help="New host")
    p_update.add_argument("--user", "-u", default=None, help="New user")
    p_update.add_argument("--password", "-p", default=None, help="New password")
    p_update.add_argument("--port", type=int, default=None, help="New port")

    # delete
    p_delete = sub.add_parser("delete", aliases=["rm"], help="Delete a connection")
    p_delete.add_argument("connection_id", help="Connection UUID")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    dispatch = {
        "list": cmd_list,
        "ls": cmd_list,
        "create": cmd_create,
        "new": cmd_create,
        "get": cmd_get,
        "test": cmd_test,
        "set-default": cmd_set_default,
        "update": cmd_update,
        "delete": cmd_delete,
        "rm": cmd_delete,
    }

    handler = dispatch.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
