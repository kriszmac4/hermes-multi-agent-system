# Hermes Multi-Agent System

> **Intelligent multi-agent orchestration for Discord** — gateway bridge, dynamic model routing, shared memory, inter-agent message bus, and self-improving capability tracking.

## Overview

This repository contains the core infrastructure that makes 7 Discord bots work as a **cohesive team** rather than isolated agents. Each specialist has its own LLM, personality (SOUL.md), and memory scope — but they coordinate through a shared message bus, escalate unsolvable tasks to a generalist coordinator, and collectively learn which agent is best at what.

```
┌─ USER (Telegram / Discord) ──────────────────────────────────────────┐
│                                                                       │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │                    BRIDGE v3 (Gateway)                           │ │
│  │  Discord ↔ LLM per-profile gateway with:                        │ │
│  │  • Auto-thread creation & tracking                               │ │
│  │  • Smart approval (dev/devops/general) vs auto-approve (others)  │ │
│  │  • Vision escalation (images → Vertex AI Gemini)                 │ │
│  │  • Fact extraction → mem0 at 3 checkpoints                     │ │
│  │  • Two-phase delegation: PLAN (high-reasoning) → EXECUTE (fast) │ │
│  └──────────┬───────────────────────────────────────────────────────┘ │
│             │                                                         │
│  ┌──────────┴───────────────────────────────────────────────────────┐ │
│  │              INTELLIGENT MODEL ROUTING                            │ │
│  │                                                                  │ │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌──────────┐ ┌─────────┐ │ │
│  │  │ TRIVIAL │ │ SIMPLE  │ │MODERATE │ │ COMPLEX  │ │ EXPERT  │ │ │
│  │  │ (local) │ │MiniMax  │ │ DS-V4-F │ │ GLM-5.1  │ │Mimo-Pro │ │ │
│  │  │ <50ms   │ │ zen/free│ │  op-go  │ │  op-go   │ │  op-go  │ │ │
│  │  └─────────┘ └─────────┘ └─────────┘ └──────────┘ └─────────┘ │ │
│  │                                                                  │ │
│  │  Dual-provider rate limiting: opencode-go ($10/mo flat) +        │ │
│  │  opencode-zen (free pool) — prevents cross-pool exhaustion      │ │
│  └──────────────────────────────────────────────────────────────────┘ │
│             │                                                         │
│  ┌──────────┴─────────┬──────────────┬──────────────┬──────────────┐ │
│  │     research       │     dev      │    devops    │    news      │ │
│  │     GLM-5.1        │  DS-V4-Flash │  MiniMax-M2.5│  DS-V4-Flash │ │
│  └─────────┬──────────┴──────┬───────┴──────┬───────┴──────┬──────┘ │
│            │                  │              │              │         │
│  ┌─────────┴──────────────────┴──────────────┴──────────────┴──────┐ │
│  │                 BUS SYSTEM (hermes_bus.py)                     │ │
│  │  SQLite WAL-mode message bus: send, receive, complete          │ │
│  │  Auto-cleanup > 24h • Status lifecycle • Metadata JSON         │ │
│  └────────────────────────┬───────────────────────────────────────┘ │
│                           │                                         │
│  ┌────────────────────────┴───────────────────────────────────────┐ │
│  │              SHARED MEMORY (mem0_integration.py)                │ │
│  │                                                                │ │
│  │  Layer 1: shared ← org facts, routing rules, preferences      │ │
│  │  Layer 2: hermes  ← orchestrator's personal knowledge          │ │
│  │  Layer 3: specialist ← domain-specific (dev, research, etc.)   │ │
│  │                                                                │ │
│  │  Each agent: dual search (shared scope + own scope) → merge    │ │
│  │  Backend: Qdrant vector DB with mem0                           │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │         DEVELOPMENT TRACKER (self-improving)                   │ │
│  │                                                                │ │
│  │  • Agent capability scores (0-100) learned from task outcomes  │ │
│  │  • Escalation tracking: who escalated, who resolved            │ │
│  │  • Auto-updates team-knowledge.md with new capabilities        │ │
│  │  • get_best_agent_for(skill) → returns highest-scoring agent  │ │
│  └────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

## Components

### [`bridge_v3.py`](bridge_v3.py) — Discord Gateway (1416 lines)

The central nervous system. Each specialist bot runs as a **separate Hermes gateway instance** connected to its own Discord bot token. The bridge handles:

| Feature | How it works |
|---------|-------------|
| **Auto-thread creation** | Messages in specialist channels automatically create Discord threads for context isolation |
| **Smart approval** | 2-phase system: dev/devops/general channels require human approval before executing risky operations; research/news/study/fitness auto-approve |
| **Two-phase delegation** | PLAN (high-reasoning model) → EXECUTE (fast model). The coordinator drafts a plan, then hands it off to a specialist for implementation |
| **Vision escalation** | Images in messages are detected and routed to Vertex AI Gemini for description before passing context to the specialist |
| **Fact extraction** → mem0 | At 3 checkpoints (specialist response, delegation result, escalation), key facts are extracted and stored in shared/specialist memory |
| **SOUL.md loading** | Each agent loads its personality from `~/.hermes/profiles/{agent}/SOUL.md` |
| **Team knowledge injection** | `team-knowledge.md` is injected into every agent's system prompt at startup |
| **Capability learning** | `DevelopmentTracker` records task success/failure per skill area, building a capability score per agent over time |

**Agent → Model Mapping:**

```python
AGENT_MODELS = {
    "general":  "glm-5.1",         # Coordinator, reasoning
    "research": "glm-5.1",         # Deep analysis, research
    "study":    "glm-5",           # Law, exam prep
    "dev":      "deepseek-v4-flash", # Coding, fast
    "news":     "deepseek-v4-flash", # News, summaries
    "fitness":  "deepseek-v4-flash", # Training plans
    "devops":   "minimax-m2.5",    # Infrastructure, medium
}
```

**Escalation chain:** Specialist can't handle → escalate to General → General delegates to best-fit specialist → outcome recorded in DevelopmentTracker.

### [`hermes_bus.py`](hermes_bus.py) — Inter-Agent Message Bus (616 lines)

SQLite-based async message bus for inter-agent communication. Designed for concurrent multi-process access from bridge instances.

```python
from hermes_bus import HermesBus, BusMessage

