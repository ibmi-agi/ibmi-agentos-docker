# IBM i AgentOS — Docker Template

Run a multi-agent system for IBM i on Agno AgentOS, with Podman.

[What is AgentOS?](https://docs.agno.com/agent-os/introduction) · [Agno Docs](https://docs.agno.com) · [Discord](https://agno.com/discord) · [IBM i MCP Server](https://github.com/IBM/ibmi-mcp-server)

---

## What's Included

### IBM i Agents
| Agent | Pattern | Description |
|-------|---------|-------------|
| **Text-to-SQL** | MCP built-ins | Translates natural language into SQL for Db2 for i |
| **Performance Monitor** | MCP | System performance analysis — CPU, memory, I/O metrics |
| **Security Audit** | MCP | Vulnerability assessment and remediation for IBM i security |
| **Library List Security** | MCP + Reasoning | Library list analysis and CWE-427 attack prevention |
| **PTF Management** | MCP | PTF group currency monitoring and maintenance planning |
| **Sample Database** | MCP | Demo agent for exploring the SAMPLE schema |

Every agent also gets a **`query_web`** tool — live web research over Parallel's MCP
endpoint, routed through a synthesizing sub-agent so the main agent's context stays clean.

---

## Quick Start

### Prerequisites

- [Podman](https://podman.io) + `podman-compose` — e.g. `brew install podman podman-compose`, then `podman machine init && podman machine start` (macOS/Windows; no machine step on Linux)
- [Anthropic API key](https://console.anthropic.com/settings/keys) (or another provider's key)
- An IBM i user profile with the [Mapepire](https://ibm-d95bab6e.mintlify.app/quickstart) database server installed on the system

### 1. Clone and configure
```sh
git clone https://github.com/ibmi-agi/ibmi-agentos-docker.git
cd ibmi-agentos-docker
cp .env.example .env
```

### 2. Configure `.env`

Add your API keys and IBM i connection details:
```sh
# Required - at least one model provider API key
ANTHROPIC_API_KEY=sk-ant-***

# IBM i connection
DB2i_HOST=your-ibmi-hostname
DB2i_USER=your-ibmi-user
DB2i_PASS=your-ibmi-password

# Model configuration (optional - defaults to Anthropic Claude)
# Format: "<provider>:<model_id>" - see https://docs.agno.com/models/providers/model-index
# AGENT_MODEL=anthropic:claude-sonnet-4-5
# AGENT_TEAM_MEMBER_MODEL=anthropic:claude-haiku-4-5

# Optional - higher rate ceiling for web research (query_web works keyless without it)
# PARALLEL_API_KEY=***
```

### 3. Start locally
```sh
podman compose up -d --build
```

- **API**: http://localhost:8000
- **Docs**: http://localhost:8000/docs
- **AgentOS MCP interface**: http://localhost:8000/mcp
- **IBM i MCP server (tools)**: http://localhost:3010/healthz
- **Database**: localhost:5432

### 4. Connect to control plane

1. Open [os.agno.com](https://os.agno.com)
2. Click "Add OS" → "Local"
3. Enter `http://localhost:8000`

### 5. Drive the agents over MCP (optional)

The platform itself is an MCP server (streamable HTTP at `/mcp`, same port as the
REST API): chat apps and coding agents run the agents through generic tools like
`run_agent(agent_id, message)`. The repo's [`.bob/mcp.json`](.bob/mcp.json) (symlinked
from `.mcp.json`) already registers it for coding agents working in this checkout;
elsewhere, register it by hand:

```sh
claude mcp add --transport http agentos http://localhost:8000/mcp
```

There is no auth layer in this template, so `/mcp` shares the API's
network-posture boundary — keep it private in production.

---

## The Agents

### Text-to-SQL

Translates natural language questions into SQL queries for Db2 for i. Handles schema discovery, query validation, and execution.

**What it does:**

| Capability | Description |
|------------|-------------|
| **Schema Discovery** | Browse schemas, tables, columns, and related objects |
| **Query Validation** | Validates SQL syntax using IBM i's native parser before execution |
| **DDL Inspection** | Generates the SQL DDL for any database object |
| **Execution** | Runs validated statements (with user confirmation) |

**Try it:**
```
What schemas are available on this system?
What tables are in the SAMPLE schema?
Show me all employees with a salary over 50000
```

**How it works:**
- Uses the IBM i MCP server's **built-in tools** (`--builtin-tools` / `--execute-sql`):
  `list_schemas`, `list_tables_in_schema`, `get_table_columns`, `get_related_objects`,
  `describe_sql_object`, `validate_query`, and `execute_sql`
- **Validate-first workflow** ensures queries are syntactically correct before running
- `execute_sql` requires explicit user confirmation (HITL)

### Performance Monitor

Monitors IBM i system performance — CPU, memory, I/O metrics — and provides actionable optimization insights.

**What it monitors:**

| Metric | Description |
|--------|-------------|
| **System Status** | CPU utilization, active jobs, system ASP |
| **Memory Pools** | Pool sizes, faults, activity levels |
| **HTTP Servers** | Connections, threads, request handling |
| **Active Jobs** | CPU consumption patterns and job activity |

**Try it:**
```
What is the current system status?
Check memory pool utilization
Show me the top CPU consuming jobs
```

**How it works:**
- **MCP tools** query QSYS2 system health views and Collection Services
- Provides prioritized recommendations with remediation steps

### Security Audit

Comprehensive security vulnerability assessment and guided remediation for IBM i systems.

**What it assesses:**

| Area | Description |
|------|-------------|
| **User Privileges** | Limited capability users, special authorities (*ALLOBJ, *SAVSYS) |
| **File Permissions** | Files readable, writable, deletable, or updatable by *PUBLIC |
| **Attack Vectors** | Trigger attacks, rename attacks, library list poisoning |
| **Impersonation** | User profiles vulnerable to impersonation |
| **Command Security** | Public authority on dangerous commands, audit settings |

**Try it:**
```
Perform a security audit of user privileges
Which files are readable by any user?
Are there any user profiles vulnerable to impersonation?
```

**How it works:**
- **MCP tools** query QSYS2 security views and authority tables
- **Assessment-first workflow** — always analyzes before recommending changes
- Remediation tools (lockdown commands) require explicit user confirmation

### Library List Security

Analyzes library list configurations to protect against "Uncontrolled Search Path Element" attacks (CWE-427).

**What it checks:**

| Check | Description |
|-------|-------------|
| **QSYSLIBL / QUSRLIBL** | System and user library list configuration |
| **CHGSYSLIBL Security** | Whether *PUBLIC can modify the system library list |
| **Library Authority** | Libraries with excessive *PUBLIC permissions |
| **Attack Surface** | Libraries where attackers could insert malicious objects |

**Try it:**
```
Analyze the security of my library list configuration
Can *PUBLIC execute CHGSYSLIBL?
Which libraries have excessive authority?
```

**How it works:**
- **MCP tools** inspect system values and library authorities
- **Reasoning tools** evaluate risk levels and prioritize findings
- Explains the attack scenario for each vulnerability found

### PTF Management

Monitors PTF (Program Temporary Fix) group currency and helps plan maintenance windows.

**What it tracks:**

| Capability | Description |
|------------|-------------|
| **PTF Currency** | Group status, levels behind, update availability |
| **Critical Updates** | Groups significantly behind with priority ranking |
| **Group Details** | Installed vs. available levels for each PTF group |
| **Maintenance Planning** | Update schedules based on criticality |

**Try it:**
```
What is the PTF status of this system?
Are there any critical PTF updates needed?
Which PTF groups are most out of date?
```

**How it works:**
- **MCP tools** query PTF group info and currency data from QSYS2
- Prioritizes by levels behind and group type (HIPER, Security, Database)

### Sample Database

Demo agent for exploring IBM's SAMPLE schema — employees, departments, projects, and salary data.

**What it queries:**

| Data | Description |
|------|-------------|
| **Employees** | Lookup, search, and filter by department or job |
| **Departments** | Organizational structure and reporting relationships |
| **Projects** | Team assignments and project status |
| **Salary Analysis** | Department stats, bonus calculations, range filters |

**Try it:**
```
Show me the employees in the SAMPLE database
Who works in department A00?
Which projects is employee 000010 assigned to?
```

**How it works:**
- **MCP tools** query the standard IBM i SAMPLE schema
- Educational focus — explains SQL concepts and IBM i conventions as it works

### Web Research (`query_web`)

Every agent can search the web through a single `query_web(question)` tool, backed by
Parallel's MCP endpoint. A synthesizing sub-agent owns the search and returns a cited
answer, so raw search snippets never enter the main agent's context window.

- Keyless by default — set `PARALLEL_API_KEY` for a higher rate ceiling
- Wired in `agents/utils/web_context.py`; the FastAPI lifespan in `app/main.py`
  connects/disconnects the backend

---

## Project Structure
```
├── agents/
│   ├── utils/
│   │   ├── common.py                    # Shared model config + instruction blocks (+ WEB)
│   │   ├── tools.py                     # Toolset loader for MCP tool filtering
│   │   └── web_context.py               # Parallel web-research provider (query_web)
│   ├── text2sql_agent.py                # Natural language to SQL (MCP built-ins)
│   ├── performance_agent.py             # System performance monitoring
│   ├── security_audit_agent.py          # Security vulnerability assessment
│   ├── library_list_security_agent.py   # Library list attack prevention
│   ├── ptf_agent.py                     # PTF group management
│   └── sample_data_agent.py             # SAMPLE schema demo
├── tools/                               # IBM i MCP tool YAMLs + generated toolsets.json
├── app/
│   ├── main.py                          # AgentOS entry point + web lifespan
│   └── config.yaml                      # Quick prompts per agent
├── db/
│   ├── session.py                       # PostgresDb factory
│   └── url.py                           # Connection URL builder
├── evals/                               # Eval suite (python -m evals)
├── scripts/                             # Helper scripts (format, validate, build, ...)
├── parse_mcp_tools.py                   # tools/*.yaml -> tools/toolsets.json
├── compose.yaml                         # Compose stack (podman compose)
├── compose.prod.yaml                    # Production override
└── pyproject.toml                       # Dependencies
```

---

## Common Tasks

### Add your own agent

1. Create `agents/my_agent.py`:
```python
from agno.agent import Agent

from agents.utils.common import AGENT_MODEL
from db import get_postgres_db

my_agent = Agent(
    id="my-agent",
    name="My Agent",
    model=AGENT_MODEL,
    db=get_postgres_db(),
    instructions="You are a helpful assistant.",
)
```

2. Register in `app/main.py`:
```python
from agents.my_agent import my_agent

agent_os = AgentOS(
    name="IBM i AgentOS",
    agents=[
        text2sql_agent,
        performance_agent,
        security_audit_agent,
        library_list_agent,
        ptf_agent,
        sample_agent,
        my_agent,
    ],
    ...
)
```

3. Restart: `podman compose restart agentos-api`

### Add tools to an agent

IBM i SQL tools are defined as YAML under `tools/` and exposed by the MCP server. Add a
`tools/*.yaml`, validate it against the live MCP server schema, regenerate the index,
and reference the toolset from the agent:

```sh
uv run python .agents/skills/create-agent/scripts/validate_tools.py tools/my-tools.yaml
uv run python parse_mcp_tools.py    # tools/*.yaml -> tools/toolsets.json
```
```python
from agents.utils.tools import get_toolset

tools = [MCPTools(url=MCP_URL, transport="streamable-http", include_tools=get_toolset("my_toolset"))]
```

Agno also ships 100+ tool integrations — see the [full list](https://docs.agno.com/tools/toolkits).

### Add dependencies

1. Edit `pyproject.toml`
2. Regenerate requirements: `./scripts/generate_requirements.sh`
3. Rebuild: `podman compose up -d --build`

### Use a different model provider

All agents share one model configuration via environment variables:

1. Add your API key to `.env` (e.g., `OPENAI_API_KEY`)
2. Set the model env var in `.env`:
```sh
AGENT_MODEL=openai:gpt-4o
# or google:gemini-2.0-flash, groq:llama-3.3-70b-versatile, ollama:llama3.3, ...
# Full list: https://docs.agno.com/models/providers/model-index
```
3. Restart: `podman compose restart agentos-api`

---

## Local Development

For development without the full container stack:
```sh
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Setup environment
./scripts/venv_setup.sh
source .venv/bin/activate

# Start PostgreSQL + MCP server (required)
podman compose up -d agentos-db ibmi-mcp-server

# Host-side runs reach the MCP server via its published port
export MCP_URL=http://localhost:3010/mcp

# Run the app
python -m app.main
```

### Run the evals

A small suite in `evals/` probes the live agents — schema discovery, system status,
prompt-injection defense, PTF currency, and more. Cases run in-process on the host
against your configured IBM i (read-only), so they need the `agentos-db` and
`ibmi-mcp-server` containers up plus your model key and IBM i credentials in `.env`:

```sh
source .venv/bin/activate
python -m evals --tag smoke     # fast core
python -m evals --tag release   # all cases
```

The LLM judge follows `AGENT_MODEL` (override with `EVALS_JUDGE_MODEL`). Results log to
Postgres and show up at [os.agno.com](https://os.agno.com). To add coverage for your own
agents, run the `/create-evals` skill; to repair a failing suite, `/eval-and-improve`.

### Validate tool YAML + regenerate toolsets.json

After adding or editing tool YAML files in `tools/`, validate them and regenerate the consolidated toolset mapping:

```sh
uv run python .agents/skills/create-agent/scripts/validate_tools.py tools/
uv run python parse_mcp_tools.py
```

The first command validates every YAML against the authoritative
[ibmi-mcp-server](https://github.com/IBM/ibmi-mcp-server) schema — downloaded fresh on
every run and discarded, so this repo never carries a stale copy. The second writes
`tools/toolsets.json`; agents load toolsets from this file at startup via `get_toolset()`.
`bash scripts/validate.sh` runs both (plus ruff + mypy) — it's what CI runs.

---

## Deploy to production

This template carries no cloud-provider layer at all: production is the same Podman
Compose you already ran locally, plus the [`compose.prod.yaml`](compose.prod.yaml)
override — on any host you control. A VPS, a home server, an office box, a partition
next to your IBM i. A coding-agent skill,
[`/deploy-platform`](.agents/skills/deploy-platform/SKILL.md), guides you through it.

> **Prerequisite:** a host with Podman and a compose provider — the prod override uses
> the `!reset`/`!override` merge tags, which need podman-compose 1.5+ (or, if
> `podman compose` delegates to docker-compose, v2.24.4+) — plus a private route for
> clients to reach port 8000 on it: LAN, VPN, or an authenticating reverse proxy /
> tunnel.

### 1. Decide the network posture

**This template ships no auth layer** — it is single-tenant by design, so network
posture *is* the security boundary: anyone who can reach port 8000 can run the agents
against your IBM i. Pick how clients reach the platform:

```sh
# LAN / VPN only — nothing extra to run; clients must be on the trusted network
# (just never expose 8000 beyond it)

# Tailscale — a private, WireGuard-encrypted URL on your tailnet; no public exposure
tailscale serve 8000

# Authenticating reverse proxy — a public name with auth enforced in front:
# Caddy/nginx with basic auth or SSO, or a Cloudflare Tunnel paired with a
# Cloudflare Access policy
cloudflared tunnel --url http://localhost:8000   # only behind an Access policy
```

Never point a public DNS name — or an unauthenticated tunnel — at port 8000 bare.

### 2. Set up your production env

Production values live in `.env` on the host — the same file compose already reads:

```sh
ANTHROPIC_API_KEY=sk-ant-...   # or another provider's key + AGENT_MODEL
DB2i_HOST=your-ibmi-hostname   # with DB2i_USER / DB2i_PASS
DB_PASS=<generate a strong one>
```

The agents reach IBM i through the one shared identity in `DB2i_*` — in production,
make it a least-privilege profile (read-only where possible), not a *SECOFR-class user.
`DB_PASS` replaces the dev default (`ai`) — the override keeps Postgres bound to
loopback, but a real password is still the floor for a production database.

One catch on a host that already ran the dev compose: Postgres reads the password only
when the `pgdata` volume is first initialized, so changing `DB_PASS` in `.env` won't
take on its own — the database keeps the old password and the API blocks waiting for
it. Either change it in place to match —
`podman compose exec agentos-db psql -U ai -c "ALTER USER ai WITH PASSWORD '<new>';"` —
or reinitialize with `podman compose down -v` (wipes all platform data).

### 3. Start in production mode

```sh
podman compose -f compose.yaml -f compose.prod.yaml up -d --build
```

The override switches `RUNTIME_ENV` to `prd`, turns off debug logging, drops the dev
bind mount and hot reload so the container runs the code baked into the image, and
rebinds Postgres **and** the `ibmi-mcp-server` to loopback so neither is reachable from
off-host (published container ports can bypass ufw-style host firewalls, so a plain
`5432:5432` publish really is public on a cloud host). All three services carry
`restart: unless-stopped`, so the platform survives reboots as long as Podman starts on
boot (e.g. `systemctl enable podman-restart` on Linux).

### 4. Verify it's up and bounded

From the host:

```sh
curl -sSf http://localhost:8000/health    # 200 — the API is serving
curl -sSf http://localhost:3010/healthz   # 200 — MCP server, loopback only
```

From a machine that should *not* have access: port 8000 must only answer over the route
you chose in step 1, and ports 5432 / 3010 must not answer at all. Then prove an agent
end to end — ask one a real question and confirm it answers from your IBM i.

### 5. Connect the control plane and MCP clients

- **AgentOS UI**: at [os.agno.com](https://os.agno.com), connect the OS using the
  address from step 1 (the LAN/VPN address, tailnet URL, or authenticated proxy URL).
- **Coding agents** reach the platform's own MCP interface at `/mcp`:
  `claude mcp add --transport http agentos http://<host>:8000/mcp`. Same posture
  caveat — `/mcp` carries no auth of its own, so register it only over the private
  route.

### 6. Redeploy after changes

```sh
git pull   # or edit in place
podman compose -f compose.yaml -f compose.prod.yaml up -d --build
```

Env changes are the same command without `--build` — compose recreates the containers
with the new `.env` values. Logs, when something looks off:

```sh
podman compose -f compose.yaml -f compose.prod.yaml logs -f agentos-api
```

Teardown is `podman compose -f compose.yaml -f compose.prod.yaml down` (add `-v` to
also delete the database volume — all sessions, memory, and traces).

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | Yes* | - | Anthropic API key (*or another provider's key) |
| `DB2i_HOST` | Yes | - | IBM i hostname or IP address |
| `DB2i_USER` | Yes | - | IBM i user profile |
| `DB2i_PASS` | Yes | - | IBM i password |
| `AGENT_MODEL` | No | `anthropic:claude-sonnet-4-5` | Model for agents ([provider index](https://docs.agno.com/models/providers/model-index)) |
| `AGENT_TEAM_MEMBER_MODEL` | No | `anthropic:claude-haiku-4-5` | Lightweight model for sub-agents |
| `EVALS_JUDGE_MODEL` | No | follows `AGENT_MODEL` | Model for the eval suite's LLM judge |
| `PARALLEL_API_KEY` | No | - | Parallel key for `query_web` (keyless works without it) |
| `OPENAI_API_KEY` | No | - | Embedder for agentic memory recall |
| `MCP_SERVER_VERSION` | No | `v0.5.1` | `ghcr.io/ibm/ibmi-mcp-server` image tag |
| `MCP_URL` | No | `http://ibmi-mcp-server:3010/mcp` | MCP server URL as the agents see it (use `http://localhost:3010/mcp` for host-side runs) |
| `DB_HOST` | No | `localhost` | PostgreSQL host |
| `DB_PORT` | No | `5432` | PostgreSQL port |
| `DB_USER` | No | `ai` | PostgreSQL user |
| `DB_PASS` | No | `ai` | PostgreSQL password |
| `DB_DATABASE` | No | `ai` | PostgreSQL database name |
| `RUNTIME_ENV` | No | `prd` | Set to `dev` for auto-reload |

---

## Learn More

- [IBM i MCP Server](https://github.com/IBM/ibmi-mcp-server)
- [Agno Documentation](https://docs.agno.com)
- [AgentOS Documentation](https://docs.agno.com/agent-os/introduction)
- [Tools & Integrations](https://docs.agno.com/tools/toolkits)
- [Discord Community](https://agno.com/discord)
