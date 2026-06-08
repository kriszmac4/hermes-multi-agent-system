#!/usr/bin/env python3
"""Check pending messages via direct DB access and write to output file."""
import sys, json
sys.path.insert(0, '/home/artofphotogrphyy/.hermes/scripts')
from agent_message_bus import get_pending_messages, get_messages

results = {"pending": [], "delivered": [], "read": []}

# Check all pending
pending = get_pending_messages()
results["pending"] = [{"id": m["id"], "from": m["from_agent"], "to": m["to_agent"], 
                        "content": m["content"][:200], "created": m["created_at"]} 
                       for m in pending]

# Check recent delivered/read that might need attention
for status in ("delivered", "read"):
    msgs = get_messages(status=status, limit=10)
    results[status] = [{"id": m["id"], "from": m["from_agent"], "to": m["to_agent"],
                         "content": m["content"][:200], "created": m["created_at"]}
                        for m in msgs]

output_path = '/tmp/amb_check_results.json'
with open(output_path, 'w') as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print(f"Results written to {output_path}")
print(f"  Pending: {len(results['pending'])}")
print(f"  Delivered (recent): {len(results['delivered'])}")
print(f"  Read (recent): {len(results['read'])}")
