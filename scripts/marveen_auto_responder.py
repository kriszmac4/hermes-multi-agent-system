#!/usr/bin/env python3
"""
Marveen Auto-Responder — no_agent watchdog cron

Pollos the Marveen bus for pending messages and auto-responds
with pre-defined templates. No LLM, no agent session needed.

Flow:
1. Find pending messages to specific agents
2. Determine responder and response template based on sender/receiver
3. Create response message via Marveen bus
4. Mark original as 'read' (not done — the target agent still sees it)

Watchdog pattern:
- Empty stdout = silent (nothing to respond to)
- Output when responses are sent
"""

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
from marveen import (
    create_message,
    get_pending_messages,
    get_messages,
    mark_delivered,
    mark_read,
    mark_done,
    mark_failed,
    DATA_DIR,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("marveen-auto-responder")

# ── Response Templates ──────────────────────────────────────────────────
# Format: (from_agent, to_agent) → responder, response_template
# responder = which agent sends the auto-response
# response_template = message content (uses {from}, {to}, {content}, {preview})

RESPONSE_RULES = [
    # study→orchestrator: orchestrator's auto-responder sends ack
    {
        "from_filter": None,           # None = any
        "to_filter": "orchestrator",    # target
        "responder": "orchestrator",    # who responds
        "response": "📥 **Auto-válasz**: Üzenetedet fogadtam! "
                     "Amint aktív session-ben vagyok, feldolgozom. "
                     "Addig is tartsd a tanulási terved! 🎯\n\n"
                     "---\n*Ezt az üzenetet automatikus cron generálta LLM nélkül.*",
        "mark_as": "read",  # delivered, read, or done
    },
    # study→general: orchestrator responds  
    {
        "from_filter": None,
        "to_filter": "general",
        "responder": "orchestrator",
        "response": "📥 **Auto-válasz**: Köszönöm az üzenetet! "
                     "Átadom a megfelelő agent-nek, amint elérhető.\n\n"
                     "---\n*Auto-responder*",
        "mark_as": "read",
    },
    # Any→dev: dev's auto-responder
    {
        "from_filter": None,
        "to_filter": "dev",
        "responder": "dev",
        "response": "📥 **Auto-ack**: Message received. Will process when session is active.",
        "mark_as": "read",
    },
    # Any→research: research's auto-responder
    {
        "from_filter": None,
        "to_filter": "research",
        "responder": "research",
        "response": "📥 **Auto-ack**: Research request logged. Will investigate next session.",
        "mark_as": "read",
    },
]


def get_responder_rule(msg: dict) -> dict | None:
    """Find the first matching rule for a message."""
    for rule in RESPONSE_RULES:
        if rule["to_filter"] and msg["to_agent"] != rule["to_filter"]:
            continue
        if rule.get("from_filter") and msg["from_agent"] != rule["from_filter"]:
            continue
        return rule
    return None


def format_response(template: str, msg: dict) -> str:
    """Fill template variables from message."""
    content = msg.get("content", "")
    preview = content[:200] + ("..." if len(content) > 200 else "")
    return template.format(
        from_=msg["from_agent"],
        to=msg["to_agent"],
        content=content,
        preview=preview,
    )


def main() -> int:
    """Main loop — poll and respond."""
    # Get both pending AND recently delivered messages
    pending = get_pending_messages(limit=50)
    
    # Also get delivered messages from the last 2 minutes that weren't auto-responded yet
    import time
    recent_cutoff = time.time() - 120  # last 2 minutes
    conn = __import__('sqlite3').connect(str(DATA_DIR / "agent_messages.db"))
    conn.row_factory = __import__('sqlite3').Row
    rows = conn.execute(
        "SELECT * FROM agent_messages WHERE status = 'delivered' AND created_at > ? "
        "ORDER BY priority DESC, created_at ASC LIMIT 50",
        (recent_cutoff,)
    ).fetchall()
    conn.close()
    delivered = [dict(r) for r in rows]
    
    # Merge: pending first (newer), then delivered
    seen_ids = set(m["id"] for m in pending)
    for m in delivered:
        if m["id"] not in seen_ids:
            pending.append(m)
            seen_ids.add(m["id"])
    responses_sent = 0
    skipped = 0
    
    for msg in pending:
        msg_id = msg["id"]
        
        # Skip messages that are auto-responses themselves (prevent loops)
        if msg["from_agent"] in ("orchestrator", "dev", "research", "news", "kanban", "fitness"):
            # Check if this is already an auto-response
            content = msg.get("content", "")
            if content.startswith("📥 **Auto-válasz") or content.startswith("📥 **Auto-ack"):
                logger.info(f"#{msg_id} skipping auto-response loop from {msg['from_agent']}")
                mark_delivered(msg_id)
                skipped += 1
                continue
        
        # Find matching rule
        rule = get_responder_rule(msg)
        if not rule:
            logger.debug(f"#{msg_id} no matching rule for {msg['from_agent']}→{msg['to_agent']}")
            continue
        
        # Don't respond to message-router messages
        if msg["from_agent"] == "message-router":
            mark_delivered(msg_id)
            skipped += 1
            continue
        
        # Format and send response
        response_text = format_response(rule["response"], msg)
        try:
            create_message(
                from_agent=rule["responder"],
                to_agent=msg["from_agent"],  # respond back to sender
                content=response_text,
                priority=msg.get("priority", 0),
            )
            logger.info(f"#{msg_id} auto-responded: {msg['from_agent']}→{msg['to_agent']}")
            
            # Mark original
            mark_as = rule.get("mark_as", "read")
            if mark_as == "read":
                mark_read(msg_id)
            elif mark_as == "done":
                mark_done(msg_id, "Auto-responded")
            else:
                mark_delivered(msg_id)
            
            responses_sent += 1
            msg["_responded"] = True  # mark for output
        except Exception as e:
            logger.error(f"#{msg_id} failed to respond: {e}")
            mark_failed(msg_id, str(e))
    
    # Watchdog output — only when something happened
    if responses_sent:
        lines = [
            f"📬 **Auto-Responder — válaszok elküldve** <@&1501629682175709197>",
        ]
        # Show each response
        for msg in pending:
            if msg.get("_responded"):
                rule = get_responder_rule(msg)
                if rule:
                    response_text = format_response(rule["response"], msg)
                    lines.append(f"> **{msg['from_agent']}→{msg['to_agent']}**")
                    lines.append(f"> {response_text[:200]}...\n" if len(response_text) > 200 else f"> {response_text}\n")
        print("\n".join(lines))
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
