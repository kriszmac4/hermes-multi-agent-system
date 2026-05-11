---
name: intelligent-routing
description: "Intelligens modell router — feladat komplexitás alapján automatikusan választ modelleket"
version: 1.0.0
author: Hermes Agent
tags: [routing, multi-model, delegation, optimization]
---

# Intelligent Routing Skill

Automatikusan elemzi a feladat komplexitását és a legmegfelelőbb modellhez irányítja.

## Routing Tiers (2026.05.11 — Dual Provider)

**Két provider, két rate limit pool:**
- **opencode-go** ($10/hó flat) → reasoning modellek: GLM-5.1, DS-V4-Pro, DS-V4-Flash, MiniMax-M2.5
- **opencode-zen** (ingyenes, saját rate limit) → MiniMax-M2.5-free egyszerű feladatokhoz

⚠️ **DESIGN SZABÁLY:** MiniMax-M2.5-free marad opencode-zen-en! Két külön pool = kisebb esélye a rate limit kimerülésnek. Ne mozgass mindent opencode-go-ra.

| Tier | Complexity | Model | Provider | Use case |
|------|-----------|-------|----------|----------|
| `trivial` | Egyszerű kérdés | — | — | Hermes válaszol közvetlenül |
| `simple` | Keresés, lista, cron script | `minimax-m2.5-free` | opencode-zen | Gyors válaszok, cron, Discord botok |
| `moderate` | Kódolás, elemzés | `deepseek-v4-flash` | opencode-go | Batch feladatok, Discord dev/news/fitness |
| `complex` | Architektúra, debug, koordináció | `glm-5.1` | opencode-go | Bridge general, research, study |
| `expert` | Research, tervezés | `mimo-v2.5-pro` vagy `glm-5.1` | opencode-go | Plan mode + extended timeout |

**Krisztian szabály:** Mindig plan mode nagy architektúránál. Okos modell (complex/expert) kidolgozza → átadja gyorsabb modellnek (simple/moderate) végrehajtásra.

### Discord Bridge AGENT_MODELS (bridge_v3.py)

```python
AGENT_MODELS = {
    "general": "glm-5.1",        # Koordinátor, reasoning
    "research": "glm-5.1",       # Kutatás, mély elemzés
    "study": "glm-5",            # Tanulás, jegyzet
    "dev": "deepseek-v4-flash",  # Kódolás, gyors
    "news": "deepseek-v4-flash", # Hírek, összefoglaló
    "fitness": "deepseek-v4-flash", # Edzésterv, gyors
    "devops": "minimax-m2.5",    # Infra, közepes
}
```

### Cron Modell Kiosztás

| Cron | Modell | Provider | Indoklás |
|------|--------|----------|----------|
| research-evening/night-batch, research-scheduler-heartbeat, ner-watch-digest | `glm-5.1` | opencode-go | LLM reasoning kell |
| hermes-skill-evolution, task-queue-monitor, link-saver, heti jelentés, ncore-login, upstream-monitor, ner-watch-watchdog | `minimax-m2.5-free` | opencode-zen | Egyszerű script, kevésbé reasoning |
| **Fallback** (ha MiniMax rate limit) | `deepseek-v4-flash` | opencode-go | Flat rate, nem kerül extra pénzbe |

**Elérhető modellek (OpenCode Go/Zen):**
```bash
curl -s https://opencode.ai/zen/go/v1/models | python3 -c "import sys,json; [print(m['id']) for m in json.load(sys.stdin).get('data',[])]"
```
Known: `deepseek-v4-pro`, `deepseek-v4-flash`, `minimax-m2.7`, `minimax-m2.5`, `kimi-k2.6`, `kimi-k2.5`, `glm-5.1`, `glm-5`, `qwen3.6-plus`, `qwen3.5-plus`, `mimo-v2-pro`, `mimo-v2-omni`, `mimo-v2.5-pro`, `mimo-v2.5`

### ⚠️ PITFALL: OpenCode Go Usage API

