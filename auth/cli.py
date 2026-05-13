"""
API Key Admin CLI
=================

Lightweight CLI for managing API keys via the /auth/keys endpoints.

Usage::

    uv run apikeys list
    uv run apikeys create --name "ci-pipeline"
    uv run apikeys create --name "dev" --scopes agents:run teams:run
    uv run apikeys revoke <key-id>
    uv run apikeys rotate <key-id>

Configuration (env vars or .env file)::

    AGENTOS_URL=http://localhost:8000    # API base URL
    AUTH_MASTER_KEY=ixr_...            # Admin API key
"""

from __future__ import annotations

import argparse
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


def _scopes_str(scopes: list[str]) -> str:
    return ", ".join(scopes)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_list(args: argparse.Namespace) -> None:
    """List all API keys."""
    with _client() as c:
        resp = c.get("/auth/keys")
    _handle_error(resp)
    keys = resp.json()

    if not keys:
        console.print("[dim]No API keys found.[/dim]")
        return

    if args.json:
        console.print_json(json.dumps(keys, default=str))
        return

    t = Table(title="API Keys")
    t.add_column("ID", style="dim", max_width=36)
    t.add_column("Name", style="cyan")
    t.add_column("Prefix", style="green")
    t.add_column("Scopes", max_width=40)
    t.add_column("Active", style="bold")
    t.add_column("Created", style="dim", max_width=16)
    t.add_column("Last Used", style="dim", max_width=16)
    t.add_column("Expires", style="dim", max_width=16)

    for k in keys:
        active = "[green]yes[/green]" if k.get("is_active") else "[red]revoked[/red]"
        t.add_row(
            str(k["id"]),
            k["name"],
            k["key_prefix"],
            _scopes_str(k.get("scopes", [])),
            active,
            _ts(k.get("created_at")),
            _ts(k.get("last_used_at")),
            _ts(k.get("expires_at")),
        )

    console.print(t)
    console.print(f"[dim]{len(keys)} keys[/dim]")


def cmd_create(args: argparse.Namespace) -> None:
    """Create a new API key."""
    body: dict[str, object] = {"name": args.name}
    if args.scopes:
        body["scopes"] = args.scopes
    if args.expires:
        body["expires_at"] = args.expires

    with _client() as c:
        resp = c.post("/auth/keys", json=body)
    _handle_error(resp)
    data = resp.json()

    if args.json:
        console.print_json(json.dumps(data, default=str))
        return

    console.print(
        Panel(
            f"[bold green]{data['key']}[/bold green]",
            title=f"New API Key: {data['name']}",
            subtitle="Save this key now — it won't be shown again",
            border_style="green",
        )
    )
    console.print(f"  [dim]ID:[/dim]     {data['id']}")
    console.print(f"  [dim]Prefix:[/dim] {data['key_prefix']}")
    console.print(f"  [dim]Scopes:[/dim] {_scopes_str(data.get('scopes', []))}")


def cmd_revoke(args: argparse.Namespace) -> None:
    """Revoke an API key."""
    with _client() as c:
        resp = c.delete(f"/auth/keys/{args.key_id}")
    _handle_error(resp)
    console.print(f"[green]Key {args.key_id} revoked.[/green]")


def cmd_rotate(args: argparse.Namespace) -> None:
    """Rotate an API key (revoke old, create new)."""
    with _client() as c:
        resp = c.post(f"/auth/keys/{args.key_id}/rotate")
    _handle_error(resp)
    data = resp.json()

    if args.json:
        console.print_json(json.dumps(data, default=str))
        return

    console.print(
        Panel(
            f"[bold green]{data['key']}[/bold green]",
            title=f"Rotated Key: {data['name']}",
            subtitle="Old key revoked. Save this new key now.",
            border_style="yellow",
        )
    )
    console.print(f"  [dim]New ID:[/dim] {data['id']}")
    console.print(f"  [dim]Prefix:[/dim] {data['key_prefix']}")


def cmd_get(args: argparse.Namespace) -> None:
    """Get details of a single API key."""
    with _client() as c:
        resp = c.get(f"/auth/keys/{args.key_id}")
    _handle_error(resp)
    data = resp.json()

    if args.json:
        console.print_json(json.dumps(data, default=str))
        return

    active = "[green]active[/green]" if data.get("is_active") else "[red]revoked[/red]"
    console.print(f"  [dim]ID:[/dim]        {data['id']}")
    console.print(f"  [dim]Name:[/dim]      {data['name']}")
    console.print(f"  [dim]Prefix:[/dim]    {data['key_prefix']}")
    console.print(f"  [dim]Status:[/dim]    {active}")
    console.print(f"  [dim]Scopes:[/dim]    {_scopes_str(data.get('scopes', []))}")
    console.print(f"  [dim]Created:[/dim]   {_ts(data.get('created_at'))}")
    console.print(f"  [dim]Last Used:[/dim] {_ts(data.get('last_used_at'))}")
    console.print(f"  [dim]Expires:[/dim]   {_ts(data.get('expires_at'))}")
    console.print(f"  [dim]Revoked:[/dim]   {_ts(data.get('revoked_at'))}")


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="apikeys",
        description="Manage API keys",
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    sub = parser.add_subparsers(dest="command", required=True)

    # list
    sub.add_parser("list", aliases=["ls"], help="List all API keys")

    # create
    p_create = sub.add_parser("create", aliases=["new"], help="Create a new API key")
    p_create.add_argument("--name", "-n", required=True, help="Human-readable label")
    p_create.add_argument(
        "--scopes",
        "-s",
        nargs="+",
        help="Permission scopes (default: agents:run teams:run workflows:run)",
    )
    p_create.add_argument("--expires", help="Expiration timestamp (ISO 8601)")

    # get
    p_get = sub.add_parser("get", help="Get details of a key")
    p_get.add_argument("key_id", help="Key UUID")

    # revoke
    p_revoke = sub.add_parser("revoke", aliases=["rm"], help="Revoke a key")
    p_revoke.add_argument("key_id", help="Key UUID")

    # rotate
    p_rotate = sub.add_parser("rotate", help="Rotate a key (revoke old, create new)")
    p_rotate.add_argument("key_id", help="Key UUID")

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
        "revoke": cmd_revoke,
        "rm": cmd_revoke,
        "rotate": cmd_rotate,
    }

    handler = dispatch.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
