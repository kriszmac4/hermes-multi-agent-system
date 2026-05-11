# Hermes Multi-Agent System

Multi-agent orchestration system for Hermes Agent — Discord gateway, intelligent model routing, shared memory, and cross-agent communication bus.

## Architecture

```
┌─ KRISZTIAN (Telegram) ─────────────────────────────────┐
│                                                          │
│  ┌─────────────┐   ┌──────────────────────────────────┐ │
│  │  ORCHESTRATOR │   │     INTELLIGENT ROUTING         │ │
│  │  (gateway)    │   │  trivial/simple/moderate/complex │ │
│  │               │   │  → picks right model + timeout   │ │
│  └──────┬────────┘   └──────────┬───────────────────────┘ │
│         │                       │                         │
│  ┌──────┴────────────────────────┴──────────────────────┐ │
│  │                 BUS SYSTEM (hermes_bus.py)             │ │
│  │          SQLite WAL • send/receive/complete            │ │
│  │          Auto-cleanup • Status tracking                │ │
│  └──────┬─────────┬─────────┬─────────┬─────────┬───────┘ │
│         │         │         │         │         │         │
│  ┌──────┴───┐ ┌──┴────┐ ┌──┴────┐ ┌──┴────┐ ┌──┴───┐   │
│  │ research │ │  dev  │ │devops │ │ news  │ │study │   │
│  │ GLM-5.1 │ │DS-V4-F│ │MiniMax│ │DS-V4-F│ │GLM-5 │   │
│  └──────┬───┘ └──┬────┘ └──┬────┘ └──┬────┘ └──┬───┘   │
│         └─────────┴─────────┴─────────┴─────────┘         │
│                          │                                │
│  ┌───────────────────────┴──────────────────────────────┐ │
│  │            SHARED MEMORY (mem0_integration.py)         │ │
│  │  Layer 1: shared (org facts, routing rules)            │ │
│  │  Layer 2: hermes (personal preferences)                │ │
│  │  Layer 3: specialist (domain-specific)                  │ │
│  │  Backend: Qdrant + mem0                                │ │
│  └───────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

## Components

### Core

| File | Description |
|------|-------------|
| `bridge_v3.py` | Discord gateway — multi-bot bridge with routing, auto_thread, escalation, vision |
| `hermes_bus.py` | SQLite-based inter-agent message bus (WAL-mode, auto-cleanup) |
| `mem0_integration.py` | SharedMemory class for mem0 with 3-layer scoped access |
| `team-knowledge.md` | Cross-bot knowledge base (routing, channels, conventions) |
| `start.sh` | Launch script for the multi-agent bridge |
| `config.json` | Bridge configuration (bot tokens, channel mappings) |

### Skills

| Directory | Description |
|-----------|-------------|
| `intelligent-routing/` | Dynamic model router — complexity-based tier selection, dual-provider rate limits |
| `orchestrator/` | Multi-agent orchestrator — task analysis, profile selection, delegation patterns |

### Scripts

| Script | Description |
|--------|-------------|
| `scripts/orchestrator.py` | Profile-based multi-agent launcher with .env loading |
| `scripts/discord_task.py` | Send tasks to Discord bots via bridge |

## Model Routing

Two providers, two rate limit pools:

| Tier | Model | Provider | Use Case |
|------|-------|----------|----------|
| trivial | — | — | Direct response (no delegation) |
| simple | minimax-m2.5-free | opencode-zen | Quick answers, cron, Discord bots |
| moderate | deepseek-v4-flash | opencode-go | Coding, analysis |
| complex | glm-5.1 | opencode-go | Architecture, debug, coordination |
| expert | mimo-v2.5-pro | opencode-go | Research, planning |

## Shared Memory Architecture

3-layer scoped access:

1. **shared** — organizational facts all agents read (routing rules, user preferences)
2. **hermes** — default orchestrator's personal knowledge
3. **specialist** — domain-specific (dev, research, news, etc.)

Each agent performs dual search (`scope=shared` first, then `scope=own`) and merges results.

## Bus System

SQLite WAL-mode message bus for inter-agent communication:

```python
from hermes_bus import Bus
bus = Bus()
bus.send(from_agent="dev", to_agent="research", task="Analyze this API response")
msg = bus.receive(agent="research")  # Returns pending messages
bus.complete(msg["id"])               # Mark as done
```

## Requirements

- Python 3.11+
- Discord bot tokens (7 bots)
- OpenCode Go ($10/mo flat) or compatible LLM provider
- Qdrant (for mem0 shared memory)
- Hermes Agent (`~/.hermes/`)

## License

MIT