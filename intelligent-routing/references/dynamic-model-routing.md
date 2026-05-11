# Dynamic Model Routing — Részletes Spec

## Krisztian eredeti koncepció (2026.05.03)

**Dispatcher-based, runtime model selection — nem statikus mint Shogun.**

### Core Insight: "Magas kidolgoz → Olcsó végrehajt"

```
BATCH feladat (pl. research cron)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Step 1: DRÁGA MODELL (Gemini 2.5 Pro, $0.015/1K)
  → Input: "kutass top 10 AI news"
  → Output: strukturált lista, source-ok, fontosság sorrend
  → Token: ~2000 in + ~500 out = $0.015

Step 2: OLCSÓ MODELL (minimax free)
  → Input: [Gemini output] + "írd 3 bekezdéses összefoglalót"
  → Output: végső summary Krisztian-nak
  → Token: ~500 in + ~200 out = $0.00

ÖSSZESEN: $0.015 / research
vs MONOLITHIC (csak Pro): ~$0.10-0.15 / research
MEGTAKARÍTÁS: 85-90%
```

### 4 Döntési Dimenzió

| Dimenzió | Értékek | Hatás |
|---|---|---|
| **Sürgősség** | azonnal / nem sürgős / batch | Mennyire drága modellt éri meg |
| **Komplexitás** | triviális / egyszerű / közepes / komplex / expert | Milyen kapacitás kell |
| **Költségkeret** | ingyenes / olcsó / bármennyi | Max token price |
| **Feladat típus** | research / kódolás / debug / kreatív / döntés | Melyik modell a legerősebb abban |

### Routing Decision Tree

```
feladat
  │
  ├─ URGENT?
  │   └─ Igen → legjobb elérhető (Claude Opus / Gemini Pro)
  │
  ├─ BATCH/AUTOMATIKUS?
  │   └─ Igen
  │       ├─ Magas modell: KIDOLGOZZA a lényeget/tervet
  │       └─ Olcsó modell: VÉGREHAJTJA
  │
  ├─ ISMERETLEN KOMPLEXITÁS?
  │   └─ Igen → Modellek MEGBESZÉLIK
  │       "én ezt nem tudom → @MODEL_B?"
  │       "szerintem @MODEL_C jobb lenne"
  │
  └─ MARGINÁLIS (bizonytalan)?
      └─ Drágább modell + extra time
```

### Self-Improving Loop

```
1. Feladat → dispatcher → route kiválasztás
2. Futtatás → eredmény (sikeres / nem sikeres)
3. routing_history.json frissítés
4. confidence score nő (3 sikeres után automatic)
5. Auto-discovery (heti cron):
   → Új modellek keresése
   → Benchmark futtatás
   → routing_config.yaml frissítés
6. Report Krisztian-nak Telegram-on
```

### Modellek Amiket Krisztian Használ

| Modell | Provider | Erősség | Ár | Státusz |
|--------|----------|---------|-----|---------|
| minimax-m2.5-free | OpenCode Zen | gyors, olcsó, egyszerű | $0 | ✅ Aktív |
| gemini-2.5-flash | OpenRouter | research, közepes | ~$0 | ✅ Van credit |
| gemini-2.5-pro | OpenRouter | deep reasoning, elemzés | $0.015/1K | ✅ |
| claude-sonnet-4 | OpenRouter | kódolás | $3/1K | ✅ |
| claude-opus-4 | OpenRouter | expert, debug | $15/1K | ⚠️ drága |
| vertex-ai/gemini-2.5-pro | GCP Vertex | deep reasoning | ADC auth | ✅ |
| copilot/gpt-4o | GitHub Copilot | kódolás | Copilot sub | ⚠️ token hiba |

### Copilot Token Probléma

**Probléma:** `ghp_*` token (klasszikus PAT) nem működik Copilot API-hoz.

**Kell:**
- `gho_*` — OAuth token
- `github_pat_*` — fine-grained PAT Copilot scope-pal
- `ghu_*` — GitHub App token

**Workaround:** Copilot CLI helyett OpenRouter Copilot proxy használata nem lehetséges.
→ Alternatíva: Claude/Copus/OpenRouter modellek kódolásra.

### Auto-Discovery Cron

```bash
# Vasárnap 03:00 — minden héten
0 3 * * 0  python3 ~/.hermes/scripts/model_discovery.py --scan --benchmark --update
```

**model_discovery.py működése:**
1. `curl https://openrouter.ai/models` → top models JSON
2. Filter: price < $0.01/1K, benchmark > 40
3. Compare to Krisztian current models
4. Update `~/.hermes/routing_config.yaml`
5. Telegram: "3 új modell: [lista]"

---

## Kapcsolódó Források

- ArXiv 2508.08322 — "Context Engineering for Multi-Agent LLM Code Assistants"
- OpenRouter API docs — model pricing, benchmarks
- OpenCode Zen — minimax-m2.5-free endpoint
