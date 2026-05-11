---
name: orchestrator
description: "Hermes multi-agent orchestrator — coordinates tasks across profiles (research, dev, devops, news, study) from a single gateway session."
version: 1.0.0
tags: [orchestrator, multi-agent, profiles, delegation]
---

# Hermes Orchestrator

Multi-agent orchestrator that coordinates work across Hermes profiles from a single gateway session.

## Architecture

### Two-Layer System

```
Layer 1: ORCHESTRATOR (Hermes Gateway)
├── Receives tasks from Krisztian (Telegram)
├── Analyzes task → selects profiles
├── Spawns subagents via delegate_task (parallel)
└── Collects results

Layer 2: DISCORD VISIBILITY
├── Posts tasks to Discord channels
├── Bridge_v3.py bots respond in #team
├── Results visible in Discord
└── Krisztian can interact directly on Discord
```

### Three Approaches

| Approach | Use Case | Speed | Isolation |
|----------|----------|-------|-----------|
| `delegate_task` | Quick parallel tasks within session | Fast (5-15s) | Low |
| `discord_task.py` | Send tasks to Discord bots | Instant | High |
| `hermes chat -q` | Profile-specific isolated work | Slow (30-60s) | High |

## How It Works

1. **User sends a task** to the gateway (Telegram)
2. **Orchestrator analyzes** the task and decides which profiles to involve
3. **Spawns profiles** via `hermes --profile X -q "task"` (terminal tool)
4. **Collects results** from each profile's stdout
5. **Synthesizes** and returns a unified response

## Profile Selection Rules

| Keywords | Profile | Model | Use Case |
|----------|---------|-------|----------|
| research, kutatás, elemzés, összehasonlítás | research | GLM-5.1 | Deep analysis, comparison |
| code, kód, implement, script, API | dev | DS-V4-Flash | Coding, implementation |
| infra, deploy, docker, server, CI/CD | devops | MiniMax-M2.5 | Infrastructure |
| news, hír, aktual, cikk | news | DS-V4-Flash | News, current events |
| jog, law, tanul, vizsga, jogi | study | GLM-5 | Law, education |
| General/complex tasks | Multiple profiles | Various | Parallel execution |

## Orchestration Patterns

### Single Agent (simple tasks)
```bash
hermes --profile research -q "Keress rá: Zürich szállások 600€"
```

### Parallel Agents (complex tasks)
```bash
# Spawn multiple profiles in parallel
hermes --profile research -q "Keress szállásokat Zürichben" &
hermes --profile dev -q "Írj Python scriptet a foglalások összehasonlítására" &
wait
# Collect results and synthesize
```

### Sequential (dependent tasks)
```bash
# Step 1: Research
RESEARCH_RESULT=$(hermes --profile research -q "Milyen API-k vannak szállásfoglalásra?")
# Step 2: Dev uses research result
hermes --profile dev -q "Implementáld a következő API-t: $RESEARCH_RESULT"
```

## Implementation

### Option A: delegate_task (Recommended for Quick Tasks)
The native Hermes way to run parallel work within a single session:

```python
# Single task
delegate_task(goal="Keress szállásokat Zürichben 600€ körül")

# Parallel batch (up to 3 concurrent)
delegate_task(tasks=[
    {"goal": "Keress szállásokat Zürichben", "toolsets": ["web"]},
    {"goal": "Írj Python scriptet a foglalásokhoz", "toolsets": ["terminal", "file"]},
])
```

**Advantages:**
- Fast (5-15 seconds per task)
- Uses Hermes subagent system (same process)
- Supports up to 3 concurrent children (configurable via `delegation.max_concurrent_children`)
- Full tool access (web, terminal, file, browser)

### Option B: hermes chat -q (For Isolated Profiles)
Spawns a separate Hermes instance per profile:

```bash
hermes chat --profile research -q "task description"
```

**Use when:**
- Need profile-specific config (different model, skills, memory)
- Long-running autonomous tasks (10+ minutes)
- Need session persistence across restarts

**Limitations:**
- Slow startup (30-60 seconds per invocation)
- Loads ALL tools (browser, terminal, web, file)
- Timeout: 5+ minutes per profile

### Option C: bridge_v3.py (For Discord Visibility)
Custom Python script for Discord-based multi-agent collaboration:

```bash
cd ~/.hermes/discord-multi-agent
~/.hermes/.venv/bin/python3 bridge_v3.py
```

**Use when:**
- Want agents visible on Discord
- Need real-time interaction with agents
- Want persistent chat history

### Choosing the Right Approach

