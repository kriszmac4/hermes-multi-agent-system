#!/usr/bin/env python3
"""
Agent Message Bus Event Router — Phase 3: event-driven skill match + auto-trigger.

Periodically scans the Agent Message Bus for newly-completed (status='done')
messages, logs them to the skill registry, and (optionally) triggers follow-up
agents based on the Agent Card's `triggers` field.

Cron expression (suggested): every 5 minutes.
    */5 * * * *  ~/.hermes/.venv/bin/python3 ~/.hermes/scripts/agent_message_bus_event_router.py >> ~/.hermes/logs/agent_message_bus_router.log 2>&1

Outputs:
- Per-run: appended to skill_registry.json
- Notifications: sent via mcp_agent_message_bus_agent_send_message to the orchestrator
- Logs: stdout (caller redirects to logs/agent_message_bus_router.log)

Usage:
    ~/.hermes/.venv/bin/python3 ~/.hermes/scripts/agent_message_bus_event_router.py
    ~/.hermes/.venv/bin/python3 ~/.hermes/scripts/agent_message_bus_event_router.py --once --lookback-minutes 60
    ~/.hermes/.venv/bin/python3 ~/.hermes/scripts/agent_message_bus_event_router.py --dry-run
"""

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Ensure agent_message_bus module is importable
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
from agent_message_bus import (
    _load_all_agent_cards,
    SKILL_REGISTRY,
    DATA_DIR,
    get_messages,
    create_message,
    logger,
)

# Where this script writes its own per-run log
ROUTER_LOG = Path.home() / ".hermes" / "logs" / "agent_message_bus_router.log"
ROUTER_STATE = DATA_DIR / "router_state.json"


def _load_router_state() -> dict:
    """Track which done messages we've already processed (idempotency)."""
    if not ROUTER_STATE.exists():
        return {"processed_ids": [], "last_run": None}
    try:
        return json.loads(ROUTER_STATE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"processed_ids": [], "last_run": None}


def _save_router_state(state: dict) -> None:
    ROUTER_STATE.parent.mkdir(parents=True, exist_ok=True)
    # Keep only the last 1000 IDs to avoid unbounded growth
    state["processed_ids"] = state["processed_ids"][-1000:]
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    ROUTER_STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _load_registry() -> dict:
    if not SKILL_REGISTRY.exists():
        return {"version": 1, "invocations": []}
    try:
        return json.loads(SKILL_REGISTRY.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "invocations": []}


def _save_registry(data: dict) -> None:
    SKILL_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    SKILL_REGISTRY.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _extract_skill_from_message(msg: dict) -> tuple[str | None, str | None]:
    """Best-effort: extract (agent, skill_id) from a done message.

    Convention: messages from the orchestrator to a specialist carry the
    skill id either in the content (e.g. "[skill=implement-feature] ...")
    or in a separate "skill" field if the sender used a structured format.
    For now we parse the content header.
    """
    content = msg.get("content", "")
    from_agent = msg.get("from_agent", "")

    if "[skill=" in content:
        try:
            start = content.index("[skill=") + 7
            end = content.index("]", start)
            return from_agent, content[start:end]
        except ValueError:
            pass

    return from_agent, None


def _build_skill_stats(registry: dict) -> dict:
    """Aggregate invocations into (agent, skill) → count and recent tasks."""
    stats: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"count": 0, "recent_tasks": [], "last_seen": None}
    )
    for inv in registry.get("invocations", []):
        key = (inv.get("agent", "?"), inv.get("skill", "?"))
        entry = stats[key]
        entry["count"] += 1
        excerpt = inv.get("task_excerpt", "")
        if excerpt and len(entry["recent_tasks"]) < 3:
            entry["recent_tasks"].append(excerpt)
        ts = inv.get("ts", "")
        if ts and (entry["last_seen"] is None or ts > entry["last_seen"]):
            entry["last_seen"] = ts
    return dict(stats)


def _followups_for(card: dict, skill_id: str | None) -> list[dict]:
    """Look up followup agents/skills defined in the Agent Card's `triggers`."""
    if not skill_id:
        return []
    for trigger in card.get("triggers", []):
        if trigger.get("after_skill") == skill_id:
            return trigger.get("then", [])
    return []


