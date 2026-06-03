#!/usr/bin/env python3
"""
Marveen Heartbeat — System health check

Runs every hour as a no_agent cron script.
- Checks message queue health
- Checks autonomy config integrity
- Checks dream engine recent output
- Reports only if something is wrong (watchdog pattern)

Watchdog: empty stdout = silent (nothing wrong). Output only on issues.
"""

import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
from marveen import (
    get_messages,
    get_all_autonomy_categories,
    AUTONOMY_CONFIG,
    DREAMS_DIR,
)


def check_message_queue() -> list[str]:
    """Check for stuck messages or anomalies."""
    issues = []
    
    pending = get_messages(status="pending", limit=100)
    old_pending = [m for m in pending if (time.time() - m["created_at"]) > 1800]  # 30+ min
    
    if old_pending:
        issues.append(f"⚠️ {len(old_pending)} üzenet 30+ perce függőben")
    
    # Check for queue buildup
    if len(pending) > 50:
        issues.append(f"⚠️ {len(pending)} függőben lévő üzenet (torlódás)")
    
    return issues


def check_autonomy() -> list[str]:
    """Check autonomy config integrity."""
    issues = []
    
    if not AUTONOMY_CONFIG.exists():
        issues.append("❌ Autonómia config nem található")
        return issues
    
    cats = get_all_autonomy_categories()
    if not cats:
        issues.append("⚠️ Nincsenek autonómia kategóriák")
    
    # Check for locked + high level (shouldn't happen)
    for c in cats:
        if c.get("locked") and c.get("level", 1) > c.get("maxLevel", 1):
            issues.append(f"⚠️ '{c['label']}' zárolva de {c['level']}. szinten")
    
    return issues


def check_dream_engine() -> list[str]:
    """Check if dream engine ran recently."""
    issues = []
    
    dreams = sorted(DREAMS_DIR.glob("*.md"), reverse=True)
    if not dreams:
        issues.append("⏳ Dream Engine még nem futott le")
        return issues
    
    last_dream = dreams[0]
    last_time = last_dream.stat().st_mtime
    hours_since = (time.time() - last_time) / 3600
    
    if hours_since > 28:  # More than a day
        issues.append(f"⏰ Dream Engine utoljára {hours_since:.0f} órája")
    
    return issues


def main():
    issues = []
    issues.extend(check_message_queue())
    issues.extend(check_autonomy())
    issues.extend(check_dream_engine())
    
    if not issues:
        return 0  # Silent — watchdog pattern
    
    print(f"**💓 Marveen Heartbeat — {datetime.now(timezone.utc).strftime('%H:%M UTC')}**")
    for issue in issues:
        print(f"- {issue}")
    print("\n_A heartbeat automatikusan fut óránként._")
    return 0


if __name__ == "__main__":
    sys.exit(main())
