# Orchestrator Architecture Patterns

Three approaches for multi-agent orchestration in Hermes, each with different trade-offs.

## Pattern 1: delegate_task (Recommended for Quick Tasks)

**How it works:** Spawns subagents within the current Hermes session. Each subagent gets its own conversation, tools, and execution context.

```python
# Single task
delegate_task(goal="Keress szállásokat Zürichben 600€ körül")

# Parallel batch (up to 3 concurrent by default)
delegate_task(tasks=[
    {"goal": "Keress szállásokat Zürichben", "toolsets": ["web"]},
    {"goal": "Írj Python scriptet a foglalásokhoz", "toolsets": ["terminal", "file"]},
])
```

**Advantages:**
- Fast startup (5-15 seconds per task)
- Full tool access (web, terminal, file, browser)
- Built-in error handling and retry
- Results come back as structured data

**Limitations:**
- Max 3 concurrent children (configurable via `delegation.max_concurrent_children`)
- Subagents die when parent session ends
- No persistent memory across sessions

**When to use:** Quick parallel research, code generation, web searches, file operations.

---

## Pattern 2: hermes chat --profile X -q (For Isolated Work)

**How it works:** Spawns a completely separate Hermes process with its own profile (model, config, memory, skills).

```bash
# One-shot, non-interactive
hermes chat --profile research -q "Keress szállásokat Zürichben"

# Background (long-running)
hermes chat --profile research -q "task" &
```

**Advantages:**
- Full profile isolation (different model, memory, skills)
- Persistent sessions (survives parent restart)
- Can run for hours/days
- Each profile has its own tool configuration

**Limitations:**
- Slow startup (30-60 seconds — loads ALL tools)
- Requires .env loading for API keys
- TUI output needs cleaning
- No built-in parallel execution

**When to use:** Long-running autonomous tasks, profile-specific work, tasks that need persistent state.

**Critical pitfall:** Use `hermes chat --profile X -q`, NOT `hermes --profile X -q`.

---

## Pattern 3: bridge_v3.py (For Discord Visibility)

**How it works:** Custom Python script that runs multiple Discord bots, each with its own model and personality. Bots respond to messages in Discord channels.

```bash
cd ~/.hermes/discord-multi-agent
~/.hermes/.venv/bin/python3 bridge_v3.py
```

**Advantages:**
- Visual separation (each agent has its own Discord channel)
- Real-time interaction with agents
- Persistent chat history in Discord
- Multi-model support (different model per agent)
- Context passing between agents
- TaskTracker integration

**Limitations:**
- Requires Discord bot tokens
- More complex setup
- Custom code maintenance

**When to use:** When you want agents visible on Discord, need real-time interaction, or want persistent chat history.

---

## Choosing the Right Pattern

| Use Case | Pattern | Speed | Isolation |
|----------|---------|-------|-----------|
| Quick parallel tasks | delegate_task | Fast (5-15s) | Low |
| Profile-specific work | hermes chat -q | Slow (30-60s) | High |
| Discord collaboration | bridge_v3.py | Medium | High |
| Long autonomous missions | hermes chat -q | Slow | High |
| Real-time team visibility | bridge_v3.py | Medium | High |

## Combining Patterns

The orchestrator can use multiple patterns together:

```
Krisztian (Telegram)
    ↓
[Hermes Gateway]
    ├── delegate_task → Quick parallel research (5-15s)
    ├── discord_task.py → Send task to Discord bots
    └── hermes chat --profile X -q → Long autonomous work
    ↓
[Results synthesized → Krisztian]
```

## Scripts

- `scripts/orchestrator.py` — Multi-profile orchestrator with .env loading and TUI cleaning
- `scripts/discord_task.py` — Send tasks to Discord channels for bridge_v3.py bots
