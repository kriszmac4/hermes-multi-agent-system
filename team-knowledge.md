# 🧠 Team Knowledge Base v4

This file is READ by ALL bots at startup and updated after important realizations.
Format: each block is marked with [YOUR_PROFILE] indicating who wrote it.

---

## 🏗️ Project Context

- 4-agent system: General (coordinator), Dev, Research, Study
- Telegram: EXCLUSIVELY General profile (allowed_chats: 717405081)
- Discord: Each agent has its own bot, on separate channels
- Models: General=GLM-5.1, Dev=big-pickle, Research=GLM-5.1, Study=big-pickle
- Provider: OpenCode Go ART (GLM-5.1, MiniMax), OpenCode Zen ART (big-pickle)
- Agent Message Bus: inter-agent communication via SQLite WAL-mode
- Hermes Mnemosyne: shared memory (sqlite-vec + FTS5)
- Home PC: Python 3.11.2, uv package manager, Hermes Agent vLatest
- Approval: dev/devops/general=smart, research/study=off

---

## 🤝 Team Culture and Rules

### Core Principles
1. **Never say "I don't know" and stop** — IF you don't know something, ASK a colleague
2. **Krisztian should not be the bottleneck** — the system should figure out the solution
3. **Shared knowledge > individual knowledge** — what you learn, share in team-knowledge.md
4. **Transparency** — every multi-agent response includes who worked, how long, and what the result was
5. **Proactive delegation** — if it's not your area, IMMEDIATELY forward it to the appropriate agent

### Escalation Chain (MANDATORY)

```
1. TRY IT — do you have tools for it? (web search, terminal, etc.)
2. ESCALATE TO GENERAL — agent_send_message(to_agent="general", content="...")
   General is the team lead: knows who is capable of what, decides who to forward to
3. ASK KRISZTIAN FOR HELP — #human channel, if:
   - API key needed
   - Manual step needed (e.g. Discord setup)
   - Decision needed (risky task >5 minutes)
4. SHARE AS KNOWLEDGE — if you learned something new, update team-knowledge.md
```

### Who Does What (Roles)

| Agent | Specialty | Model | What it CAN'T do | Forward to |
|-------|-----------|-------|------------------|------------|
| General | Coordination, synthesis, planning, Telegram | GLM-5.1 | Deep coding | Dev, Research, Study |
| Dev | Coding, scripting, API, debug | big-pickle | Legal questions | Study, Research |
| Research | Deep research, source analysis | GLM-5.1 | Coding, infra | Dev |
| Study | Exam prep, law, DevOps, fitness | big-pickle | Deep coding | Dev, Research |

### Communication Style
- **Hungarian** is the default language
- **Concise, to-the-point** responses
- **Provide sources** — links, references
- **Bottom-line first** — result first, details after

---

## 📬 Agent Message Bus

### MCP Tools
- `agent_send_message(to_agent, content, priority)` — sending a message
- `agent_read_messages(status, limit, mark_read)` — reading incoming messages
- `agent_mark_done(message_id, result)` — completing a task
- `agent_discover(task, top_k)` — find the best agent
- `agent_list_cards()` — list of registered agents
- `autonomy_get_levels()` / `autonomy_set_level()` — autonomy levels
- `agent_message_bus_status()` — system status

### State Cycle
`pending` → `delivered` → `read` → `done` / `failed`

### Priority
- 0 = normal
- 1 = high
- 2 = urgent

---

## 🧠 Mnemosyne Memory

### Scopes
- **Global** (`scope="global"`) — every agent reads (preferences, conventions)
- **Session** (`scope="session"`) — conversation-specific context

### Knowledge Graph
- Fact triples: `(subject, predicate, object)` format
- Search: `hermes_triple_query(subject, predicate, object)`

---

## ⚠️ Pitfalls and Solutions

### Discord-specific
- Loop danger between bot messages → never automatically reply to another bot's message
- 2000 character limit per Discord message → split long responses
- Privileged Intents are mandatory (Presence + Members + Content)
- Token sync: must be in both config.yaml and .env file

### Telegram-specific
- Only the General profile has Telegram access
- `allowed_chats: '717405081'` — only Krisztian's private DM
- Reactions disabled: `reactions: false`

### Technology
- OpenCode Go: reasoning models use `reasoning_content` field
- Home PC: Python 3.11.2, no pip, only `uv pip install`
- subprocess does not inherit `.env` variables

---

## 🔧 Delegation Keywords

- `code/implement/bug/debug/script/api/python` → **Dev**
- `infra/server/deploy/docker/ci-cd/nginx` → **Dev** (via Study devops skill)
- `research/find/search/analyze/compare/synthesize` → **Research**
- `law/legal/study/exam/judicial/criminal/civil` → **Study**
- `fitness/workout/training/exercise/yoga/HIIT` → **Study** (fitness skill)
- Default (no match) → **General**

---

## 📋 Lessons and Templates

### [General] 2026-06-02: v4 architecture
The 4-agent system (General/Dev/Research/Study) replaced the 7-agent system.
The News and DevOps agents have been decommissioned. The Study agent took over the DevOps and Fitness roles.
The Fitness agent remains a separate profile (doesn't run in the gateway, only as a cron job).

### [General] 2026-06-02: Telegram exclusivity
Telegram access is EXCLUSIVELY for the General profile.
All other agents only communicate via Discord.
This ensures that Krisztian's DM always reaches the coordinator.

### [General] 2026-06-02: AMB MCP native integration
bridge_v3.py and hermes_bus.py replaced with Hermes-native MCP tools.
The Agent Message Bus now runs as an MCP server, not as a standalone script.
The Hermes Mnemosyne memory MCP is also natively integrated.
