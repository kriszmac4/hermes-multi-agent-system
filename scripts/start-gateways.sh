#!/bin/bash
# Hermes Multi-Agent System v4 — Start all gateways
# Usage: ./scripts/start-gateways.sh [--stagger SECONDS]
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
STAGGER="${1:-5}"  # seconds between each gateway start

echo "🏛️ Hermes Multi-Agent System v4 — Starting gateways"
echo "================================================"

PROFILES=("general" "dev" "research" "study")

for profile in "${PROFILES[@]}"; do
    echo "▶️  Starting $profile gateway..."
    hermes gateway run --profile "$profile" --replace &
    sleep "$STAGGER"
done

echo ""
echo "✅ All gateways started!"
echo "   General (Telegram+Discord) — PID: $(pgrep -f 'profile general' | head -1)"
echo "   Dev (Discord)              — PID: $(pgrep -f 'profile dev' | head -1)"
echo "   Research (Discord)         — PID: $(pgrep -f 'profile research' | head -1)"
echo "   Study (Discord)            — PID: $(pgrep -f 'profile study' | head -1)"
echo ""
echo "📋 Check status: hermes gateway status"