OpenCode Go **nincs token usage/billing API-ja**. Az `/models` endpoint működik, de `/usage`, `/billing`, `/dashboard` mind 404. A flat rate előfizetés ($10/hó) miatt ez nem kritikus, de monitoringra saját naplózás kell a bridge-be.

### ⚠️ PITFALL: MiniMax-M2.5-free Provider mixer

MiniMax-M2.5-free elérhető **mindkét provideren** (opencode-go és opencode-zen). A cronoké **opencode-zen**, mert külön rate limit pool. Ha opencode-go-ra mozgatod, kimerítheted a GLM-5.1 rate limitet (880/5h). **Ne mozgasd opencode-go-ra Krisztian explicit jóváhagyása nélkül!** Ez volt már probléma — adminisztratívan átmásoltuk opencode-go-ra, de Krisztian visszaállította mert az intelligens routing szándékosan használ külön pool-t.

### ⚠️ PITFALL: mem0 model választás

mem0 fakt-kinyerés **NEM reasoning feladat**. Használj `deepseek-v4-flash`-et, nem `glm-5.1`-et. A GLM-5.1 pazarló lenne fakt-kinyerésre és kimerítheti a rate limitet (880/5h).
- Global `~/.hermes/mem0.json`: `deepseek-v4-flash` @ opencode-go ✅
- Per-profile `~/.hermes/profiles/*/mem0.json`: `deepseek-v4-flash` @ opencode-go ✅

```
┌─ Feladat bejött
│
├─ TRIVIAL (egyszerű kérdés)
│   → Én válaszolok (max 50ms)
│
├─ SIMPLE (lista, keresés, definition)
│   → minimax-m2.5-free — delegate_task
│
├─ MODERATE (kódolás, elemzés, írás)
│   → deepseek-v4-flash — delegate_task
│
├─ COMPLEX (architektúra, debug, multi-step)
│   → deepseek-v4-pro — plan mode + delegate_task
│
└─ EXPERT (research, tervezés, innováció)
    → mimo-v2.5-pro — plan mode + delegate_task + extra time
```

## Complexity Markerek

### TRIVIAL (<5 szó, kérdő)
```python
TRIVIAL_KEYWORDS = ["mi az", "miért", "hogyan", "mikor", "hol", "lista",
                    "mutasd", "mi a", "define", "what is", "how to", "list"]
# Válaszolok közvetlenül, nem delegálok
```

### SIMPLE (keresés, listázás)
```python
SIMPLE_KEYWORDS = ["keress", "találj", "részletek", "info", "search",
                   "find", "details", "lookup", "read", "fetch"]
# delegate_task → fast_model
```

### MODERATE (kódolás, írás, elemzés)
```python
MODERATE_KEYWORDS = ["írd meg", "szerkeszd", "elemezd", "fordítsd",
                     "code", "write", "edit", "analyze", "compile",
                     "build", "convert", "refactor", "debug", "fix"]
# delegate_task → medium_model
```

### COMPLEX (architektúra, debug, multi-file)
```python
COMPLEX_KEYWORDS = ["tervezd", "architektúra", "rendszer", "redesign",
                    "architecture", "system", "multi-file", "migrate",
                    "optimize performance", "security audit"]
# delegate_task → strong_model
```

### EXPERT (research, tervezés, innováció)
```python
EXPERT_KEYWORDS = ["kutass", "vizsgáld", "tanulmány", "research",
                   "benchmark", "compare", "evaluate", "novel approach",
                   "paper", "experiment", "HBO"]
# delegate_task → expert_model + extended timeout
```

# Modell Konfiguráció (frissítve: 2026.05.02)

## KONKRÉT MODELLEK AMIKET HASZNÁLSZ (OpenCode Go):

| Modell | Provider | Tier | Státusz |
|--------|----------|------|---------|
| — | — | `trivial` | ✅ Én válaszolok |
| `minimax-m2.5-free` | opencode-go | `simple` | ✅ Aktív (Discord + gyors) |
| `deepseek-v4-flash` | opencode-go | `moderate` | ✅ Aktív (batch) |
| `deepseek-v4-pro` | opencode-go | `complex` | ✅ Aktív (plan mode, reasoning) |
| `mimo-v2.5-pro` | opencode-go | `expert` | ✅ Aktív (research) |

