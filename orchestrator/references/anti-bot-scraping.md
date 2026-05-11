# Anti-Bot Scraping Patterns

## Problem
Booking.com, Cloudflare-protected sites, and other anti-bot systems block the Hermes browser tool.

## Solution: Scrapling
GitHub: https://github.com/D4Vinci/Scrapling (46k+ stars)

### Installation
```bash
pip install "scrapling[all]"
scrapling install  # Download browsers
```

### Key Features
- **Cloudflare bypass**: `solve_cloudflare=True` flag
- **Browser fingerprint spoofing**: Canvas, WebGL, Audio context
- **TLS fingerprint impersonation**: Chrome/Firefox patterns
- **Adaptive element tracking**: Auto-finds elements after site changes
- **MCP server**: Built-in AI integration (`pip install "scrapling[ai]"`)

### Usage in Hermes
```python
# In a script or terminal tool
from scrapling import StealthyFetcher

fetcher = StealthyFetcher()
page = await fetcher.fetch(
    "https://www.booking.com/searchresults.html?ss=Zurich",
    solve_cloudflare=True
)
# Parse results...
```

### When to Use
- Booking.com searches (aggressive bot detection)
- Cloudflare-protected sites
- Sites that block headless browsers
- When you need reliable scraping without proxy rotation

### vs. Hermes Browser Tool
| Feature | Hermes Browser | Scrapling |
|---------|---------------|-----------|
| Cloudflare bypass | ❌ | ✅ |
| Fingerprint spoofing | ❌ | ✅ |
| Adaptive tracking | ❌ | ✅ |
| MCP server | N/A | ✅ |
| Ease of use | ✅ | Medium |

## hermes-watchdog (Zero-Token Monitoring)

GitHub: https://github.com/LeventeNagy/hermes-watchdog

### How It Saves Tokens
- Checkers run in Python (HTTP + SQLite, no LLM)
- Only wakes agent when changes detected
- `notify` action = zero tokens (direct platform API call)
- `wake` action = uses tokens (only when configured)

### Installation
```bash
hermes plugins install LeventeNagy/hermes-watchdog
hermes plugins enable watchdog
# /reset or gateway restart
```

### Monitors
- GitHub repos (issues, PRs, releases)
- RSS/Atom feeds (new entries)
- Websites (content changes via SHA256 hash)

### Commands
- `/watchdog create` — new watchdog
- `/watchdog list` — all watchdogs
- `/watchdog test <name>` — immediate check
- `/watchdog history <name>` — last 10 runs

### NER-Watch Integration
Can run alongside NER-Watch (separate processes, separate DBs):
- NER-Watch: Entity recognition, Hungarian news
- hermes-watchdog: Content change detection, any source
