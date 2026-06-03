#!/usr/bin/env python3
import sqlite3, time

db = sqlite3.connect('/home/artofphotogrphyy/.hermes/data/marveen/agent_messages.db')
db.row_factory = sqlite3.Row

for s in ['pending','delivered','read','done','failed']:
    c = db.execute("SELECT COUNT(*) FROM agent_messages WHERE status=?", (s,)).fetchone()[0]
    print(f"{s}: {c}")

print()
rows = db.execute("SELECT * FROM agent_messages WHERE status='pending' ORDER BY priority DESC, created_at ASC").fetchall()
print(f"PENDING ({len(rows)}):")
for r in rows:
    age = int(time.time() - r['created_at'])
    print(f"  #{r['id']} [{age}s] {r['from_agent']}→{r['to_agent']}: {r['content'][:200]}")

print()
rows = db.execute("SELECT * FROM agent_messages WHERE status IN ('delivered','read') ORDER BY created_at DESC LIMIT 20").fetchall()
print(f"RECENT DELIVERED/READ ({len(rows)}):")
for r in rows:
    print(f"  #{r['id']} [{r['status']}] {r['from_agent']}→{r['to_agent']}: {r['content'][:200]}")

print()
rows = db.execute("SELECT * FROM agent_messages WHERE status='done' ORDER BY created_at DESC LIMIT 5").fetchall()
print(f"RECENT DONE ({len(rows)}):")
for r in rows:
    print(f"  #{r['id']} {r['from_agent']}→{r['to_agent']}: {r['content'][:200]}")

db.close()