**Provider config (global):**
```yaml
model:
  default: deepseek-v4-pro
  provider: opencode-go
  base_url: https://opencode.ai/zen/go/v1
providers:
  opencode-go:
    display_name: OpenCode Go
    base_url: https://opencode.ai/zen/go/v1
    api_key: ${OPENCODE_GO_API_KEY}
    api_mode: chat_completions
    default_model: minimax-m2.5-free
```

**Discord profile config:**
```yaml
# ~/.hermes/profiles/<name>/config.yaml
model:
  default: minimax-m2.5-free
  provider: opencode-go
```

### Vertex AI Gemini (GCP) — auxiliary vision/extract:

```bash
# Service Account JSON: ~/.config/gcloud/application_default_credentials.json
# Project: utility-meter-reader-492216
# Vertex AI API enabled
```

In config.yaml under `providers`:
```yaml
vertex-ai:
  display_name: Vertex AI (Gemini)
  base_url: https://us-central1-aiplatform.googleapis.com/v1beta1/projects/utility-meter-reader-492216/locations/us-central1/publishers/google
  api_key: ADC
  api_mode: chat_completions
  default_model: gemini-3.1-pro-preview
```

---

## Beállítás Queue (prioritás szerint):

1. **GitHub Copilot CLI** — `gh extension install github/copilot-cli`
2. **Vertex AI Gemini** — GCP Service Account → `.env`-be

```yaml
routing:
  models:
    trivial:  null
    simple:   "deepseek-v4-pro via opencode-go"    # Fallback: most capable
    moderate: "deepseek-v4-flash via opencode-go"  # Fast coding
    complex:  "deepseek-v4-pro via opencode-go"    # Reasoning, planning
    expert:   "mimo-v2.5-pro via opencode-go"     # Research, deep analysis
  fallback: "minimax-m2.5-free via opencode-go"   # Cheapest, fastest
  timeout:
    trivial:  0
    simple:   30
    moderate: 120
    complex:  300
    expert:   600
```

## Beállítás Queue (prioritás szerint):

1. **Groq** — Regisztrálj groq.com → API Key → `.env`-be (`GROQ_API_KEY`)
2. **GitHub Copilot CLI** — `brew install gh && gh extension install github/copilot-cli`
3. **Vertex AI Gemini** — GCP Service Account JSON → `~/.hermes/vertex-sa.json` + `.env`

## Használat

### Automatikus routing (betöltés után)
```
1. Betöltöm a skillet → /skill intelligent-routing
2. Küldesz egy feladatot
3. Automatikusan elemzem és delegálom
```

### Kézi modell választás
```
@fast: "mi az a Python?"
@medium: "írd meg a FastAPI auth-ot"
@strong: "tervezz egy microservices architektúrát"
@expert: "kutass és hasonlítsd össze a RAG implementációkat"
```

### Override flag-ek
```
# Mindig erős modellt akarok
@force:strong "simple question"  → strong modell

# Gyors válasz kell
@force:fast "complex code"       → fast modell (nem ajánlott)
```

## Delegation Wrapper

```python
def route_and_delegate(task: str, context: str = "") -> str:
    """
    1. Analyze complexity
    2. Select appropriate model
    3. Delegate with timeout
    4. Return result
    """
    complexity = analyze_complexity(task)
    model = get_model_for_complexity(complexity)
    timeout = get_timeout_for_complexity(complexity)

    return delegate_task(
        goal=f"{context}\n\nTask: {task}",
        model=model,
        timeout=timeout
    )
```

## Teljesítmény Statisztika

| Modell | Latencia | Költség | Jó feladathoz |
|--------|---------|---------|--------------|
| minimax-m2.5-free | ~300ms | $0 | Trivial/Simple (Discord) |
| deepseek-v4-flash | ~1s | $0 | Moderate (batch) |
| deepseek-v4-pro | ~5s | Reasoning token | Complex (plan, debug) |
| mimo-v2.5-pro | ~3s | OK | Expert (research) |

