# IBM i AgentOS — Docker Template

Run a multi-agent system for IBM i on Agno AgentOS, with Docker.

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

- [Docker Desktop](https://www.docker.com/products/docker-desktop)
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
docker compose up -d --build
```

- **API**: http://localhost:8000
- **Docs**: http://localhost:8000/docs
- **MCP server**: http://localhost:3010/healthz
- **Database**: localhost:5432

### 4. Connect to control plane

1. Open [os.agno.com](https://os.agno.com)
2. Click "Add OS" → "Local"
3. Enter `http://localhost:8000`

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
├── scripts/                             # Helper scripts (format, validate, build, ...)
├── parse_mcp_tools.py                   # tools/*.yaml -> tools/toolsets.json
├── compose.yaml                         # Docker Compose stack
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

3. Restart: `docker compose restart agentos-api`

### Add tools to an agent

IBM i SQL tools are defined as YAML under `tools/` and exposed by the MCP server. Add a
`tools/*.yaml`, regenerate the index, and reference the toolset from the agent:

```sh
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
3. Rebuild: `docker compose up -d --build`

### Use a different model provider

All agents share one model configuration via environment variables:

1. Add your API key to `.env` (e.g., `OPENAI_API_KEY`)
2. Set the model env var in `.env`:
```sh
AGENT_MODEL=openai:gpt-4o
# or google:gemini-2.0-flash, groq:llama-3.3-70b-versatile, ollama:llama3.3, ...
# Full list: https://docs.agno.com/models/providers/model-index
```
3. Restart: `docker compose restart agentos-api`

---

## Local Development

For development without the full Docker stack:
```sh
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Setup environment
./scripts/venv_setup.sh
source .venv/bin/activate

# Start PostgreSQL + MCP server (required)
docker compose up -d agentos-db ibmi-mcp-server

# Run the app
python -m app.main
```

### Regenerate toolsets.json

After adding or editing tool YAML files in `tools/`, regenerate the consolidated toolset mapping:

```sh
uv run python parse_mcp_tools.py
```

This parses every YAML in `tools/`, validates against the MCP server schema, and writes
`tools/toolsets.json`. Agents load toolsets from this file at startup via `get_toolset()`.

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
| `PARALLEL_API_KEY` | No | - | Parallel key for `query_web` (keyless works without it) |
| `OPENAI_API_KEY` | No | - | Embedder for agentic memory recall |
| `MCP_SERVER_VERSION` | No | `v0.5.1` | `ghcr.io/ibm/ibmi-mcp-server` image tag |
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