| Use Case | Approach | Speed | Isolation |
|----------|----------|-------|-----------|
| Quick parallel tasks | delegate_task | Fast (5-15s) | Low |
| Profile-specific work | hermes chat -q | Slow (30-60s) | High |
| Discord collaboration | bridge_v3.py | Medium | High |
| Scheduled tasks | cronjob tool | Variable | High |

### Transparency Rules (CRITICAL)

**Every orchestrator response MUST include:**

1. **Agent count header** — how many agents were spawned
2. **Per-agent summary** — what each agent did, how long it took
3. **Status per agent** — success/failure/interrupted
4. **Total time** — wall clock time for the whole operation

**Example format:**
```
🎯 Orchestrátor: 3 ágens párhuzamosan
├── Ágens 1 (Google Hotels): 562s ✅ → VISIONAPARTMENTS, Swiss Star Tower
├── Ágens 2 (Booking.com): 413s ❌ → UI hiba
└── Ágens 3 (Airbnb): 519s ✅ → 5 opció €391-€567
⏱️ Összesen: 563s (párhuzamos)
```

**Why this matters:** The user has no visibility into how many agents are working. Without this, they can't tell if the orchestrator is using 1 agent or 10. Always report the parallelism.

## Error Handling
- **delegate_task**: Auto-retries on failure, continues with other tasks
- **hermes chat -q**: Timeout per profile (configurable), manual retry
- **bridge_v3.py**: Built-in error handling and logging

---

## Pitfalls (learned 2026-05-06)

### 1. `hermes chat --profile` NOT `hermes --profile`
The correct syntax is `hermes chat --profile X -q "task"`, NOT `hermes --profile X -q "task"`. The `--profile` flag belongs to the `chat` subcommand, not the root command. Without `chat`, hermes treats the query as a subcommand name and fails.

### 2. Subprocess needs .env loaded explicitly
When spawning `hermes chat --profile X -q` from a Python script, the subprocess does NOT inherit the parent's `.env` variables. You must load them explicitly:

```python
import os
from pathlib import Path

env = os.environ.copy()
env_path = Path.home() / ".hermes" / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, _, value = line.partition('=')
            key, value = key.strip(), value.strip()
            if key and value:
                env[key] = value

proc = await asyncio.create_subprocess_shell(cmd, env=env, ...)
```

Without this, profiles get `HTTP 401: Invalid API key` errors.

### 3. TUI output cleaning required
`hermes chat -q` outputs TUI artifacts (ASCII art, box drawing, tool lists, progress bars). Clean before displaying:

```python
def clean_hermes_output(output: str) -> str:
    lines = output.split('\n')
    cleaned = []
    skip_until_empty = False
    for line in lines:
        if any(c in line for c in ['╭', '╮', '╯', '╰', '│', '─', '═']):
            skip_until_empty = True; continue
        if '⣀' in line or '⣴' in line or '⣿' in line:
            skip_until_empty = True; continue
        if 'Available Tools' in line or 'Hermes Agent v' in line:
            skip_until_empty = True; continue
        if any(x in line for x in ['ctx --', '⏲', 'K/', '%', 'MB', '░', '█', '▓', '▒']):
            continue
        if skip_until_empty and not line.strip():
            skip_until_empty = False; continue
        if skip_until_empty: continue
        if '⚠' in line or 'hermes setup' in line.lower(): continue
        cleaned.append(line)
    return '\n'.join(cleaned).strip()
```

### 4. Parallel `hermes chat -q` is SLOW
Each `hermes chat -q` invocation loads ALL tools (browser, terminal, web, file, etc.) — startup takes 30-60 seconds. Running 3 in parallel = 3× the overhead.

**Better approaches:**
- `delegate_task` with batch mode (5-15s per task, same process)
- `discord_task.py` to send tasks to bridge_v3.py bots (instant)
- `hermes chat -q` only for truly isolated, long-running tasks

### 5. Use venv python for scripts with aiohttp
System `python3` doesn't see packages installed in the Hermes venv. Always use:
```bash
~/.hermes/.venv/bin/python3 ~/.hermes/scripts/orchestrator.py
```

Or install globally: `uv pip install --python ~/.hermes/.venv/bin/python3 aiohttp`

### 6. Discord posting from orchestrator
Use `discord_task.py` to send tasks to Discord channels. The bridge_v3.py bots handle the actual work.

```bash
# Send task to #team with @research mention
~/.hermes/.venv/bin/python3 ~/.hermes/scripts/discord_task.py \
  --channel team --mention research "Keress szállásokat Zürichben"
```

### 7. Provide REAL links, not made-up URLs
When reporting search results, NEVER fabricate URLs. Use:
- Actual URLs captured during browsing
- Generic search URLs with proper parameters (Booking.com, Airbnb, Google Hotels)
- Or explicitly say "search for [name] on [platform]" instead of a fake link

