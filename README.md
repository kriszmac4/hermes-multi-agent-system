# 🏛️ Hermes Multi-Agent System v4

> **4-Agent Intelligent System** — Telegram + Discord multi-communication, agent-to-agent bus, shared memory, gradual autonomy.

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                        USER (Krisztian)                              │
│                                                                      │
│   📱 Telegram ──────┐                        ┌──── Discord Server    │
│   (private DM)      │                        │  #general #dev #team  │
│                      │                        │  #research #study     │
│                      ▼                        ▼                       │
│              ┌──────────────────────────────────────┐                 │
│              │        GENERAL (Orchestrator)         │                 │
│              │   glm-5.1 | Telegram + Discord        │                 │
│              │   📬 AMB + Mnemosyne Memory  │                 │
│              └──────┬─────────┬──────────┬──────────┘                 │
│                     │         │          │                             │
│              ┌──────┴──┐ ┌────┴────┐ ┌───┴──────┐                    │
│              │  DEV    │ │RESEARCH │ │  STUDY   │                    │
│              │big-pickle│ │ glm-5.1 │ │big-pickle│                    │
│              │ #dev     │ │#research│ │#study +   │                    │
│              │ coding   │ │research │ │devops     │                    │
│              │ debug    │ │analysis │ │fitness    │                    │
│              └──────────┘ └─────────┘ └───────────┘                    │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │          AGENT MESSAGE BUS (SQLite WAL)                       │  │
│  │  agent_messages.db: send, receive, done, failed, read          │  │
│  │  Auto-cleanup > 72h • Priority messages • Status lifecycle      │  │
│  └─────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │          HERMES MNEMOSYNE (Shared Memory)                       │  │
│  │  SQLite + sqlite-vec + FTS5 • Global + Session scopes          │  │
│  │  Knowledge graph (triples) • BEAM consolidation • Scratchpad   │  │
│  └─────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │          GRADUAL AUTONOMY (15 categories)                      │  │
│  │  🔴 L1 notify only  🟡 L2 suggest+approve  🟢 L3 autonomous   │  │
│  │  Locked: git_force_push, email, payment, secrets                │  │
│  └─────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

## Agents

| Agent | Model | Role | Gateway | Channels |
|-------|--------|--------|---------|-----------|
| **General** | glm-5.1 | Orchestrator, routing, synthesis | Telegram + Discord | #general, #team, #human |
| **Dev** | big-pickle | Coding, debugging, refactoring, CI/CD | Discord | #dev, #team |
| **Research** | glm-5.1 | Research, source analysis, market research | Discord | #research, #team |
| **Study** | big-pickle | Exam preparation, law, DevOps, fitness | Discord | #study, #devops, #fitness |

## Components

### 📬 Agent Message Bus (`agent_message_bus/`)

Inter-agent communication system with SQLite WAL-mode database.

```python
from agent_message_bus import create_message, get_messages, mark_done, discover_agents

# Send message to Dev
msg = create_message("general", "dev", "Implement API endpoint for X", priority=1)

# Read incoming messages
messages = get_messages(to_agent="dev", status="pending")

// Complete task
mark_done(msg_id, result="Done: pushed to feature/api-x")
```

**Status lifecycle:** `pending` → `delivered` → `read` → `done` / `failed`

**MCP Server:** The `agent_send_message`, `agent_read_messages`, `agent_mark_done`, `agent_discover` tools are exposed through Hermes profiles.

### 🧠 Hermes Mnemosyne Memory (`memory/`)

Three-layer shared memory with SQLite + sqlite-vec + FTS5 backend.

- **Global scope** — read by all agents (preferences, conventions)
- **Session scope** — conversation-specific context
- **Knowledge Graph** — fact triples (subject-predicate-object)
- **BEAM consolidation** — old working memories → episodic summaries

### ⚙️ Gradual Autonomy (`autonomy-config.json`)

15-category gradual autonomy system:
- 🔴 **Level 1** — notify only
- 🟡 **Level 2** — suggest + human approval
- 🟢 **Level 3** — full autonomy

Locked categories: `git_force_push`, `email_send`, `payment`, `secret_access`

### 🎯 Agent Cards (`agent_cards/`)

JSON-based agent registration cards used by the `discover_agents()` routing algorithm:

```json
{
  "name": "dev",
  "display_name": "Dev Agent",
  "skills": [{"id": "implement-feature", "keywords": ["implement", "build"], ...}],
  "model": "big-pickle",
  "autonomy_level": 3
}
```

The `discover_agents(task, top_k=3)` routes via keyword- and description-based scoring.

