---
name: deploy-platform
description: Take this IBM i AgentOS from a locally-proven stack to production on a host the user controls — preflight Podman and the production env, settle the network posture (this template ships no auth layer), start the compose.prod override, verify the platform is up and bounded, then hand over the redeploy/logs/teardown loop. Use this skill when the user asks to deploy, ship to production, go live, or take the platform to prod.
---

# Deploy the Platform

> _**Coding-agent workflow** — a `/slash-command` your coding agent (Claude Code, Codex, others) runs while developing this repo. Invoke it by name (e.g. `/deploy-platform`) or describe the task and it triggers automatically._

You are taking a locally-proven platform to production. This template carries no cloud-provider layer: production is the same Podman Compose the user already ran locally, plus the [`compose.prod.yaml`](../../../compose.prod.yaml) override, on a host they control. There is nothing to provision and nothing billed — the trade is that **this template ships no auth layer**, so the security boundary is network posture, and settling that posture honestly is this skill's most important job.

**Be self-driving:** run every command and check yourself. Stop when progress needs a human: picking the network posture, credentials only they can supply, a host only they can reach. When you stop, give exact instructions — and for interactive commands (SSH sessions, `tailscale up` logins), tell the user to run them in a separate terminal window, not this chat. Never read, echo, or print secret values from `.env` — talk *about* keys (`DB_PASS`, `DB2i_PASS`), never show them; when one must change, have the user edit `.env` in their editor.

**Narrate the trip:** open with the map, shaped like this, then a line as each step starts and a word when it lands:

```text
Kicking off /deploy-platform. Here's the map for this trip:

1. Read the deploy layer — compose.prod.yaml + the README's Deploy to production section
2. Preflight — Podman + compose provider, production .env, where this runs
3. Network posture — no auth layer here, so we decide who can reach port 8000
4. Start — podman compose with the prod override
5. Prove it — health probes, loopback bounds, one real agent answer
6. Hand over — redeploy, logs, teardown

Nothing here bills a cloud account — this deploys onto a host you already own.
The exit is always one command away: podman compose down.
```

On a **redeploy** — Step 4 finds the prod stack already running — the map is three beats (push the change, prove it live, hand back).

## 1. Read the deploy layer

Read [`AGENTS.md`](../../../AGENTS.md), the README's [Deploy to production](../../../README.md#deploy-to-production) section, and [`compose.prod.yaml`](../../../compose.prod.yaml) — they are the deploy truth this skill conducts; never invent a step they don't have. This is the family's smallest deploy layer: no provider CLI, no provisioning script, no domain minted for you. The target host is wherever this repo checkout lives — if the user wants production on a different machine, the flow is theirs to run there (clone, `.env`, this skill again); say so rather than pretending to reach a host you can't.

## 2. Preflight

Four checks before anything starts:

- **Podman + compose provider.** `podman info` works, and `podman compose version` answers. The prod override uses the `!reset`/`!override` merge tags — podman-compose 1.5+ (or docker-compose v2.24.4+ behind `podman compose`). If the versions are too old, stop and hand the user the upgrade path before going further.
- **Production `.env`.** The file exists with a model key (`ANTHROPIC_API_KEY` by default), real `DB2i_HOST` / `DB2i_USER` / `DB2i_PASS`, and a strong `DB_PASS` (the dev default is `ai`). Check *presence*, not values — `grep -c '^DB_PASS=' .env`-style probes, never printing. Two production-only conversations to have out loud:
  - **The IBM i identity.** Every agent shares the one `DB2i_*` profile. Production wants a least-privilege profile — read-only where possible — not a *SECOFR-class user. Ask which profile this is; recommend a dedicated one if they hesitate.
  - **The `DB_PASS` catch.** Postgres reads the password only when the `pgdata` volume is first initialized. If this host already ran the dev compose and they're changing `DB_PASS` now, the change won't take on its own — either alter it in place (`podman compose exec agentos-db psql -U ai -c "ALTER USER ai WITH PASSWORD '<new>';"` — have *them* run it with the real value) or `podman compose down -v` (say plainly: wipes all sessions, memory, traces).
