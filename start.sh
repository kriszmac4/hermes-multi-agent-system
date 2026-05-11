#!/bin/bash
# Start Hermes Discord bots — 6 specialist agents as separate gateways
# Usage: ./start.sh [all|general|research|dev|devops|news|study]
# Default: starts all bots

PROFILES=("general" "research" "dev" "devops" "news" "study")
SESSION="hermes-discord"

start_bot() {
    local profile=$1
    local port=$((5000 + $(echo "$profile" | cksum | cut -d' ' -f1) % 1000))
    echo "🤖 Starting $profile (gateway, port $port)..."
    tmux new-window -t "$SESSION" -n "$profile" 2>/dev/null
    tmux send-keys -t "$SESSION:$profile" "hermes gateway run --profile $profile --port $port" Enter
    sleep 5
    # Check if process is alive
    if tmux list-windows -t "$SESSION" 2>/dev/null | grep -q "$profile"; then
        echo "✅ $profile gateway starting"
    else
        echo "❌ $profile failed to start"
    fi
}

# Create session if needed
if ! tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "📡 Creating tmux session: $SESSION"
    tmux new-session -d -s "$SESSION" -n "control"
fi

# Start bots
if [ "$1" = "all" ] || [ -z "$1" ]; then
    for profile in "${PROFILES[@]}"; do
        start_bot "$profile"
    done
    echo ""
    echo "🎉 All 6 Discord bot gateways starting!"
    echo "📡 Monitor: tmux attach -t $SESSION"
    echo "📋 Windows: ${PROFILES[*]}"
    echo ""
    echo "Wait ~10-15s for all bots to connect to Discord."
    echo "Check status: tmux capture-pane -t $SESSION:general -p | tail -5"
else
    start_bot "$1"
fi