bus = HermesBus()  # Default: ~/.hermes/discord-multi-agent/bus.db

# Send a task from research to dev
bus.send(from_agent="research", to_agent="dev",
         type="delegation",
         content="Implement the API client we discussed",
         thread_id="1501147842595655721")

# Dev picks up pending tasks
messages = bus.receive(agent="dev")  # Returns list[BusMessage]

# Mark completed
bus.complete(msg_id, result="Done: pushed to branch feature/api-client")
```

**BusMessage fields:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Auto-increment ID |
| `from_agent` | str | Sender agent ID |
| `to_agent` | str | Recipient, or `"broadcast"` for all |
| `type` | str | `delegation`, `result`, `info`, `escalation` |
| `content` | str | Message body |
| `thread_id` | str | Discord thread reference |
| `parent_msg_id` | str | Original Discord message ID |
| `status` | str | `pending` → `in_progress` → `completed` / `failed` |
| `metadata` | dict | Flexible JSON for arbitrary data |

**Design decisions:**
- **WAL mode** for concurrent reads from multiple bridge processes
- **Auto-cleanup** prunes messages older than 24 hours
- **Indexed** on `(to_agent, status)` and `(from_agent, created_at)` for fast queries
- **Configurable path** — defaults to `bus.db` in the multi-agent directory

### [`mem0_integration.py`](mem0_integration.py) — 3-Layer Shared Memory (274 lines)

Hierarchical memory built on [mem0](https://mem0.ai) with Qdrant backend. Each agent reads from two scopes and writes to one:

```
┌──────────────────────────────────────┐
│  SHARED (scope="shared")            │  ← Any agent writes
│  • User preferences                 │
│  • Routing rules                    │
│  • System configuration             │
│  • Cross-agent conventions          │
├──────────────────────────────────────┤
│  SPECIALIST (scope="dev"/"research") │  ← Only that agent reads
│  • Domain-specific knowledge        │
│  • Task history                     │
│  • Technical details                │
└──────────────────────────────────────┘
```

```python
from mem0_integration import SharedMemory

memory = SharedMemory()

# Agent searches both shared + own scope (dual search, merged, deduped)
results = memory.search(query="Discord bot tokens", agent="dev", scope="all")
# Returns: [{"memory": "...", "score": 0.89, "agent_id": "shared", "scope": "shared"}, ...]

