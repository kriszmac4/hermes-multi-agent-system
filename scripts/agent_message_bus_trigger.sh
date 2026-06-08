#!/bin/bash
# AMB Trigger — no_agent watchdog cron
# Detects pending messages, writes trigger file for LLM processor
# Outputs to stdout only when there's work (watchdog pattern)

AMB_DIR="/home/artofphotogrphyy/.hermes/scripts"
TRIGGER_FILE="/tmp/amb-trigger"
LOCK_FILE="/tmp/amb-trigger.lock"

# Prevent concurrent runs
if [ -f "$LOCK_FILE" ] && [ -n "$(find "$LOCK_FILE" -mmin -1 2>/dev/null)" ]; then
    exit 0
fi
touch "$LOCK_FILE"

# Check for pending messages
PENDING=$(cd "$AMB_DIR" && PYTHONPATH=. /home/artofphotogrphyy/.hermes/.venv/bin/python3 -c "
import sys
sys.path.insert(0, '.')
from agent_message_bus import get_pending_messages
msgs = get_pending_messages(limit=100)
if not msgs:
    sys.exit(0)

# Collect unique target agents
agents = set()
for m in msgs:
    agents.add(m['to_agent'])

# Count per agent
from collections import Counter
counts = Counter(m['to_agent'] for m in msgs)

# Write trigger file
with open('/tmp/amb-trigger', 'w') as f:
    for agent in sorted(agents):
        f.write(f'{agent}:{counts[agent]}\n')

# Output summary
print(f'📬 **AMB Trigger** — $(date +\"%H:%M\")')
for agent in sorted(agents):
    print(f'  → **{agent}**: {counts[agent]} message(s)')
total = len(msgs)
high_prio = sum(1 for m in msgs if m.get('priority', 0) >= 1)
if high_prio:
    print(f'  ⚡ {high_prio} high priority among them')
")

EXIT_CODE=$?

rm -f "$LOCK_FILE"

if [ -n "$PENDING" ]; then
    echo "$PENDING"
fi

exit $EXIT_CODE