### 🌙 Dream Engine (`dreams/`)

Nightly consolidation — 5 buckets:
1. Skill suggestions
2. Memory health check
3. Priority re-evaluation
4. External opportunities
5. Fleet health (agent availability)

## File Structure

```
hermes-multi-agent-system/
├── README.md                          # This file
├── config.json                        # Discord channel & token map
├── team-knowledge.md                  # Shared knowledge base (read by all agents)
├── agent_message_bus/
│   ├── __init__.py                    # Core module (bus, autonomy, cards, discover)
│   └── mcp_server.py                  # MCP server (Hermes integration)
├── memory/
│   └── mcp_server.py                  # Mnemosyne MCP server
├── agent_cards/
│   ├── general.json                   # Orchestrator card
│   ├── dev.json                       # Dev card
│   ├── research.json                  # Research card
│   └── study.json                     # Study card
├── souls/
│   ├── general.md                     # General SOUL.md
│   ├── dev.md                         # Dev SOUL.md
│   ├── research.md                    # Research SOUL.md
│   └── study.md                       # Study SOUL.md
├── profiles/
│   ├── general.yaml                   # General profile config
│   ├── dev.yaml                       # Dev profile config
│   ├── research.yaml                  # Research profile config
│   └── study.yaml                     # Study profile config
├── .env.example                       # Environment variable template
├── .gitignore
└── scripts/
    ├── start-gateways.sh              # Start all gateways
    └── restart-gateways.sh            # Staggered gateway restart
```

## Gateway Configuration

### Telegram (General only)

The **General** profile is the only one with Telegram access:

```yaml
# ~/.hermes/profiles/general/config.yaml
telegram:
  enabled: true
  reactions: false
  allowed_chats: '717405081'  # Only Krisztian's private chat
discord:
  token: ${DISCORD_GENERAL_TOKEN}
  require_mention: true
  auto_thread: true
  allowed_channels: 1501148038117330995,...
```

### Discord (all agents)

Each agent with its own Discord bot token and channels:

```json
{
  "server_id": "1501144914333925376",
  "channels": {
    "general": "1501148038117330995",
    "dev": "1501148006219776002",
    "research": "1501147842595655721",
    "study": "1501188232807972905",
    "human": "1501617834952888455",
    "team": "1501633520563654716"
  }
}
```

## Startup

```bash
# Start all gateways
./scripts/start-gateways.sh

# Or individually
hermes gateway run --profile general --replace &
hermes gateway run --profile dev --replace &
hermes gateway run --profile research --replace &
hermes gateway run --profile study --replace &
```

## MCP Integration

Each profile's config has the AMB and Memory MCP servers registered:

```yaml
mcp_servers:
  agent_message_bus:
    command: /path/to/.hermes/.venv/bin/python3
    args:
      - /path/to/.hermes/scripts/agent_message_bus_mcp_server.py
    connect_timeout: 5
    timeout: 30
  hermes-memory:
    command: /path/to/.hermes/.venv/bin/python3
    args:
      - /path/to/.hermes/memory/mcp_server.py
    connect_timeout: 5
    timeout: 30
```

## Installation into the Production System

The files should be copied to the following locations:

```bash
# AMB core module
~/.hermes/scripts/agent_message_bus/__init__.py
~/.hermes/scripts/agent_message_bus_mcp_server.py

# Memory MCP server
~/.hermes/memory/mcp_server.py

# Agent Cards
~/.hermes/data/agent_message_bus/agent_cards/general.json
~/.hermes/data/agent_message_bus/agent_cards/dev.json
~/.hermes/data/agent_message_bus/agent_cards/research.json
~/.hermes/data/agent_message_bus/agent_cards/study.json

# Autonomy config (auto-generated by first use)
~/.hermes/data/agent_message_bus/autonomy-config.json

# SOUL.md files
~/.hermes/profiles/general/SOUL.md
~/.hermes/profiles/dev/SOUL.md
~/.hermes/profiles/research/SOUL.md
~/.hermes/profiles/study/SOUL.md

# Team knowledge
~/.hermes/discord-multi-agent/team-knowledge.md  # or wherever the SOUL.md files reference
```

## Version

- **v1** — Bridge v3, 7 agents, hermes_bus.py, mem0 shared memory
- **v2** — Agent Message Bus, Agent Cards, Gradual Autonomy, Dream Engine (legacy repo)
- **v3** — 4 agents (General/Dev/Research/Study), Hermes-native MCP, Mnemosyne memory, Telegram exclusive to General
