# 🏛️ Hermes Multi-Agent System v4

> **4-ágenses intelligens rendszer** — Telegram + Discord multicommunication, agent-to-agent bus, shared memory, gradual autonomy.

## Architektúra

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
│              │   📬 Marveen Bus + Mnemosyne Memory  │                 │
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
│  │          MARVEEN MESSAGE BUS (SQLite WAL)                       │  │
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

## Ágensek

| Ágens | Modell | Szerep | Gateway | Csatornák |
|-------|--------|--------|---------|-----------|
| **General** | glm-5.1 | Orchesztrátor, routing, szintézis | Telegram + Discord | #general, #team, #human |
| **Dev** | big-pickle | Kódolás, debug, refactoring, CI/CD | Discord | #dev, #team |
| **Research** | glm-5.1 | Kutatás, forráselemzés, piackutatás | Discord | #research, #team |
| **Study** | big-pickle | Vizsgafelkészítés, jog, DevOps, fitness | Discord | #study, #devops, #fitness |

## Komponensek

### 📬 Marveen Message Bus (`marveen/`)

Inter-ágens kommunikációs rendszer SQLite WAL-mode adatbázissal.

```python
from marveen import create_message, get_messages, mark_done, discover_agents

# Üzenet küldése Dev-nek
msg = create_message("general", "dev", "Implement API endpoint for X", priority=1)

# Bejövő üzenetek olvasása
messages = get_messages(to_agent="dev", status="pending")

// Feladat befejezése
mark_done(msg_id, result="Done: pushed to feature/api-x")
```

**Állapotciklus:** `pending` → `delivered` → `read` → `done` / `failed`

**MCP Server:** Az `agent_send_message`, `agent_read_messages`, `agent_mark_done`, `agent_discover` tool-ok expozálva Hermes profilokon keresztül.

### 🧠 Hermes Mnemosyne Memory (`memory/`)

Háromrétegű megosztott memória SQLite + sqlite-vec + FTS5 backenddel.

- **Global scope** — minden ágens olvassa (preferenciák, konvenciók)
- **Session scope** — beszélgetés-specifikus kontextus
- **Knowledge Graph** — tényhárlok (subject-predicate-object)
- **BEAM konszolidáció** — régi working memóriák → episodic summaries

### ⚙️ Gradual Autonomy (`autonomy-config.json`)

15 kategóriás fokozatos autonómia rendszer:
- 🔴 **Level 1** — csak jelzés (notify)
- 🟡 **Level 2** — javaslat + emberi jóváhagyás
- 🟢 **Level 3** — teljes autonómia

Zárolt kategóriák: `git_force_push`, `email_send`, `payment`, `secret_access`

### 🎯 Agent Cards (`agent_cards/`)

JSON-alapú ágens regisztrációs kártyák, amiket a `discover_agents()` routing algoritmus használ:

```json
{
  "name": "dev",
  "display_name": "Dev Agent",
  "skills": [{"id": "implement-feature", "keywords": ["implementál", "build"], ...}],
  "model": "big-pickle",
  "autonomy_level": 3
}
```

A `discover_agents(task, top_k=3)` kulcsszó- és leírás-alapú pontozással_route-ol.

### 🌙 Dream Engine (`dreams/`)

Éjszakai konszolidáció — 5 bucket:
1. Skill javaslatok
2. Memória health check
3. Prioritások újraértékelése
4. Külső opportunity-k
5. Fleet health (ágens dostępność)

## Fájlstruktúra

```
hermes-multi-agent-system/
├── README.md                          # Ez a fájl
├── config.json                        # Discord csatorna & token térkép
├── team-knowledge.md                  # Közös tudásbázis (minden ágens olvassa)
├── marveen/
│   ├── __init__.py                    # Core modul (bus, autonomy, cards, discover)
│   └── mcp_server.py                  # MCP server (Hermes integráció)
├── memory/
│   └── mcp_server.py                  # Mnemosyne MCP server
├── agent_cards/
│   ├── general.json                   # Orchestrátor kártya
│   ├── dev.json                       # Dev kártya
│   ├── research.json                  # Research kártya
│   └── study.json                     # Study kártya
├── souls/
│   ├── general.md                     # General SOUL.md
│   ├── dev.md                         # Dev SOUL.md
│   ├── research.md                    # Research SOUL.md
│   └── study.md                       # Study SOUL.md
├── profiles/
│   ├── general.yaml                   # General profil config
│   ├── dev.yaml                       # Dev profil config
│   ├── research.yaml                  # Research profil config
│   └── study.yaml                     # Study profil config
├── .env.example                       # Környezeti változók sablon
├── .gitignore
└── scripts/
    ├── start-gateways.sh              # Összes gateway indítása
    └── restart-gateways.sh            # Gateway újraindítás staggered
```

## Gateway Konfiguráció

### Telegram (csak General)

A **General** profil az egyetlen, amelyik Telegram hozzáféréssel rendelkezik:

```yaml
# ~/.hermes/profiles/general/config.yaml
telegram:
  enabled: true
  reactions: false
  allowed_chats: '717405081'  # Csak Krisztian privát chat-je
discord:
  token: ${DISCORD_GENERAL_TOKEN}
  require_mention: true
  auto_thread: true
  allowed_channels: 1501148038117330995,...
```

### Discord (minden ágens)

Minden ágens saját Discord bot tokennel és csatornákkal:

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

## Indítás

```bash
# Összes gateway elindítása
./scripts/start-gateways.sh

# Vagy egyénileg
hermes gateway run --profile general --replace &
hermes gateway run --profile dev --replace &
hermes gateway run --profile research --replace &
hermes gateway run --profile study --replace &
```

## MCP Integráció

Minden profil configjában regisztrálva van a Marveen és a Memory MCP server:

```yaml
mcp_servers:
  marveen:
    command: /path/to/.hermes/.venv/bin/python3
    args:
      - /path/to/.hermes/scripts/marveen_mcp_server.py
    connect_timeout: 5
    timeout: 30
  hermes-memory:
    command: /path/to/.hermes/.venv/bin/python3
    args:
      - /path/to/.hermes/memory/mcp_server.py
    connect_timeout: 5
    timeout: 30
```

## Telepítés az éles rendszerbe

A fájlok az alábbi helyekre másolandók:

```bash
# Marveen core modul
~/.hermes/scripts/marveen/__init__.py
~/.hermes/scripts/marveen_mcp_server.py

# Memory MCP server
~/.hermes/memory/mcp_server.py

# Agent Cards
~/.hermes/data/marveen/agent_cards/general.json
~/.hermes/data/marveen/agent_cards/dev.json
~/.hermes/data/marveen/agent_cards/research.json
~/.hermes/data/marveen/agent_cards/study.json

# Autonomy config (auto-generated by first use)
~/.hermes/data/marveen/autonomy-config.json

# SOUL.md files
~/.hermes/profiles/general/SOUL.md
~/.hermes/profiles/dev/SOUL.md
~/.hermes/profiles/research/SOUL.md
~/.hermes/profiles/study/SOUL.md

# Team knowledge
~/.hermes/discord-multi-agent/team-knowledge.md  # vagy bárhova a SOUL.md-k hivatkozzanak
```

## Verzió

- **v1** — Bridge v3, 7 ágenses, hermes_bus.py, mem0 shared memory
- **v2** — Marveen Message Bus, Agent Cards, Gradual Autonomy, Dream Engine (legacy repo)
- **v3** — 4 ágenses (General/Dev/Research/Study), Hermes-native MCP, Mnemosyne memory, Telegram exclusive to General