# Write org-level fact (all agents can find it)
memory.add(content="Approval required for dev tasks", agent="shared", scope="shared")

# Write specialist fact (only dev can find it)
memory.add(content="Python 3.11.2 available", agent="dev", scope="specialist")

# Get formatted context for AI prompts
context = memory.get_context(agent="research", query="Vertex AI setup")
# Returns: "## Shared Knowledge\n- Approval required for dev tasks\n\n## Specialist Knowledge\n..."
```

**Key behavior:** `mem0` doesn't support `{in: [shared, dev]}` filter — so we perform **two separate searches** and merge results in-code, with shared scope taking priority on conflicts.

### [`team-knowledge.md`](team-knowledge.md) — Cross-Bot Knowledge Base

A living document that **every bot reads at startup** and **DevelopmentTracker auto-updates** when agents demonstrate new capabilities. Contains:

- **Project context** (models, channels, infrastructure)
- **Team culture & rules** (escalation chain, transparency requirements)
- **Role table** — who does what, their model, limitations, and who to escalate to
- **Delegation keywords** — which words trigger which specialist
- **Development log** — auto-appended when an agent scores ≥70 in a skill area (3+ successes)

### Intelligent Routing ([`intelligent-routing/`](intelligent-routing/))

Dynamic model selection based on task complexity. Instead of every task hitting the most expensive model:

```
Task arrives
    ↓
DISPATCHER analyzes complexity
    ├── TRIVIAL (<5 words, question) → Answer directly, no delegation
    ├── SIMPLE (search, list, definition) → minimax-m2.5-free (opencode-zen, FREE)
    ├── MODERATE (coding, analysis, writing) → deepseek-v4-flash (opencode-go)
    ├── COMPLEX (architecture, debug, multi-step) → deepseek-v4-pro / glm-5.1 (opencode-go)
    └── EXPERT (research, planning, innovation) → mimo-v2.5-pro (opencode-go)
```

**Dual-provider architecture** prevents rate limit exhaustion:
- `opencode-go` ($10/mo flat): GLM-5.1, DS-V4-Pro/Flash, MiniMax-M2.5, Mimo-Pro
- `opencode-zen` (free pool): MiniMax-M2.5-free for simple/cron tasks

**Key pitfall documented:** MiniMax-M2.5-free stays on zen (separate rate pool). Moving it to go would exhaust the GLM-5.1 rate limit (880 req/5h).

### Orchestrator ([`orchestrator/`](orchestrator/))

Three-level orchestration pattern:

| Level | Method | Speed | Isolation |
|-------|--------|-------|-----------|
| 1 | `delegate_task()` | 5-15s | Low (subagent in same process) |
| 2 | `hermes chat --profile X -q` | 30-60s | High (separate instance) |
| 3 | `bridge_v3.py` + Discord | Real-time | Persistent |

- **Level 1** for quick parallel tasks within a session
- **Level 2** for long-running isolated work needing profile-specific memory
- **Level 3** for real-time visible collaboration on Discord channels

**Transparency rule:** Every orchestrator response MUST include agent count, per-agent summary, status, and total time.

## Setup

### Prerequisites

```bash
# Python 3.11+ with uv
python3 --version
# Hermes Agent installed
hermes --version
# Discord server with bot tokens (7 bots)
```

### Installation

```bash
git clone https://github.com/kriszmac4/hermes-multi-agent-system.git
cd hermes-multi-agent-system

# Copy and configure environment
cp .env.example .env
# Edit .env with your Discord bot tokens

# Create profiles directory
mkdir -p ~/.hermes/profiles/{general,research,dev,devops,news,study,fitness}
```

### Running

```bash
# Start all 6 specialist bots in tmux
./start.sh

# Or start individual bots
./start.sh research
./start.sh dev

