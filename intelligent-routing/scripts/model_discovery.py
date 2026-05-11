#!/usr/bin/env python3
"""
Model Auto-Discovery Script — Intelligent Routing Skill.
Weekly scan: new models on OpenRouter, benchmark comparison, route update.
"""

import sys
import json
import os
import urllib.request
from datetime import datetime

OPENROUTER_API = "https://openrouter.ai/models"
CONFIG_PATH = os.path.expanduser("~/.hermes/routing_config.yaml")

def fetch_openrouter_models():
    """Fetch top models from OpenRouter."""
    try:
        req = urllib.request.Request(
            OPENROUTER_API,
            headers={"Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY', '')}"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"OpenRouter fetch failed: {e}")
        return []

def filter_interesting_models(models: list, max_price: float = 0.01, min_score: float = 35) -> list:
    """Filter models by price and benchmark score."""
    results = []
    for m in models:
        # Skip if no pricing
        context = m.get("context_length", 0)
        # Look for per-token pricing in pricing field
        pricing = m.get("pricing", {})
        price_per_1k = 0
        if isinstance(pricing, dict):
            # Try common keys
            for key in ["prompt", "completion", "price"]:
                if key in pricing:
                    price_per_1k = float(pricing[key]) * 1000  # per 1K tokens
                    break

        score = m.get("rating", 0) or m.get("trending_score", 0) or 0

        if price_per_1k <= max_price and (score == 0 or score >= min_score):
            results.append({
                "id": m.get("id", "unknown"),
                "name": m.get("name", m.get("id")),
                "price_per_1k": price_per_1k,
                "score": score,
                "context": context,
                "description": m.get("description", "")[:100]
            })

    return sorted(results, key=lambda x: x["score"], reverse=True)[:10]

def generate_report(new_models: list, current_models: list) -> str:
    """Generate Telegram report."""
    if not new_models:
        return "📊 Model Discovery: No new relevant models found this week."

    report = ["📊 **Heti Model Auto-Discovery Report**"]
    report.append(f"__{datetime.now().strftime('%Y-%m-%d')}__\n")
    report.append(f"**{len(new_models)} új modell** (<${max(m['price_per_1k'] for m in new_models):.4f}/1K, score>{min(m['score'] for m in new_models):.0f}):**\n")

    for m in new_models[:5]:
        report.append(f"• `{m['id']}` — ${m['price_per_1k']:.4f}/1K | score:{m['score']}")

    report.append(f"\n**Jelenlegi modellek:**")
    for cm in current_models[:5]:
        report.append(f"• `{cm}`")

    return "\n".join(report)

if __name__ == "__main__":
    scan_mode = '--scan' in sys.argv
    update_mode = '--update-routes' in sys.argv
    report_mode = '--report' in sys.argv

    if not any([scan_mode, update_mode, report_mode]):
        print("Usage: model_discovery.py --scan --benchmark --update-routes --report")
        sys.exit(1)

    print("🔍 Fetching OpenRouter models...")
    all_models = fetch_openrouter_models()
    print(f"   Found {len(all_models)} models")

    interesting = filter_interesting_models(all_models)
    print(f"   {len(interesting)} interesting (<$0.01/1K, score>35)")

    current_models = ["minimax-m2.5-free", "gemini-2.5-pro", "gemini-2.5-flash", "claude-sonnet-4"]

    if report_mode:
        report = generate_report(interesting, current_models)
        print(report)

    if update_mode and interesting:
        print(f"\n📝 Would add: {interesting[0]['id']}")
        # TODO: Update routing_config.yaml with new models
        print("   (config update not implemented yet)")