**Tipikus megtakarítás:** Plan mode → okos modell tervez ($0.015) → gyors modell végrehajt ($0) = 90%+ spórolás az "egész feladat drága modellel" helyett.

---

## ⚡ Krisztian Dinamikus Modell Rendszer (2026.05.03)

**Kulcs különbség a Shogun-hoz képest:** Runtime döntés, nem statikus routing.

### Dispatcher Logika

```
Feladat beérkezik
      ↓
  DISPATCHER
  (Orchestrator)
      ↓ értékeli:
      │
      ├── SÜRGŐS?
      │   └── Igen → Magas modell AZONNAL
      │
      ├── BATCH / AUTOMATIKUS (reminder cron, éjszakai run)?
      │   └── Igen → Magas modell KIDOLGOZZA a lényeget/tervet
      │               ↓
      │           Olcsó modell VÉGREHAJTJA
      │
      ├── NEM SÜRGŐS + ISMERETLEN komplexitás?
      │   └── Modellek MEGBESZÉLIK: "ki tudja jobban?"
      │
      └── BIZTONSÁGI MARGINÁLIS (alig döntött)?
          └── Drágább modell, extra time
```

### Döntési Mátrix

| Feladat típusa | Sürgősség | Modell 1 (Kidolgozza) | Modell 2 (Végrehajtja) | Miért? |
|---|---|---|---|---|
| Research | Batch (cron) | Gemini 2.5 Pro (értelmezi) | minimax (összefoglalja) | Pro = $0.015/1K, minimax = ingyenes |
| Kódolás | Sürgős | Claude Sonnet (implementál) | — | Gyors kell, legjobb kell |
| Kódolás | Éjszakai batch | Claude Sonnet (kidolgozza) | Gemini Flash (leprogramozza) | Spórolás, Sonnet nem dolgozik éjszaka |
| Debug | Sürgős | Claude Opus (elemzi) | — | Mély reasoning kell |
| Egyszerű kérdés | Sürgős | Én (Hermes) | — | Trivial, nincs delegálás |
| Kreatív írás | Nem sürgős | GPT-4o (ötletel) | — | Kreativitás számít |
| Döntés | — | Multi-model vote | — | Modellek szavaznak |

### Miért nem statikus (Shogun = mindig Claude Code)?

- **Nem mindegyik modell egyformán jó mindenben**
  - Van ami GYORSABB (Gemini Flash: 50ms vs Claude: 800ms)
  - Van ami KREATIVÍVABB (GPT-4o vs Claude)
  - Van ami JOBB KÓDOLÁSBAN (Claude vs Gemini)
  - Van ami OLCSÓBB batch-hez (minimax ingyenes)
- **Költséghatékonyság** — nem mindig kell a legdrágább
- **Shogun: minden feladathoz ugyanaz az agent** — ez pazarlás triviális dolgokra

### Modell Átadás / Megbeszélés

```python
# Ha Modell A nem tud valamit:
"Én ezt a részt nem tudom jól — @MODEL_B, te tudod?"

# Ha Modell A bizonytalan:
"@MODEL_B, @MODEL_C — ti mit gondoltok erről a megközelítésről?"

# Ha Modell A kész, átadja Modell B-nek:
"OK, az architektúra kész. @MODEL_B, implementáld a részleteket."
```

### 🎯 Önfejlesztő Rendszer

```python
# routing_history.json — automatikusan épül
{
  "task_pattern": "research + summary",
  "optimal_route": {
    "elaborator": "gemini-2.5-pro",
    "executor": "minimax-m2.5-free"
  },
  "confidence": 0.85,      # 2/3 sikeres futás után nő
  "attempts": 3,
  "successes": 2,
  "learned": "2026-05-03"
}

# 2-3 sikeres futás után:
# → Automatikusan ezt a route-ot választja
# → Nem kérdez rá, nem gondolkodik
```

### 🌐 Auto-Discovery (heti background job)

Krisztian fontosította: az agentnek NEM ELÉG csak tanulni — aktívan kutasson hetente új modelleket.