# Monitor
tmux attach -t hermes-discord
```

### Configuration

**`config.json`** — Server ID, channel IDs, bot tokens (use env vars for security):

```json
{
  "server_id": "YOUR_SERVER_ID",
  "channels": {
    "research": "CHANNEL_ID",
    "dev": "CHANNEL_ID",
    "devops": "CHANNEL_ID",
    "news": "CHANNEL_ID",
    "general": "CHANNEL_ID",
    "study": "CHANNEL_ID",
    "human": "CHANNEL_ID",
    "team": "CHANNEL_ID",
    "fitness": "CHANNEL_ID"
  },
  "tokens": {
    "research": "${DISCORD_TOKEN_RESEARCH}",
    "dev": "${DISCORD_TOKEN_DEV}",
    ...
  }
}
```

**Per-profile SOUL.md** — Personality files at `~/.hermes/profiles/{agent}/SOUL.md`:

Each file contains: role description, competencies, 5-step work method, communication style, and examples of good/bad responses. Written in Hungarian with technical terms in English.

**Per-profile mem0.json** — Memory configuration:

```json
{
  "agent_id": "dev",
  "llm": { "model": "deepseek-v4-flash", "base_url": "..." }
}
```

## Directory Structure

```
hermes-multi-agent-system/
├── bridge_v3.py              # Main gateway — 1416 lines
│   ├── DevelopmentTracker    # Capability learning & scoring
│   ├── TaskTracker           # Task lifecycle tracking
│   ├── get_ai_response()     # LLM call with model selection
│   ├── run_bridge()          # Main event loop per agent
│   └── fact extraction       # 3-checkpoint mem0 storage
│
├── hermes_bus.py             # Message bus — 616 lines
│   ├── BusMessage            # Dataclass with status lifecycle
│   └── HermesBus             # SQLite WAL CRUD + cleanup
│
├── mem0_integration.py      # Shared memory — 274 lines
│   └── SharedMemory          # Hierarchical search/add/context
│
├── start.sh                  # tmux launcher for 6 bots
├── config.json               # Server/channels/tokens
├── team-knowledge.md         # Cross-bot knowledge base
├── .env.example              # Token template
├── .gitignore
│
├── intelligent-routing/      # Model routing skill
│   ├── SKILL.md              # Full routing documentation
│   ├── references/           # Model configs, design docs
│   └── scripts/              # route_task.py, model_discovery.py
│
├── orchestrator/             # Orchestration patterns skill
│   ├── SKILL.md              # Delegation docs + pitfalls
│   ├── references/           # Architecture patterns
│   └── scripts/              # orchestrator.py, discord_task.py
│
└── scripts/                  # Standalone scripts
    ├── orchestrator.py       # Profile-based launcher
    └── discord_task.py        # Discord task submission
```

## Key Design Decisions

### 1. Two-Phase Delegation

High-reasoning models are expensive. Instead of sending every task to GLM-5.1:

```
PLAN phase:  GLM-5.1 drafts plan ($0.015)
EXECUTE phase: MiniMax-M2.5-free implements ($0.00)
Total: ~$0.015 vs ~$0.15 if only Pro was used → 90% savings
```

### 2. Self-Improving Capability Tracking

`DevelopmentTracker` learns from outcomes:

```python
dev_tracker.record_task_success("dev", "python")    # score += 10
dev_tracker.record_task_failure("dev", "rust")      # score -= 2
best = dev_tracker.get_best_agent_for("python")     # → "dev" (score: 80/100)
```

When an agent reaches score ≥70 with 3+ successes, `team-knowledge.md` is auto-updated with the new capability — visible to all bots next time they start.

### 3. Memory Scoping

The `scope="shared"` vs `scope="specialist"` distinction prevents cross-contamination:

- **Shared**: "User prefers concise responses" → all agents can read this
- **Specialist**: "Dev learned that Python 3.11.2 is available" → only Dev's context includes this
- **Merge priority**: On conflict, shared scope wins (organizational truth > individual memory)

### 4. Escalation Chain

```
Specialist stuck
    ↓
Escalate to General (#team channel via @mention)
    ↓
General: checks DevelopmentTracker → "who's best at this?"
    ↓
General: delegates to best-fit specialist
    ↓
Outcome recorded: capability score updated
```

Specialists **never** delegate directly to each other — always through the coordinator, who has the full capability picture.

## Requirements

| Dependency | Purpose |
|-----------|---------|
| Python 3.11+ | Runtime |
| Hermes Agent | Core agent framework (`~/.hermes/`) |
| mem0 + Qdrant | Shared memory backend |
| Discord.py | Bot gateway |
| OpenCode Go / Zen | LLM providers |
| aiohttp | Async HTTP for Discord API |

## License

MIT