def _trigger_followups(
    followups: list[dict],
    original_msg: dict,
    agent: str | None,
    skill: str | None,
    dry_run: bool,
) -> list[dict]:
    """Send a message to each followup target. Returns the list of (target, message_id)."""
    sent = []
    for fu in followups:
        target = fu.get("to_agent")
        if not target:
            continue
        priority = fu.get("priority", 0)
        content = (
            f"[followup] A '{agent}.{skill}' skill befejeződött. "
            f"Auto-trigger: {fu.get('reason', 'következő lépés')}.\n\n"
            f"Eredeti task: {original_msg.get('content', '')[:300]}\n\n"
            f"Cselekvés: {fu.get('action', 'nézd meg és folytasd')}"
        )
        if dry_run:
            sent.append({"target": target, "dry_run": True, "preview": content[:80]})
            continue
        try:
            new_msg = create_message(
                from_agent="event_router",
                to_agent=target,
                content=content,
                priority=priority,
            )
            sent.append({"target": target, "message_id": new_msg["id"]})
        except Exception as e:
            logger.warning(f"Failed to send followup to {target}: {e}")
    return sent


def run_once(lookback_minutes: int = 30, dry_run: bool = False) -> dict:
    """Single pass: scan done messages, log skills, trigger followups.

    Returns a run summary dict.
    """
    state = _load_router_state()
    processed = set(state.get("processed_ids", []))

    # Pull recent done messages
    done_msgs = get_messages(status="done", limit=200)
    cards = _load_all_agent_cards()

    registry = _load_registry()
    newly_logged = 0
    newly_triggered: list[dict] = []
    new_processed_ids: list[int] = []

    for msg in done_msgs:
        msg_id_raw = msg.get("id")
        if msg_id_raw is None:
            continue
        msg_id = int(msg_id_raw)
        if msg_id in processed:
            continue

        agent, skill = _extract_skill_from_message(msg)

        # Skip noise (system messages, router pings)
        if agent in ("message-router", "event_router", None, ""):
            new_processed_ids.append(msg_id)
            continue

        # Log to skill registry
        registry.setdefault("invocations", []).append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "agent": agent or "unknown",
            "skill": skill or "unknown",
            "task_excerpt": (msg.get("content", "") or "")[:200],
            "message_id": msg_id,
        })
        newly_logged += 1
        new_processed_ids.append(msg_id)

        # Look up followups
        card = cards.get(agent, {}) if agent else {}
        followups = _followups_for(card, skill)
        if followups:
            triggered = _trigger_followups(followups, msg, agent, skill, dry_run)
            for t in triggered:
                newly_triggered.append({
                    "after": f"{agent}.{skill}",
                    **t,
                })

    # Also notify the orchestrator about all newly-done work, even without followups
    if not dry_run and new_processed_ids:
        summary_lines = [f"**📬 Event Router — {len(new_processed_ids)} új done üzenet:**\n"]
        for msg in done_msgs:
            if msg.get("id") in new_processed_ids:
                agent, skill = _extract_skill_from_message(msg)
                summary_lines.append(
                    f"- `#{msg['id']}` **{agent}.{skill}** "
                    f"({msg.get('from_agent', '?')} → {msg.get('to_agent', '?')})"
                )
        if newly_triggered:
            summary_lines.append(f"\n**Auto-triggerelt followupok: {len(newly_triggered)}**")
            for t in newly_triggered:
                summary_lines.append(f"  → {t['after']} → {t['target']}")

        create_message(
            from_agent="event_router",
            to_agent="orchestrator",
            content="\n".join(summary_lines),
            priority=1,
        )

    # Persist state
    state["processed_ids"] = list(processed | set(new_processed_ids))
    if not dry_run:
        _save_registry(registry)
        _save_router_state(state)

    stats = _build_skill_stats(registry)

    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "newly_logged": newly_logged,
        "newly_triggered": newly_triggered,
        "registry_size": len(registry.get("invocations", [])),
        "top_skills": Counter({
            f"{a}.{s}": v["count"] for (a, s), v in
            sorted(stats.items(), key=lambda x: x[1]["count"], reverse=True)[:5]
        }),
        "dry_run": dry_run,
    }


def main():
    parser = argparse.ArgumentParser(description="Agent Message Bus event-driven skill router")
    parser.add_argument("--once", action="store_true", help="Run a single pass and exit")
    parser.add_argument("--interval", type=int, default=300, help="Loop interval seconds (default: 300 = 5 min)")
    parser.add_argument("--lookback-minutes", type=int, default=30, help="Lookback for unprocessed messages (default: 30)")
    parser.add_argument("--dry-run", action="store_true", help="Don't write or send anything")
    args = parser.parse_args()

    if args.once:
        result = run_once(lookback_minutes=args.lookback_minutes, dry_run=args.dry_run)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    # Loop mode (for systemd service or testing)
    print(f"AMB event router started. interval={args.interval}s", file=sys.stderr)
    while True:
        try:
            result = run_once(lookback_minutes=args.lookback_minutes, dry_run=args.dry_run)
            print(json.dumps({"ts": result["ts"], "logged": result["newly_logged"], "triggered": len(result["newly_triggered"])}))
        except Exception as e:
            logger.exception("Router loop error")
            print(f"ERROR: {e}", file=sys.stderr)
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
