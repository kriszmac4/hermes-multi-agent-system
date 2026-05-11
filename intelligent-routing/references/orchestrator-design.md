# Orchestrator Design Reference

## Krisztian's Vision (2026.05.03)

Multi-agent team where specialized LLMs work together like a development team:
- Different agents in different chat channels (Telegram threads / Discord)
- Each has a specialized model
- They can call each other's work
- Parallel execution — not sequential
- Fastest-first prioritization (agile sprint logic)
- Round-robin review

## State of the Art

### arXiv 2508.08322 — "Context Engineering for Multi-Agent LLM Code Assistants"
- Intent Translator → semantic retrieval → NotebookLM → Claude Code multi-agent
- Validates: multi-agent code gen > single-agent
- Compared: CodePlan, MASAI, HyperAgent
- Key insight: role decomposition + targeted context injection

### GitHub: ZSeven-W/openpencil (2.5k ⭐)
- "Design-as-Code" — prompt → live canvas UI
- Agent Teams feature (concurrent agents)
- MCP server native
- monorepo: apps/, packages/, scripts/

## Proposed Agent Roles

| Agent | Model | Specialty | Tools |
|-------|-------|-----------|-------|
| Orchestrator | minimax-m2.5-free | dispatch, priority, coordination | delegate_task |
| Researcher | nemotron-3-super | web search, analysis, options | Brave/ArXiv/Tavily MCP |
| Coder | copilot/gpt-4o | code write, refactor, test | terminal, file, gh |
| Reviewer | claude-sonnet | critique, quality, security | terminal, gh |
| Architect | nemotron-3-super | system design, patterns | file, research |

## Shared Context Bus

```
OpenSpace (~/.openspace/openspace.db):
- task_queue: prioritization order
- agent_outputs: {researcher: {}, coder: {}, reviewer: {}}
- shared_memory: cross-agent context
- skill_registry: what each agent can do
```

## Implementation Phases

### Phase 1: Dispatcher Script
```python
# ~/.hermes/scripts/orchestrator.py
# - Agent registry (model, capabilities, toolsets)
# - Task queue with priority
# - Spawn agents via delegate_task()
# - Aggregate outputs
```

### Phase 2: Shared Context
- OpenSpace already has `execution_analyses` table
- Extend to `agent_outputs` table
- Each agent writes output → other agents read

### Phase 3: Priority Engine
- Fastest-first: track completion time per agent
- Reorder queue after each completion
- "Reviewer → if code is ready, review now"

### Phase 4: Channel Mapping
- Telegram: thread per task
- Discord: channel per agent
- Hermes: agent per task

## Open Questions

1. **Sync vs async**: parallel agents need async coordination
2. **Conflict resolution**: two agents disagree → who decides?
3. **Context window**: shared context must not exceed token limits
4. **Cost tracking**: each agent uses different API → track per-agent cost

## Related

- `deep-research-scheduler` skill — Researcher agent backend
- `autonomous-ai-agents` skill — subagent spawning patterns
- OpenSpace skill — shared context store
