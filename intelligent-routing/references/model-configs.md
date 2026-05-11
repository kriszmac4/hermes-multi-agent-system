# Routing Reference

## Free Tier Models (2024-2025)

| Provider | Model | Context | Cost | Best For |
|----------|-------|---------|------|----------|
| **Groq** | `llama-3.1-8b-instant` | 128K | FREE | Trivial/Simple |
| **Groq** | `llama-3.3-70b-versatile` | 128K | FREE | Moderate (kódolás, elemzés) |
| **Groq** | `mixtral-8x7b-32768` | 32K | FREE | Fallback medium |
| **OpenRouter** | `anthropic/claude-haiku-3.5` | 200K | ~$0.80/1M | Complex |
| **OpenRouter** | `anthropic/claude-sonnet-4` | 200K | ~$3/1M | Expert |
| **Google** | `gemini-2.0-flash` | 1M | FREE | Simple/Cheap |
| **OpenAI** | `gpt-4o-mini` | 128K | ~$0.15/1M | Fast medium |

## Groq Setup (Priority — free + fast)

```bash
# Get API key: https://console.groq.com/keys
hermes auth add  # then paste key

# Or manually in .env:
GROQ_API_KEY=gsk_xxxx
```

## OpenRouter Setup (Credit needed)

```bash
# Get API key: https://openrouter.ai/keys
hermes auth add

# Or manually in .env:
OPENROUTER_API_KEY=sk-or-v1-xxxx
```

## Working Routing Config

```yaml
# ~/.hermes/config.yaml — add under existing config
delegation:
  model: groq/llama-3.1-8b-instant  # Default alagent modell
  provider: groq
  max_iterations: 50

# Vagy dinamikusan, a route_task.py output alapján:
# trivial  → agent maga válaszol (timeout=0)
# simple   → groq/llama-3.1-8b-instant (timeout=30)
# moderate → groq/llama-3.3-70b-versatile (timeout=120)
# complex  → openrouter/anthropic/claude-haiku-3.5 (timeout=300)
# expert   → openrouter/anthropic/claude-sonnet-4 (timeout=600)
```

## Delegation Call Examples

```python
# Egyszerű feladat → Groq 8B
delegate_task(
    goal="List the files in the current directory",
    model="groq/llama-3.1-8b-instant",
    timeout=30
)

# Komplex feladat → Claude Haiku
delegate_task(
    goal="Debug why the API returns 500 on /users endpoint",
    model="openrouter/anthropic/claude-haiku-3.5",
    timeout=300
)

# Expert feladat → Claude Sonnet
delegate_task(
    goal="Research and compare RAG implementations for production use. Write a detailed analysis.",
    model="openrouter/anthropic/claude-sonnet-4",
    timeout=600
)
```

## Token Estimation

| Task Type | Est. Input | Est. Output | Total |
|-----------|-----------|-------------|-------|
| Egyszerű kérdés | 100 | 200 | 300 |
| Kód generálás | 500 | 1500 | 2000 |
| Architektúra terv | 800 | 3000 | 4000 |
| Research összefoglaló | 1000 | 4000 | 5000 |

**Cost estimate** (Groq free tier):
- ~5,000 trivial/simple tasks = ~$0
- ~500 moderate tasks = ~$0
- Complex/Expert = OpenRouter credit only

## Routing Accuracy Tips

- Hungarian keywords in patterns → catch domestic language queries
- Multi-word patterns (e.g., "írd meg a") → more specific, less false positives
- Trivial detection: short (<5 words) + question mark → agent handles directly
- Default to `moderate` if no pattern matches → safe middle ground
- Test new patterns with: `python3 scripts/route_task.py "your test query"`