```python
# model_discovery.py — heti cron, nem Krisztian indítja
"""
Heti feladat:
1. Listázd az elérhető modelleket minden provider-től
2. Keress új modelleket (arXiv, model release news, OpenRouter trending)
3. Értékeld: mi jobb mint amit most használunk?
4. Ha igen: frissítsd a routing_history.json-t
5. Javaslatot küldj Telegram-ra

Providers:
- Vertex AI: client.models.list() → Gemini modellek
- OpenRouter: API endpoint
- GitHub Copilot: copilot CLI
"""

# Vertex AI model discovery:
~/.hermes/.venv/bin/python3 -c "
from google import genai
client = genai.Client(vertexai=True, project='utility-meter-reader-492216', location='us-central1')
for m in client.models.list():
    if 'gemini' in m.name.lower():
        print(m.name)
"
```

**Miért fontos ez Krisztian-nak:**
- Új modellek jelennek meg folyamatosan
- Ami ma a legjobb, holnap lehet olcsóbb/better
- Az agent nem vár a user-re hogy megtalálja

**Status: NEM IMPLEMENTÁLVA** — Krisztian kérte, soron következő feladat.

### 🤖 Auto-Discovery: Heti Model Benchmark

**Cél:** A dispatcher NEM csak tanul a múltból — AKTÍVAN kutasson új modelleket és benchmarkoljon.

```
HETI CRON JOB (vasárnap hajnal)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. ARXIV / HUGGINGFACE KERESÉS
   → "top openrouter models 2026"
   → "best coding model benchmark"
   → "cheapest large language model"

2. OPENROUTER TOP LISTA LETÖLTÉS
   → curl openrouter.ai/models
   → filter: ár < $0.01/1K token
   → filter: benchmark score > 40

3. KRISZTIAN MODELLEI ÖSSZEHASONLÍTÁS
   → Jelenlegi: gemini-2.5-pro, minimax-m2.5-free, claude-sonnet
   → Új jelöltek: van-e jobb/olcsóbb/gyorsabb?

4. ROUTING TÁBLÁZAT FRISSÍTÉS
   → routing_config.yaml update
   → Új modellek auto-hozzáadás
   → Régi modellek archival (ha újabb jobb)

5. REPORT KRISTZIAN-NAK (Telegram)
   → "5 új modell érkezett, 2 releváns"
   → "TOP SHELF 2026" összefoglaló
```

**Cron parancs:**
```bash
hermes cron create \
  --name "model-auto-discovery" \
  --prompt "python3 ~/.hermes/scripts/model_discovery.py --scan --benchmark --update-routes --report" \
  --schedule "0 3 * * 0" \
  --deliver telegram \
  --skills intelligent-routing
```

**Script: `model_discovery.py`** — MIT KELL MÉG ÍRNI
→ OpenRouter API → top models
→ Local benchmark (feladat típusonként)
→ Config frissítés
→ Telegram report

Lásd: `scripts/model_discovery.py` (stubs kész, config frissítés TODO)

### Key Insight: "Magas kidolgoz → Alacsony végrehajt"

```
BATCH AUTomatikus RUN (pl. reggeli research)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Magas modell: GEMINI 2.5 PRO
  → "Kutatás: top 10 AI news"
  → Output: strukturált lista, source-ok, fontosság sorrend
  → Token: ~2000 input, ~500 output = $0.015

Olcsó modell: MINIMAX FREE
  → "Olvasd el a Gemini output-ját, írj 3 bekezdéses összefoglalót"
  → Token: ~500 input, ~200 output = $0.00

ÖSSZESEN: $0.015 / research (nem $0.15 ha csak Pro-t használnál)
MEGTAKARÍTÁS: ~90%
```

## Legacy: Multi-Agent Orchestration (2026.05.02)

Régi koncepció — az új Krisztian rendszer felülírja:

### Architektúra

