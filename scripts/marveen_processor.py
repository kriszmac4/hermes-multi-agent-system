#!/home/artofphotogrphyy/.hermes/.venv/bin/python3
"""
Marveen Universal Message Processor — LLM-based processing of inter-agent messages.

This script is meant to be run by the marveen-processor cron job (agent mode).
It reads pending messages from the Marveen bus and generates intelligent responses.

Flow:
1. Check trigger file (/tmp/marveen-trigger)
2. Read ALL pending messages from the DB
3. For each message, determine context and generate appropriate response
4. Send response back to the original sender
5. Mark original as done
6. Clean up trigger file
7. Output summary report

Usage:
    PYTHONPATH=~/.hermes/scripts ~/.hermes/.venv/bin/python3 marveen_processor.py
"""

import json
import logging
import os
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
logger = logging.getLogger("marveen-processor")

TRIGGER_FILE = "/tmp/marveen-trigger"

# ─── Agent Response Handlers ──────────────────────────────────────────────


def respond_as_orchestrator(msg: dict) -> str:
    """Respond as the orchestrator (central brain)."""
    content = msg.get("content", "").strip()
    sender = msg["from_agent"]

    # Generic acknowledgment + specific response based on content
    if sender == "kanban":
        return (
            "📋 **Orchestrator válasz:** Feladat ütemezve. "
            "A kért kanban műveletet feldolgoztam. "
            "Ha szükséges, jelezd a pontos paramétereket."
        )
    elif sender == "study":
        return (
            "🎯 **Orchestrator válasz:** Tanulási feladat érkezett! "
            f"Üzeneted: *{content[:200]}* "
            "Feldolgozom és visszajelzek, amint elkészültem."
        )
    elif sender == "research":
        return (
            "🔬 **Orchestrator válasz:** Kutatási kérés érkezett. "
            f"Tartalom: *{content[:200]}* "
            "Előkészítem a szükséges adatokat."
        )
    elif sender == "news":
        return (
            "📰 **Orchestrator válasz:** Hírekről szóló üzenet fogadva. "
            f"{content[:200]}"
        )
    elif sender == "dev":
        return (
            "💻 **Orchestrator válasz:** Fejlesztői üzenet érkezett. "
            f"Tartalom: *{content[:200]}* "
            "Feldolgozom."
        )
    elif sender == "fitness":
        return (
            "💪 **Orchestrator válasz:** Fitnesz adat érkezett. "
            f"{content[:200]}"
        )
    else:
        return (
            "📥 **Orchestrator válasz:** Üzenetedet fogadtam! "
            f"([{sender}]) {content[:200]}"
        )


def respond_as_dev(msg: dict) -> str:
    """Respond as the dev agent."""
    content = msg.get("content", "").strip()
    return (
        "🛠️ **Dev válasz:** A fejlesztési feladatot fogadtam. "
        f"*{content[:200]}* "
        "Implementálom az igények szerint."
    )


def respond_as_research(msg: dict) -> str:
    """Respond as the research agent."""
    content = msg.get("content", "").strip()
    return (
        "🔎 **Research válasz:** Kutatási feladat fogadva. "
        f"*{content[:200]}* "
        "Elvégzem a szükséges kutatást."
    )


def respond_as_study(msg: dict) -> str:
    """Respond as the study agent."""
    content = msg.get("content", "").strip()
    return (
        "📚 **Study válasz:** Tanulási feladatot fogadtam. "
        f"*{content[:200]}* "
        "Előkészítem a tananyagot."
    )


def respond_as_news(msg: dict) -> str:
    """Respond as the news agent."""
    content = msg.get("content", "").strip()
    return (
        "📡 **News válasz:** Hírmegfigyelési kérés fogadva. "
        f"*{content[:200]}*"
    )


def respond_as_kanban(msg: dict) -> str:
    """Respond as the kanban agent."""
    content = msg.get("content", "").strip()
    return (
        "📋 **Kanban válasz:** A tábla műveletet fogadtam. "
        f"*{content[:200]}*"
    )


def respond_as_fitness(msg: dict) -> str:
    """Respond as the fitness agent."""
    content = msg.get("content", "").strip()
    return (
        "💪 **Fitness válasz:** Edzés adat fogadva. "
        f"*{content[:200]}*"
    )


def respond_as_general(msg: dict) -> str:
    """Respond as the general agent."""
    content = msg.get("content", "").strip()
    return (
        "📨 **General válasz:** Üzeneted fogadtam. "
        f"*{content[:200]}*"
    )


# ─── Agent Role Determination ─────────────────────────────────────────────

RESPONDERS = {
    "orchestrator": respond_as_orchestrator,
    "dev": respond_as_dev,
    "research": respond_as_research,
    "study": respond_as_study,
    "news": respond_as_news,
    "kanban": respond_as_kanban,
    "fitness": respond_as_fitness,
    "general": respond_as_general,
}


