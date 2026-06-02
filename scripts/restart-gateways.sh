#!/bin/bash
# Quick gateway restart for consolidated active profiles
# Usage: ~/.hermes/scripts/restart-gateways.sh [--dry-run]

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"

# Source .env to ensure API keys are available in non-interactive contexts (cron, systemd)
set -a
[[ -f "$HERMES_HOME/.env" ]] && source "$HERMES_HOME/.env"
set +a

# More forgiving connect timeout for Discord gateway handshake.
export HERMES_GATEWAY_PLATFORM_CONNECT_TIMEOUT="${HERMES_GATEWAY_PLATFORM_CONNECT_TIMEOUT:-90}"

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

TARGET_PROFILES=(general research study dev)
PROFILES=$(printf "%s\n" "${TARGET_PROFILES[@]}")

if [ -z "$PROFILES" ]; then
  echo "No running gateways found."
  exit 0
fi

echo "Target profiles: $PROFILES"

if [ "$DRY_RUN" = true ]; then
  echo "DRY RUN — would restart: $PROFILES"
  exit 0
fi

# Stop all gateways
echo "Stopping all gateways..."
pids=$(ps aux | grep 'hermes.*gateway' | grep -v grep | awk '{print $2}')
if [ -n "$pids" ]; then
  echo "$pids" | xargs kill 2>/dev/null || true
  echo "Waiting 5s for graceful shutdown..."
  sleep 5
  pids=$(ps aux | grep 'hermes.*gateway' | grep -v grep | awk '{print $2}')
  if [ -n "$pids" ]; then
    echo "Force killing remaining..."
    echo "$pids" | xargs kill -9 2>/dev/null || true
    sleep 2
  fi
  echo "All gateways stopped."
fi

# Restart each profile with staggered startup
for profile in $PROFILES; do
  echo "Starting $profile..."
  if [ "$profile" = "general" ]; then
    nohup hermes gateway run --replace \
      > "$HERMES_HOME/logs/gateway-${profile}.log" 2>&1 &
  else
    nohup hermes gateway run --profile "$profile" --replace \
      > "$HERMES_HOME/logs/gateway-${profile}.log" 2>&1 &
  fi
  sleep 30
done

echo "Waiting 20s for connections..."
sleep 20

# Verify
for profile in $PROFILES; do
  if [ "$profile" = "general" ]; then
    pid=$(ps aux | grep "hermes.*gateway" | grep -v grep | grep -v -- "--profile" | awk '{print $2}' | head -1)
  else
    pid=$(ps aux | grep "hermes.*gateway.*--profile $profile" | grep -v grep | awk '{print $2}' | head -1)
  fi
  if [ -n "$pid" ]; then
    echo "✅ $profile running (PID $pid)"
  else
    echo "❌ $profile NOT running!"
  fi
done

# Restart branch sidecar bot
BRANCH_BOT_PID=$(ps aux | grep '[b]ranch_bot.py' | awk '{print $2}' | head -1)
if [ -n "$BRANCH_BOT_PID" ]; then
  echo "Restarting branch bot (PID $BRANCH_BOT_PID)..."
  kill "$BRANCH_BOT_PID" 2>/dev/null || true
  sleep 2
fi
BRANCH_TOKEN=$(grep BRANCH_BOT_TOKEN "$HERMES_HOME/.env" | cut -d= -f2)
if [ -n "$BRANCH_TOKEN" ]; then
  nohup "$HERMES_HOME/.venv/bin/python3" "$HERMES_HOME/scripts/branch_bot.py" \
    > "$HERMES_HOME/logs/branch-bot.log" 2>&1 &
  sleep 3
  NEW_PID=$(ps aux | grep '[b]ranch_bot.py' | awk '{print $2}' | head -1)
  if [ -n "$NEW_PID" ]; then
    echo "✅ Branch bot running (PID $NEW_PID)"
  else
    echo "❌ Branch bot failed to start"
  fi
else
  echo "⚠️ BRANCH_BOT_TOKEN not set, skipping branch bot"
fi

echo "Done."
