#!/usr/bin/env python3
"""
Marveen Escalation Watchdog — no_agent cron

Detects messages that were delivered/read but never processed by an LLM.
If a message sits unprocessed for >5 minutes, pushes a Discord notification
with role ping to alert the orchestrator.

Watchdog pattern:
- Empty stdout = silent (nothing to escalate)
- Output when escalation happens
"""

import json
import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
from marveen import DATA_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("marveen-escalation")

# ── Config ──────────────────────────────────────────────────────────────
ESCALATION_MINUTES = 5  # How long before a message is considered "stale"
TRACKING_FILE = DATA_DIR / "escalation_tracked.json"

DISCORD_ROLE_MENTION = "<@&1501629682175709197>"

# ── Tracking ────────────────────────────────────────────────────────────

def load_tracked() -> set[int]:
    """Load message IDs that have already been escalated."""
    if TRACKING_FILE.exists():
        try:
            data = json.loads(TRACKING_FILE.read_text())
            return set(data.get("escalated_ids", []))
        except (json.JSONDecodeError, KeyError):
            return set()
    return set()


def save_tracked(tracked: set[int]):
    """Save escalated message IDs to disk."""
    TRACKING_FILE.parent.mkdir(parents=True, exist_ok=True)
    TRACKING_FILE.write_text(json.dumps({"escalated_ids": list(tracked)}))


def cleanup_tracked(tracked: set[int], cutoff: float):
    """Remove IDs older than 1 hour from tracking to prevent unbounded growth."""
    # We don't have timestamps per ID, so just clear old entries
    # by keeping only IDs that exist in the DB
    try:
        import sqlite3
        conn = sqlite3.connect(str(DATA_DIR / "agent_messages.db"))
        existing = set(
            row[0] for row in conn.execute(
                "SELECT id FROM agent_messages WHERE id IN ({}) AND status != 'done' AND status != 'failed'".format(
                    ",".join("?" for _ in tracked)
                ),
                list(tracked)
            ).fetchall()
        )
        conn.close()
        # Keep only IDs that still exist and aren't done
        return tracked & existing
    except Exception:
        return tracked


# ── Main ────────────────────────────────────────────────────────────────

def main() -> int:
    cutoff = time.time() - (ESCALATION_MINUTES * 60)
    now_str = time.strftime("%H:%M UTC", time.gmtime())
    
    # Get stale messages
    import sqlite3
    conn = sqlite3.connect(str(DATA_DIR / "agent_messages.db"))
    conn.row_factory = sqlite3.Row
    
    # Messages in 'read' or 'delivered' state older than ESCALATION_MINUTES
    rows = conn.execute(
        "SELECT * FROM agent_messages "
        "WHERE status IN ('read', 'delivered') "
        "AND created_at < ? "
        "ORDER BY priority DESC, created_at ASC "
        "LIMIT 20",
        (cutoff,)
    ).fetchall()
    conn.close()
    
    if not rows:
        # Silent — nothing to escalate (watchdog pattern)
        return 0
    
    tracked = load_tracked()
    stale_messages = []
    for r in rows:
        msg = dict(r)
        if msg["id"] not in tracked:
            stale_messages.append(msg)
    
    if not stale_messages:
        # All already tracked — silent
        return 0
    
    # Build escalation output
    lines = [
        f"⚠️ **Marveen Escalation — üzenetek feldolgozásra várnak** {DISCORD_ROLE_MENTION}",
        f"> *{len(stale_messages)} üzenet vár >{ESCALATION_MINUTES} perce LLM feldolgozásra*",
        ""
    ]
    
    for msg in stale_messages[:5]:  # Max 5 per run
        age_min = int((time.time() - msg["created_at"]) / 60)
        preview = msg["content"][:200]
        if len(msg["content"]) > 200:
            preview += "..."
        lines.append(f"**#{msg['id']}** {msg['from_agent']}→{msg['to_agent']} *(>{age_min} perce)*")
        lines.append(f"> {preview}")
        lines.append("")
        
        # Track that we've escalated this one
        tracked.add(msg["id"])
    
    if len(stale_messages) > 5:
        lines.append(f"> *... és még {len(stale_messages) - 5} üzenet*")
    
    save_tracked(tracked)
    
    # Print for Discord delivery (watchdog pattern)
    print("\n".join(lines))
    logger.info(f"Escalated {len(stale_messages)} stale messages (tracked: {len(tracked)})")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