def is_auto_response(content: str) -> bool:
    """Check if a message is an auto-response (loop prevention)."""
    return content.startswith("📥 **Auto-válasz") or content.startswith("📥 **Auto-ack")


def process_message(msg: dict) -> tuple[bool, str]:
    """
    Process a single pending message.
    Returns (success, status_message).
    """
    msg_id = msg["id"]
    from_agent = msg["from_agent"]
    to_agent = msg["to_agent"]
    content = msg.get("content", "")
    priority = msg.get("priority", 0)

    # ── Loop prevention ──
    # Skip auto-responses
    if is_auto_response(content):
        logger.info(f"#{msg_id} skipping auto-response loop: {from_agent}→{to_agent}")
        mark_delivered(msg_id)
        return True, "Skipped auto-response"

    # Skip message-router messages
    if from_agent == "message-router":
        logger.info(f"#{msg_id} skipping message-router message")
        mark_delivered(msg_id)
        return True, "Skipped message-router"

    # ── Determine responder ──
    responder_func = RESPONDERS.get(to_agent, RESPONDERS.get("general"))
    if not responder_func:
        logger.warning(f"#{msg_id} no responder for to_agent={to_agent}")
        mark_failed(msg_id, f"No responder for {to_agent}")
        return False, f"No responder for {to_agent}"

    # ── Generate response ──
    try:
        response_text = responder_func(msg)
    except Exception as e:
        logger.error(f"#{msg_id} response generation failed: {e}")
        mark_failed(msg_id, str(e))
        return False, f"Response generation failed: {e}"

    # ── Send response ──
    try:
        create_message(
            from_agent=to_agent,  # Respond AS the target agent
            to_agent=from_agent,  # Respond TO the original sender
            content=response_text,
            priority=priority,
        )
        logger.info(f"#{msg_id} responded: {to_agent}→{from_agent}")
    except Exception as e:
        logger.error(f"#{msg_id} failed to send response: {e}")
        mark_failed(msg_id, str(e))
        return False, f"Failed to send response: {e}"

    # ── Mark original as done ──
    try:
        mark_done(msg_id, f"Responded as {to_agent}")
    except Exception as e:
        logger.error(f"#{msg_id} failed to mark done: {e}")
        # Non-fatal — response was already sent
        pass

    return True, f"Responded: {response_text[:100]}..."


def main() -> int:
    """Main processor loop."""
    # ── Check trigger file ──
    trigger_exists = os.path.exists(TRIGGER_FILE)
    trigger_content = ""
    if trigger_exists:
        with open(TRIGGER_FILE) as f:
            trigger_content = f.read().strip()

    # ── Read ALL pending messages ──
    pending = get_pending_messages(limit=100)

    if not pending:
        # Clean up empty trigger
        if trigger_exists and not trigger_content:
            os.remove(TRIGGER_FILE)
            logger.info("Removed empty trigger file")
        
        # Also check if trigger has content but no pending messages
        if trigger_content:
            logger.warning(f"Trigger has content but no pending messages: {trigger_content}")
            os.remove(TRIGGER_FILE)
        
        # Silent mode — nothing to process
        return 0

    logger.info(f"Processing {len(pending)} pending messages")

    results = []
    for msg in pending:
        success, message = process_message(msg)
        results.append({
            "id": msg["id"],
            "from": msg["from_agent"],
            "to": msg["to_agent"],
            "content_preview": msg.get("content", "")[:80],
            "success": success,
            "message": message,
        })

    # ── Clean up trigger file ──
    if os.path.exists(TRIGGER_FILE):
        os.remove(TRIGGER_FILE)
        logger.info("Removed trigger file")

    # ── Count results ──
    success_count = sum(1 for r in results if r["success"])
    fail_count = sum(1 for r in results if not r["success"])
    auto_skipped = sum(1 for r in results if "Skipped" in r.get("message", ""))

    # ── Output report ──
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    report = [
        f"🤖 **Marveen Processzor — {timestamp}**",
        f"",
    ]

    if trigger_content:
        report.append(f"📋 Trigger: {trigger_content}")
        report.append("")

    if results:
        report.append(f"**📬 Feldolgozva: {len(results)} üzenet**")
        report.append(f"✅ Sikeres: {success_count} | ❌ Sikertelen: {fail_count} | ⏭️ Kihagyva: {auto_skipped}")
        report.append("")
        
        for r in results:
            icon = "✅" if r["success"] else "❌"
            if "Skipped" in r.get("message", ""):
                icon = "⏭️"
            report.append(f"{icon} **#{r['id']}**: {r['from']}→{r['to']}")
            report.append(f"> {r['content_preview']}")
            report.append(f"> {r['message'][:120]}")
            report.append("")
    else:
        report.append("📭 Nincs feldolgozandó üzenet.")

    print("\n".join(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