- **Local proof.** The dev stack has answered a real agent question against their IBM i at least once (setup-platform's finish line). Deploying an unproven stack just moves the debugging to a worse place; run a quick local smoke first if in doubt.
- **Reboot survival.** All three services carry `restart: unless-stopped`, but only if Podman itself starts on boot — on Linux, `systemctl enable podman-restart`; on a Mac mini in a closet, the podman machine must autostart. Name it now so it doesn't surprise them later.

## 3. Network posture

This is the step that replaces the JWT-key ceremony other AgentOS templates have. Frame it honestly: the platform has **no authentication** — anyone who can reach port 8000 can run the agents against their IBM i and read the data — so before anything serves, they choose who can reach it. Lay out the three postures and ask them to pick (use the coding agent's structured-choice control when available):

| Posture | What it means | Good when |
|---|---|---|
| **LAN / VPN only** | Nothing extra runs; port 8000 is simply never exposed beyond the trusted network | The team is already on a private network |
| **Tailscale** | `tailscale serve 8000` — a private, WireGuard-encrypted tailnet URL; no public exposure | People connect from laptops anywhere |
| **Authenticating proxy** | Caddy/nginx with basic auth or SSO, or a Cloudflare Tunnel **paired with an Access policy** | A stable public name is required |

Two hard lines, stated plainly: never a public DNS name or unauthenticated tunnel pointed at 8000 bare, and the same applies to `/mcp` — it shares the port and carries no auth of its own. The database (5432) and the IBM i MCP server (3010) need no decision: the prod override rebinds both to loopback.

Tailscale and proxy setups are theirs to run (separate terminal; `tailscale serve` needs their login). Wait for "ready", capture the resulting URL — it's the address Steps 5 and 6 use.

## 4. Start in production mode

**First, is this a first deploy or a redeploy?** `podman ps` — if the stack is already up with the prod override, take the redeploy path: rebuild with the same command below (code), or recreate without `--build` (env), then skip to Step 5. Otherwise:

```bash
podman compose -f compose.yaml -f compose.prod.yaml up -d --build
```

Narrate what the override just did — `RUNTIME_ENV=prd`, debug off, no bind mount or hot reload (the container runs the code baked into the image), Postgres and `ibmi-mcp-server` rebound to loopback. Watch the boot with a bounded log read (`podman compose -f compose.yaml -f compose.prod.yaml logs --tail 50 agentos-api`) — clean start, no tracebacks, all six agents registered.

## 5. Prove it live and bounded

This is the payoff of deploying with a coding agent — you verify the platform, not just start it. Both directions matter:

- **Up** (from the host): `curl -sSf http://localhost:8000/health` → 200; `curl -sSf http://localhost:3010/healthz` → 200.
- **Bounded** (from a machine that should *not* have access — this part is the user's to run; give them the exact probes): port 8000 answers only over the posture from Step 3; 5432 and 3010 don't answer at all. If they have no second machine handy, at minimum confirm the publish bindings yourself: `podman ps --format '{{.Names}} {{.Ports}}'` must show `127.0.0.1:` on 5432 and 3010.
- **Real** (end to end): one agent run through the API, e.g. the performance agent answering "What is the current system status?" — a 200 with non-empty content, answered from their IBM i.
- **Connected**: have them connect the AgentOS UI at os.agno.com to the Step 3 address, and register coding agents with `claude mcp add --transport http agentos http://<address>/mcp` — over the private route only.

Close the step by showing what you verified, compactly — their platform is live, and only reachable the way they chose.

## 6. Hand over the loop

Finish with what they own now:

- code changes → `podman compose -f compose.yaml -f compose.prod.yaml up -d --build`
- env changes → edit `.env`, then the same command without `--build`
- logs → `podman compose -f compose.yaml -f compose.prod.yaml logs -f agentos-api`
- teardown → `podman compose -f compose.yaml -f compose.prod.yaml down` (`-v` also deletes the database volume — all sessions, memory, traces)
- the development loop keeps working against dev: [`/extend-agent`](../extend-agent/SKILL.md), [`/improve-agent`](../improve-agent/SKILL.md), [`/create-evals`](../create-evals/SKILL.md) — build and prove locally, then redeploy.
