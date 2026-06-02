#!/bin/bash
# Graceful restart — wait for active conversations to finish, then restart
# Usage: ~/.hermes/scripts/graceful-restart.sh [--timeout SECONDS] [--dry-run]
#
# How it works:
# 1. Check for active gateway sessions (agents currently processing)
# 2. If found, wait up to TIMEOUT seconds for them to finish
# 3. Then do a normal restart (upgrade-and-restart.sh --skip-upgrade)
#
# Active conversations that are WAITING for user input will resume
# seamlessly on the next message — session context is persisted in SQLite.
# Only currently-PROCESSING agent turns are interrupted.

set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TIMEOUT=60  # seconds to wait for active sessions
DRY_RUN=false

for arg in "$@"; do
  case "$arg" in
    --timeout=*) TIMEOUT="${arg#*=}" ;;
    --timeout) shift; TIMEOUT="${1:-60}" ;;
    --dry-run) DRY_RUN=true ;;
    *) echo "Unknown arg: $arg"; echo "Usage: $0 [--timeout SECONDS] [--dry-run]"; exit 1 ;;
  esac
done

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${CYAN}[INFO]${NC} $*"; }
ok()   { echo -e "${GREEN}[OK]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }

# ─── Check for active agent processing ──────────────────────────────────────
# Active conversations = gateway processes that are currently in an agent loop
# We can detect this by checking if any hermes gateway process is consuming
# significant CPU (meaning it's actively processing, not just idling)

check_active() {
  local count=0
  # Check CPU usage of gateway processes — if any are using >5% CPU, they're likely processing
  while IFS= read -r line; do
    pid=$(echo "$line" | awk '{print $2}')
    cpu=$(ps -p "$pid" -o %cpu= 2>/dev/null | awk '{printf "%.0f", $1}')
    if [ -n "$cpu" ] && [ "$cpu" -gt 5 ] 2>/dev/null; then
      count=$((count + 1))
    fi
  done < <(ps aux | grep 'hermes.*gateway' | grep -v grep)
  echo "$count"
}

if [ "$DRY_RUN" = true ]; then
  active=$(check_active)
  echo "=== DRY RUN ==="
  echo "Active processing agents: $active"
  echo "Would wait up to ${TIMEOUT}s for them to finish"
  echo "Then restart via upgrade-and-restart.sh --skip-upgrade"
  exit 0
fi

# ─── Wait for active sessions ───────────────────────────────────────────────
log "Checking for active agent processing..."
active=$(check_active)

if [ "$active" -gt 0 ]; then
  warn "$active agent(s) currently processing. Waiting up to ${TIMEOUT}s..."
  
  elapsed=0
  while [ "$elapsed" -lt "$TIMEOUT" ]; do
    sleep 5
    elapsed=$((elapsed + 5))
    active=$(check_active)
    if [ "$active" -eq 0 ]; then
      ok "All agents finished processing (waited ${elapsed}s)"
      break
    fi
    if [ $((elapsed % 15)) -eq 0 ]; then
      log "Still waiting... ${active} active (${elapsed}/${TIMEOUT}s)"
    fi
  done
  
  if [ "$active" -gt 0 ]; then
    warn "Timeout reached. ${active} agent(s) still active — proceeding with restart anyway."
    warn "Their current processing will be interrupted but sessions will resume on next message."
  fi
else
  ok "No active agent processing detected"
fi

# ─── Do the restart ─────────────────────────────────────────────────────────
log "Initiating restart..."
exec "$SCRIPT_DIR/upgrade-and-restart.sh" --skip-upgrade