#!/usr/bin/env python3
"""
Marveen Dream Engine — Nightly Consolidation (02:00 UTC)

5 buckets:
1. 💡 Skill suggestions from daily patterns
2. 🧹 Memory health (tier management, vectorization)
3. 🎯 Top-3 priorities for tomorrow (from kanban)
4. 🌐 External opportunity (weekly)
5. 🛠 Skill fleet health

Output: ~/.hermes/data/marveen/dreams/YYYY-MM-DD_DREAM.md
"""

import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
from marveen import DATA_DIR, DREAMS_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("dream-engine")

HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))


def run(cmd: list[str], timeout: int = 30) -> str:
    """Run a shell command and return stdout, or empty on failure."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception as e:
        logger.warning(f"Command failed: {' '.join(cmd)}: {e}")
        return ""


def get_kanban_stats() -> dict:
    """Read kanban DB for task stats."""
    kanban_db = HERMES_HOME / "kanban.db"
    if not kanban_db.exists():
        return {"total": 0, "in_progress": 0, "done_today": 0}
    
    import sqlite3
    try:
        conn = sqlite3.connect(str(kanban_db))
        cur = conn.cursor()
        
        total = cur.execute("SELECT COUNT(*) FROM kanban_tasks").fetchone()[0]
        in_progress = cur.execute(
            "SELECT COUNT(*) FROM kanban_tasks WHERE status = 'in_progress'"
        ).fetchone()[0]
        done_today = cur.execute(
            "SELECT COUNT(*) FROM kanban_tasks WHERE status = 'done' "
            "AND updated_at >= ?",
            (time.time() - 86400,)
        ).fetchone()[0]
        conn.close()
        return {"total": total, "in_progress": in_progress, "done_today": done_today}
    except Exception as e:
        logger.warning(f"Kanban read error: {e}")
        return {"total": 0, "in_progress": 0, "done_today": 0}


def get_skills_list() -> list[dict]:
    """List installed skills with metadata."""
    skills_dir = HERMES_HOME / "skills"
    if not skills_dir.exists():
        return []
    
    skills = []
    for skill_file in skills_dir.rglob("SKILL.md"):
        try:
            content = skill_file.read_text()
            name = ""
            desc = ""
            modified = skill_file.stat().st_mtime
            for line in content.split("\n"):
                if line.startswith("name:"):
                    name = line.split(":", 1)[1].strip()
                if line.startswith("description:"):
                    desc = line.split(":", 1)[1].strip()
            skills.append({
                "name": name or skill_file.parent.name,
                "description": desc[:80],
                "modified": datetime.fromtimestamp(modified).isoformat(),
                "days_since_mod": int((time.time() - modified) / 86400),
            })
        except Exception:
            continue
    return skills


def get_memory_stats() -> dict:
    """Get memory stats from ICM or mem0."""
    try:
        # Try ICM
        r = subprocess.run(
            ["icm", "topics"], capture_output=True, text=True, timeout=10
        )
        if r.returncode == 0:
            topics = [t.strip() for t in r.stdout.split("\n") if t.strip()]
            return {"source": "icm", "topics_count": len(topics)}
    except Exception:
        pass
    
    # Try mem0
    mem0_path = HERMES_HOME / "data" / "mem0"
    if mem0_path.exists():
        count = sum(1 for _ in mem0_path.rglob("*")) if mem0_path.is_dir() else 0
        return {"source": "mem0", "approx_entries": count}
    
    return {"source": "unknown", "note": "no memory provider found"}


def get_message_stats() -> dict:
    """Get agent message bus stats."""
    from marveen import get_messages
    pending = get_messages(status="pending", limit=0)
    delivered = get_messages(status="delivered", limit=0)
    done = get_messages(status="done", limit=0)
    return {
        "pending": len(pending),
        "delivered": len(delivered),
        "done": len(done),
    }


# =============================================================================
# Dream Engine — 5 Buckets
# =============================================================================

def bucket_1_skill_suggestions(skills: list[dict], message_stats: dict) -> str:
    """Analyze daily patterns: are there repeated patterns that suggest new skills?"""
    lines = []
    
    if message_stats["done"] >= 5:
        lines.append("- 📊 Több mint 5 üzenet lett feldolgozva ma. "
                     "Ha többször ismétlődő minta volt, érdemes skill-t írni hozzá.")
    
    if len(skills) < 5:
        lines.append(f"- 🆕 Csak {len(skills)} skill telepítve. "
                     "Ha vannak ismétlődő manuális lépések, érdemes skill-t létrehozni.")
    
    # Check for very old skills that might need updates
    old_skills = [s for s in skills if s["days_since_mod"] > 30]
    if old_skills:
        lines.append(f"- 📅 {len(old_skills)} skill 30+ napja nem módosult. "
                     f"Érdemes átnézni: {', '.join(s['name'] for s in old_skills[:5])}")
    
    if not lines:
        lines.append("- ✅ Nincs kiemelt skill-javaslat. A meglévő skill-ek fedik a mintákat.")
    
    return "\n".join(lines)


def bucket_2_memory_health(mem_stats: dict) -> str:
    """Check memory health."""
    lines = []
    source = mem_stats.get("source", "unknown")
    
    if source == "icm":
        topics = mem_stats.get("topics_count", 0)
        lines.append(f"- 📚 ICM memória: {topics} topic")
        lines.append("- ✅ Memória rendszer aktív")
    elif source == "mem0":
        entries = mem_stats.get("approx_entries", 0)
        lines.append(f"- 📚 Mem0: kb. {entries} bejegyzés")
    else:
        lines.append("- ⚠️ Memória provider nem található")
    
    # Check dream engine history
    dreams = sorted(DREAMS_DIR.glob("*.md"))
    if dreams:
        days = len(dreams)
        lines.append(f"- 📋 Dream Engine: {days} éjszaka óta aktív")
    
    return "\n".join(lines)


def bucket_3_top_priorities(kanban: dict) -> str:
    """Top 3 priorities for tomorrow based on kanban state."""
    lines = []
    
    if kanban["in_progress"] > 0:
        lines.append(f"- 🔄 {kanban['in_progress']} folyamatban lévő feladat — folytatás holnap")
    
    if kanban["done_today"] > 0:
        lines.append(f"- ✅ {kanban['done_today']} feladat teljesítve ma")
    
    if kanban["total"] > 0:
        pending = kanban["total"] - kanban["in_progress"]
        lines.append(f"- 📋 {pending} hátralévő feladat a kanban táblában")
    else:
        lines.append("- 📋 Nincs kanban feladat")
    
    return "\n".join(lines)


def bucket_4_external_opportunity(day_of_year: int) -> str:
    """Weekly external opportunity check (every 7 days)."""
    if day_of_year % 7 != 0:
        return "_Heti külső keresés napja még nem esett. (Következő: 7 nap múlva)_"
    
    return ("- 🔍 Heti külső opportunity keresés napja van!\n"
            "- Érdemes új skill-eket vagy eszközöket keresni a piacon.")


def bucket_5_skill_fleet_health(skills: list[dict]) -> str:
    """Check skill fleet health."""
    lines = []
    
    if not skills:
        return "- ⚠️ Nincsenek telepített skill-ek"
    
    total = len(skills)
    recent = sum(1 for s in skills if s["days_since_mod"] < 7)
    stale = sum(1 for s in skills if s["days_since_mod"] > 60)
    
    lines.append(f"- 📦 {total} skill telepítve")
    lines.append(f"- 🆕 {recent} frissítve az elmúlt 7 napban")
    
    if stale > 0:
        lines.append(f"- ⚠️ {stale} skill 60+ napja nem módosult")
    else:
        lines.append("- ✅ Nincs elavult skill")
    
    return "\n".join(lines)


def bucket_6_soul_sync() -> str:
    """Run SOUL.md Auto-Updater and report changes.
    
    Calls soul_auto_updater.py with --apply to auto-update
    SOUL.md files and Agent Cards based on usage patterns.
    """
    script_dir = Path(__file__).parent
    updater = script_dir / "soul_auto_updater.py"
    
    if not updater.exists():
        return "- ⚠️ soul_auto_updater.py nem található"
    
    try:
        result = subprocess.run(
            [sys.executable, str(updater), "--apply"],
            capture_output=True, text=True, timeout=60,
            cwd=str(script_dir),
            env={**os.environ, "PYTHONPATH": str(script_dir)},
        )
        output = result.stdout
        error = result.stderr
        
        if result.returncode != 0:
            return f"- ⚠️ SOUL updater hiba (exit={result.returncode}): {error[:200]}"
        
        # Parse the report section from output
        changes = []
        syncs = []
        suggestions = []
        
        for line in output.split("\n"):
            line = line.strip()
            if "📌" in line:
                changes.append(line.split("📌")[-1].strip())
            elif "✅" in line and "[" in line:
                syncs.append(line.split("✅")[-1].strip())
            elif "💬" in line:
                suggestions.append(line.split("💬")[-1].strip())
        
        lines = []
        if syncs:
            lines.append(f"- 🔄 Agent Card szinkron: {len(syncs)} módosítás")
            for s in syncs[:5]:
                lines.append(f"  · {s[:80]}")
        if changes:
            lines.append(f"- 📝 SOUL.md frissítés: {len(changes)} módosítás")
            for c in changes[:5]:
                lines.append(f"  · {c[:80]}")
        if suggestions:
            lines.append(f"- 💡 Javaslatok: {len(suggestions)}")
            for s in suggestions[:3]:
                lines.append(f"  · {s[:80]}")
        if not lines:
            lines.append("- ✅ Nincs változás. Minden SOUL.md szinkronban.")
        
        return "\n".join(lines)
    
    except subprocess.TimeoutExpired:
        return "- ⚠️ SOUL updater timeout (60s)"
    except Exception as e:
        return f"- ⚠️ SOUL updater hiba: {str(e)[:200]}"


def generate_dream() -> str:
    """Generate the full dream report."""
    now = datetime.now(timezone.utc)
    day_of_year = now.timetuple().tm_yday
    
    logger.info("🌙 Dream Engine indul — 6 bucket elemzés")
    
    # Collect data
    kanban = get_kanban_stats()
    skills = get_skills_list()
    mem_stats = get_memory_stats()
    msg_stats = get_message_stats()
    
    # Generate buckets
    b1 = bucket_1_skill_suggestions(skills, msg_stats)
    b2 = bucket_2_memory_health(mem_stats)
    b3 = bucket_3_top_priorities(kanban)
    b4 = bucket_4_external_opportunity(day_of_year)
    b5 = bucket_5_skill_fleet_health(skills)
    b6 = bucket_6_soul_sync()
    
    # Assemble report
    report = f"""# 🌙 Dream Engine — {now.strftime('%Y-%m-%d')}

> Automatikus éjszakai konszolidáció — {now.strftime('%H:%M UTC')}

---

## 💡 Skill-javaslatok
{b1}

## 🧹 Memória-egészség
{b2}

## 🎯 Holnapi prioritások
{b3}

## 🌐 Külső opportunity
{b4}

## 🛠 Skill-flotta health
{b5}

## 📄 SOUL.md & Agent Card szinkron
{b6}

---

*Dream Engine automatikusan fut minden éjjel 02:00 UTC-kor. SOUL.md frissítés: többször naponta.*"""
    return report


def main():
    DREAMS_DIR.mkdir(parents=True, exist_ok=True)
    report = generate_dream()
    
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    output_path = DREAMS_DIR / f"{date_str}_DREAM.md"
    output_path.write_text(report)
    
    print(report)
    logger.info(f"✅ Dream Engine jelentés mentve: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