```
┌─ KRISTIAN / ORCHESTRATOR ────────────────────────────┐
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ RESEARCHER   │  │  CODER       │  │  REVIEWER    │  │
│  │ (Nemotron)   │  │ (Copilot)    │  │ (Claude)     │  │
│  │               │  │              │  │              │  │
│  │ - web search  │  │ - code write │  │ - critique   │  │
│  │ - analysis    │  │ - refactor   │  │ - quality     │  │
│  │ - options     │  │ - test       │  │ - security   │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │
│         │                  │                  │          │
│         └──────────────────┼──────────────────┘          │
│                            ▼                            │
│               ┌────────────────────────┐                │
│               │  SHARED CONTEXT BUS    │                │
│               │  (OpenSpace store)     │                │
│               │  research_output       │                │
│               │  code_snippets         │                │
│               │  review_comments       │                │
│               └────────────────────────┘                │
│                            │                            │
│                            ▼                            │
│               ┌────────────────────────┐                │
│               │  PRIORITY SCRUM       │                │
│               │  Fastest-first       │                │
│               │  Reorder by speed    │                │
│               └────────────────────────┘                │
└──────────────────────────────────────────────────────────┘
```

### Kulcs Jellemzők

1. **Dedikált csatornák** — minden agent külön chatben (Telegram thread / Discord channel)
2. **Specializált LLM-ek** — Researcher=Nemotron, Coder=Copilot/GPT-4o, Reviewer=Claude
3. **Párhuzamos futás** — minden agent egyszerre dolgozik, nem szekvenciálisan
4. **Cross-referencing** — Agent A meghívja Agent B munkáját: "használd a Researcher output-ját"
5. **Fastest-first** — ha valamelyik kész → azt fejlesztjük le először (scrum sprint logika)
6. **Round-robin review** — minden kódot review-ol a Reviewer agent

### Meglévő Integrációk

- `research_scheduler.py` — Researcher agent backend (lásd: `deep-research-scheduler` skill)
- OpenSpace store — közös context bus (lásd: OpenSpace skill)
- delegate_task() — már támogatja a párhuzamos agent spawn-t
- MCP szerverek (Brave/ArXiv/Tavily) — Researcher tool support

### Research Baseline

> **Context Engineering for Multi-Agent LLM Code Assistants** (arXiv 2508.08322, 2025)
> Intent Translator → domain knowledge → NotebookLM → Claude Code multi-agent
> State-of-the-art: CodePlan, MASAI, HyperAgent
> [🔗 https://arxiv.org/abs/2508.08322](https://arxiv.org/abs/2508.08322)

Ez a paper validates Krisztian ötletét — multi-agent code generation jobban teljesít mint single-agent.
A különbség: Krisztian hozzáadja a **fastest-first sprint prioritizálást** és a **dedikált csatornákat** — ez újdonság.

### Következő Lépés

1. Orchestrator dispatcher script írása (Python)
2. Agent registry: melyik agent mit tud, milyen modellel
3. Telegram thread-ek létrehozása (vagy Discord channels)
4. Priority queue implementáció (fastest-first)
5. Cross-agent output passing

Lásd: `references/dynamic-model-routing.md` (Krisztian teljes spec, decision tree, self-improving loop, Copilot token pitfall)

## ⚠️ PITFALL: Web Keresés Korlátai

### Nem működik:
- **Google/TripAdvisor/Yelp** — JavaScript renderelést használnak, curl nem elég
- **DuckDuckGo API** — nem ad vissza használható restaurant/termék adatokat
- **Browser tool** — Node.js kell, nincs telepítve

### Működik:
- **Wikipedia API** — strukturált adatok
- **DDG Lite (text mode)** — csak ha a HTML parser elég, de instabil
- **User tudása/memóriája** — a legjobb forrás sok dologra

### Megoldás:
1. Ha web keresés kell → mondd a usernek hogy nézze meg Google Maps-en
2. Ha én fontos infót tudok → használom a tudásom
3. Ha critical → javasold a Node.js telepítését

### Node.js Telepítés (ha szükséges):
```bash
# Linux/WSL
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

# Ellenőrzés
node --version
npm --version
```

## Teljesítmény Statisztika

> **Model configs, delegation examples, and token estimates:** `references/model-configs.md`