User feedback: "Egyik link sem mukodik" — made-up URLs break trust.

## Tips

- **Keep tasks specific** — "Keress szállásokat Zürichben" not "Segíts Zürichbe utazni"
- **Use parallel for independent tasks** — research + dev can run simultaneously
- **Use sequential for dependent tasks** — dev needs research results first
- **Synthesize, don't concatenate** — combine insights, not raw output

## SOUL.md Files (Created 2026-05-06)

Every profile has a `~/.hermes/profiles/{agent}/SOUL.md` with Hungarian-language instructions:

| Profile | SOUL.md | Focus |
|---------|---------|-------|
| research | 1867 b | Forráselemzés, kutatás, szintézis |
| dev | 2049 b | Kódolás, scriptelés, API integráció |
| devops | 1804 b | Docker, CI/CD, infra, monitoring |
| news | 1690 b | Hírek, TLDR, aktuális események |
| study | 1951 b | Jogi tanulás, fogalmak magyarázata |
| general | 1936 b | Koordinátor, delegálás, szintézis |

Each SOUL.md contains: szerep leírás, kompetenciák, 5 lépéses munkamódszer, kommunikációs stílus, ajánlott eszközök, jó/rossz válasz példák.

## Scripts

| Script | Path | Purpose |
|--------|------|---------|
| `orchestrator.py` | `~/.hermes/scripts/orchestrator.py` | Multi-profile orchestrator with .env loading |
| `discord_task.py` | `~/.hermes/scripts/discord_task.py` | Send tasks to Discord channels |
| `discord_poster.py` | `~/.hermes/scripts/discord_poster.py` | Post results to Discord |

All scripts require venv python: `~/.hermes/.venv/bin/python3`

## Shared Memory Architecture (IMPLEMENTED — see discord-multi-agent skill for full details)

### 3-Layer Memory Model (LIVE)

| Layer | agent_id | Who writes | Who reads | Purpose |
|-------|----------|-----------|-----------|---------|
| 1 | `shared` | Any agent (via `scope="shared"`) | All agents | User preferences, system config, routing rules |
| 2 | `hermes` (default) | Default orchestrator | All + shared queries | Personal preferences, communication style |
| 3 | `dev`/`research`/... | Each specialist | That specialist only | Domain-specific knowledge |

### Hierarchical Read Pattern
Each agent reads shared + own memories via **dual search** (NOT `{"in": [...]}` — mem0 doesn't support it on agent_id):
1. `search(query, filters={user_id: "krisztian", agent_id: "shared"})`
2. `search(query, filters={user_id: "krisztian", agent_id: own_agent_id})`
3. Merge: shared first (organizational priority), then own specialist, deduped

### Implementation Status
- [x] Profile-specific `mem0.json` with `agent_id` matching profile name
- [x] `mem0_integration.py` SharedMemory class for bridge context injection
- [x] bridge_v3.py fact extraction at 3 points (specialist response, delegation result, escalation)
- [x] Bus CLI `delegate` + `context` commands with mem0 injection
- [x] 12 initial shared facts seeded in Qdrant
- [x] SOUL.md mem0 scope directives in all 7 gateway profiles
- [x] Gateway restart with mem0 plugin active

### Key Files
- Plugin: `~/.hermes/hermes-agent/plugins/memory/mem0/__init__.py` (_shared_search, scope param)
- Integration: `~/.hermes/discord-multi-agent/mem0_integration.py` (SharedMemory class)
- Bus CLI: `~/.hermes/discord-multi-agent/hermes_bus.py` (delegate/context commands)
- Init script: `~/.hermes/scripts/init_shared_mem0.py` (seed shared facts)

### Bus System (`hermes_bus.py`)
SQLite-based message bus for inter-agent communication. Located at `~/.hermes/discord-multi-agent/hermes_bus.py`.
- Supports: send, receive, complete, get_history, cleanup
- WAL-mode for concurrent access from multiple bridge processes
- Auto-cleanup: messages older than 24h pruned
- Status lifecycle: pending → in_progress → completed/failed

## Future Integrations

### Scrapling (Anti-bot scraping)
For sites that block Hermes browser tool (Booking.com, Cloudflare-protected):
```bash
pip install "scrapling[all]"
scrapling install
```
- Cloudflare bypass built-in (`solve_cloudflare=True`)
- Browser fingerprint spoofing
- MCP server for AI integration
- 46k+ GitHub stars

### hermes-watchdog (Zero-token monitoring)
For NER-Watch and other monitoring without token usage:
```bash
hermes plugins install LeventeNagy/hermes-watchdog
```
- Python checkers run locally (HTTP + SQLite)
- Only wakes agent when changes detected
- `notify` action = zero tokens
- GitHub, RSS, website monitoring
