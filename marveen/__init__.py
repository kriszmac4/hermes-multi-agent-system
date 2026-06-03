#!/usr/bin/env python3
"""
Marveen Integration — Core Module

Three systems:
1. Agent Message Bus (inter-agent communication)
2. Gradual Autonomy (heartbeat + trust levels)
3. Dream Engine (nightly consolidation)

Data directory: ~/.hermes/data/marveen/
"""

import json
import logging
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("marveen")

# --- Paths ---
HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
DATA_DIR = HERMES_HOME / "data" / "marveen"
DREAMS_DIR = DATA_DIR / "dreams"
MESSAGES_DB = DATA_DIR / "agent_messages.db"
AUTONOMY_CONFIG = DATA_DIR / "autonomy-config.json"
AGENT_CARDS_DIR = DATA_DIR / "agent_cards"
SKILL_REGISTRY = DATA_DIR / "skill_registry.json"

# Thread-local DB connections
_local = threading.local()


# =============================================================================
# DB LAYER (Agent Messages)
# =============================================================================

def _get_db() -> sqlite3.Connection:
    """Get thread-local SQLite connection."""
    if not hasattr(_local, "conn") or _local.conn is None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        DREAMS_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(MESSAGES_DB))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        _init_db(conn)
        _local.conn = conn
    return _local.conn


def close_db():
    """Close thread-local connection."""
    if hasattr(_local, "conn") and _local.conn:
        _local.conn.close()
        _local.conn = None


def _init_db(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS agent_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_agent TEXT NOT NULL,
            to_agent TEXT NOT NULL,
            content TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending','delivered','done','failed','read')),
            result TEXT,
            priority INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            delivered_at REAL,
            completed_at REAL
        );
        CREATE INDEX IF NOT EXISTS idx_agent_messages_status
            ON agent_messages(status, to_agent);
        CREATE INDEX IF NOT EXISTS idx_agent_messages_created
            ON agent_messages(created_at);
    """)


def create_message(from_agent: str, to_agent: str, content: str,
                   priority: int = 0) -> dict:
    conn = _get_db()
    now = time.time()
    cur = conn.execute(
        "INSERT INTO agent_messages (from_agent, to_agent, content, status, priority, created_at) "
        "VALUES (?, ?, ?, 'pending', ?, ?)",
        (from_agent, to_agent, content, priority, now)
    )
    conn.commit()
    msg_id = cur.lastrowid
    return {
        "id": msg_id,
        "from_agent": from_agent,
        "to_agent": to_agent,
        "content": content,
        "status": "pending",
        "priority": priority,
        "created_at": now,
    }


def get_pending_messages(to_agent: Optional[str] = None,
                         limit: int = 50) -> list[dict]:
    conn = _get_db()
    if to_agent:
        rows = conn.execute(
            "SELECT * FROM agent_messages "
            "WHERE status = 'pending' AND to_agent = ? "
            "ORDER BY priority DESC, created_at ASC LIMIT ?",
            (to_agent, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM agent_messages "
            "WHERE status = 'pending' "
            "ORDER BY priority DESC, created_at ASC LIMIT ?",
            (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_messages(from_agent: Optional[str] = None,
                 to_agent: Optional[str] = None,
                 status: Optional[str] = None,
                 limit: int = 50) -> list[dict]:
    conn = _get_db()
    clauses = []
    params = []
    if from_agent:
        clauses.append("from_agent = ?")
        params.append(from_agent)
    if to_agent:
        clauses.append("to_agent = ?")
        params.append(to_agent)
    if status:
        clauses.append("status = ?")
        params.append(status)
    where = " AND ".join(clauses) if clauses else "1=1"
    rows = conn.execute(
        f"SELECT * FROM agent_messages WHERE {where} "
        "ORDER BY created_at DESC LIMIT ?",
        (*params, limit)
    ).fetchall()
    return [dict(r) for r in rows]


def mark_delivered(msg_id: int) -> bool:
    conn = _get_db()
    now = time.time()
    cur = conn.execute(
        "UPDATE agent_messages SET status = 'delivered', delivered_at = ? "
        "WHERE id = ? AND status = 'pending'",
        (now, msg_id)
    )
    conn.commit()
    return cur.rowcount > 0


def mark_read(msg_id: int) -> bool:
    conn = _get_db()
    cur = conn.execute(
        "UPDATE agent_messages SET status = 'read' "
        "WHERE id = ? AND status IN ('delivered', 'pending')",
        (msg_id,)
    )
    conn.commit()
    return cur.rowcount > 0


def mark_done(msg_id: int, result: str = "") -> bool:
    conn = _get_db()
    now = time.time()
    cur = conn.execute(
        "UPDATE agent_messages SET status = 'done', result = ?, completed_at = ? "
        "WHERE id = ? AND status IN ('pending','delivered')",
        (result, now, msg_id)
    )
    conn.commit()
    return cur.rowcount > 0


def mark_failed(msg_id: int, error: str = "") -> bool:
    conn = _get_db()
    now = time.time()
    cur = conn.execute(
        "UPDATE agent_messages SET status = 'failed', result = ?, completed_at = ? "
        "WHERE id = ? AND status = 'pending'",
        (error, now, msg_id)
    )
    conn.commit()
    return cur.rowcount > 0


def cleanup_old_messages(hours: int = 72):
    """Delete messages older than `hours` that are done/failed."""
    conn = _get_db()
    cutoff = time.time() - (hours * 3600)
    conn.execute(
        "DELETE FROM agent_messages WHERE status IN ('done','failed','read') "
        "AND created_at < ?", (cutoff,)
    )
    conn.commit()


# =============================================================================
# AUTONOMY CONFIG
# =============================================================================

DEFAULT_AUTONOMY_CATEGORIES = [
    {"key": "kanban_archive_done",  "label": "Kanban archive",           "level": 3, "locked": False, "maxLevel": 3},
    {"key": "file_read",            "label": "File read",                "level": 3, "locked": False, "maxLevel": 3},
    {"key": "file_write",           "label": "File write/edit",          "level": 2, "locked": False, "maxLevel": 3},
    {"key": "git_push",             "label": "Git push",                 "level": 1, "locked": False, "maxLevel": 2},
    {"key": "git_force_push",       "label": "Git force push",           "level": 1, "locked": True,  "maxLevel": 1},
    {"key": "email_send",           "label": "Email send",               "level": 1, "locked": True,  "maxLevel": 1},
    {"key": "payment",              "label": "Payment operation",        "level": 1, "locked": True,  "maxLevel": 1},
    {"key": "deployment",           "label": "Deployment",               "level": 1, "locked": False, "maxLevel": 2},
    {"key": "research",             "label": "Research/Web scraping",    "level": 3, "locked": False, "maxLevel": 3},
    {"key": "system_maintenance",   "label": "System maintenance",       "level": 2, "locked": False, "maxLevel": 3},
    {"key": "cron_management",      "label": "Cron job management",      "level": 2, "locked": False, "maxLevel": 3},
    {"key": "memory_write",         "label": "Memory write",             "level": 3, "locked": False, "maxLevel": 3},
    {"key": "code_execution",       "label": "Code execution",           "level": 2, "locked": False, "maxLevel": 2},
    {"key": "api_call",             "label": "API call (external)",       "level": 2, "locked": False, "maxLevel": 2},
    {"key": "secret_access",        "label": "Secrets/API keys",          "level": 1, "locked": True,  "maxLevel": 1},
]


def _load_autonomy_config() -> dict:
    """Load autonomy config, merging defaults with saved overrides."""
    if not AUTONOMY_CONFIG.exists():
        return _save_autonomy_config({"version": 1, "categories": DEFAULT_AUTONOMY_CATEGORIES})
    try:
        data = json.loads(AUTONOMY_CONFIG.read_text())
    except (json.JSONDecodeError, OSError):
        logger.warning("Corrupt autonomy config, re-initializing")
        return _save_autonomy_config({"version": 1, "categories": DEFAULT_AUTONOMY_CATEGORIES})

    # Merge defaults — add any new categories without overwriting levels
    existing = {c["key"]: c for c in data.get("categories", [])}
    merged = []
    for default_cat in DEFAULT_AUTONOMY_CATEGORIES:
        if default_cat["key"] in existing:
            saved = existing[default_cat["key"]]
            # Take saved level but enforce maxLevel
            saved_level = min(saved.get("level", default_cat["level"]),
                              default_cat["maxLevel"])
            merged.append({
                **default_cat,
                "level": saved_level,
                "locked": default_cat["locked"],  # always from defaults
            })
        else:
            merged.append(dict(default_cat))
    data["categories"] = merged
    data["version"] = 1
    return _save_autonomy_config(data)


def _save_autonomy_config(data: dict) -> dict:
    AUTONOMY_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    AUTONOMY_CONFIG.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return data


def get_autonomy_level(category_key: str) -> int:
    """Get the autonomy level for a category. Returns 1 if not found."""
    config = _load_autonomy_config()
    for cat in config.get("categories", []):
        if cat["key"] == category_key:
            return cat["level"]
    return 1


def get_all_autonomy_categories() -> list[dict]:
    config = _load_autonomy_config()
    return config.get("categories", [])


def set_autonomy_level(category_key: str, level: int) -> tuple[bool, str]:
    """Set the autonomy level for a category. Returns (success, message)."""
    config = _load_autonomy_config()
    for cat in config.get("categories", []):
        if cat["key"] == category_key:
            if cat.get("locked", False):
                return False, f"Category '{cat['label']}' is locked and cannot be modified."
            max_lvl = cat.get("maxLevel", 3)
            if level < 1 or level > max_lvl:
                return False, f"Level must be between 1 and {max_lvl} (current: {level})."
            cat["level"] = level
            _save_autonomy_config(config)
            return True, f"'{cat['label']}' level set to {level}."
    return False, f"No category '{category_key}' found."


def classify_command(command: str) -> str:
    """Classify a shell command to determine which autonomy category applies."""
    cmd_lower = command.strip().lower()
    
    # Git operations
    if cmd_lower.startswith("git push --force") or cmd_lower.startswith("git push -f"):
        return "git_force_push"
    if cmd_lower.startswith("git push"):
        return "git_push"
    
    # File operations
    if any(cmd_lower.startswith(x) for x in ("rm ", "mv ", "cp ", "dd ", "mkfs", "format")):
        if any(flag in cmd_lower for flag in ("-rf", "-r", "-f", "--recursive")):
            return "system_maintenance"
        return "file_write"
    
    # Email
    if any(x in cmd_lower for x in ("sendmail", "mail ", "mutt ", "email")):
        return "email_send"
    
    # Deployment
    if any(x in cmd_lower for x in ("deploy", "kubectl", "helm ", "terraform", "cloudformation")):
        return "deployment"
    
    # Code execution
    if any(cmd_lower.startswith(x) for x in ("python", "node ", "npm ", "pip ", "cargo ", "go ")):
        return "code_execution"
    
    # API calls
    if any(x in cmd_lower for x in ("curl ", "wget ", "http ", "api")):
        return "api_call"
    
    # Default to file_read for most operations
    return "file_read"


# =============================================================================
# Agent Card Registry & Capability Discovery
# =============================================================================

def _load_all_agent_cards() -> dict[str, dict]:
    """Load all Agent Card JSON files from the registry directory.

    Returns a dict {agent_name: card_dict}. Missing/empty dir → empty dict.
    """
    if not AGENT_CARDS_DIR.exists():
        return {}
    cards: dict[str, dict] = {}
    for path in sorted(AGENT_CARDS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Skipping invalid Agent Card {path.name}: {e}")
            continue
        name = data.get("name")
        if not name:
            continue
        cards[name] = data
    return cards


def _get_agent_card(name: str) -> dict | None:
    """Return a single Agent Card by name, or None."""
    return _load_all_agent_cards().get(name)


def _score_task_against_card(task: str, card: dict) -> tuple[float, str | None, str]:
    """Score a task description against an Agent Card.

    Returns (score, best_skill_id, reasoning).

    Scoring (simple, deterministic — no embeddings needed):
      +3.0  per keyword match (whole-word, case-insensitive)
      +1.0  if the keyword appears as a substring inside the task
      +1.5  if any token from skill.description appears in the task
      +0.5  per token overlap with card.description
      -2.0  if agent is the fallback (we prefer specialists when they match)
    """
    if not task:
        return 0.0, None, ""

    task_lower = task.lower()
    task_tokens = set(task_lower.split())

    best_score = 0.0
    best_skill_id: str | None = None
    best_skill_score = 0.0
    matched_keywords: list[str] = []

    for skill in card.get("skills", []):
        skill_id = skill.get("id", "")
        skill_desc = (skill.get("description", "")).lower()
        skill_score = 0.0

        # Keyword match
        for kw in skill.get("keywords", []):
            kw_lower = kw.lower()
            if not kw_lower:
                continue
            if kw_lower in task_tokens:
                skill_score += 3.0
                matched_keywords.append(kw)
            elif kw_lower in task_lower:
                skill_score += 1.0
                matched_keywords.append(kw)

        # Description overlap (looser)
        for word in skill_desc.split():
            w = word.strip(".,:;()")
            if len(w) > 3 and w in task_lower:
                skill_score += 1.5
                break

        if skill_score > best_skill_score:
            best_skill_score = skill_score
            best_skill_id = skill_id

        best_score += skill_score

    # Card-level description match
    card_desc = (card.get("description", "")).lower()
    for token in card_desc.split():
        w = token.strip(".,:;()")
        if len(w) > 4 and w in task_lower:
            best_score += 0.5

    # Fallback penalty
    if card.get("is_fallback"):
        best_score -= 2.0

    if matched_keywords:
        reasoning = f"matched: {', '.join(matched_keywords[:5])}"
    else:
        reasoning = "no keyword match"

    return best_score, best_skill_id, reasoning


def discover_agents(task: str, top_k: int = 3, min_score: float = 1.0) -> list[dict]:
    """Find the best-matching agents for a given task description.

    Returns a list of result dicts, sorted by score (descending):
        [
          {
            "agent": "dev",
            "display_name": "Dev Agent",
            "score": 7.5,
            "skill": "implement-feature",
            "reasoning": "matched: implement, build feature",
            "model": "DS-V4-Flash",
            "autonomy_level": 2
          },
          ...
        ]

    `min_score` filters out noise — if the best match is below threshold,
    returns the orchestrator as a safe default.
    """
    cards = _load_all_agent_cards()
    if not cards:
        return []

    results: list[dict] = []
    for name, card in cards.items():
        score, skill_id, reasoning = _score_task_against_card(task, card)
        results.append({
            "agent": name,
            "display_name": card.get("display_name", name),
            "score": round(score, 2),
            "skill": skill_id,
            "reasoning": reasoning,
            "model": card.get("model"),
            "autonomy_level": card.get("autonomy_level", 3),
            "is_fallback": card.get("is_fallback", False),
        })

    results.sort(key=lambda r: r["score"], reverse=True)

    # Filter below threshold; if nothing qualifies, fall back to orchestrator
    qualified = [r for r in results if r["score"] >= min_score]
    if not qualified:
        orch = next((r for r in results if r["agent"] == "orchestrator"), None)
        return [orch] if orch else results[:1]

    return qualified[:top_k]


def list_agent_cards() -> list[dict]:
    """Return minimal summaries of all registered Agent Cards."""
    cards = _load_all_agent_cards()
    out = []
    for name, card in cards.items():
        out.append({
            "agent": name,
            "display_name": card.get("display_name", name),
            "description": card.get("description", ""),
            "skills": [s.get("id") for s in card.get("skills", [])],
            "model": card.get("model"),
            "is_fallback": card.get("is_fallback", False),
        })
    return out


def record_skill_invocation(agent: str, skill: str, task_excerpt: str = "") -> None:
    """Append a skill invocation record to skill_registry.json.

    Used by Phase 3 router — feeds the skill-match learning loop.
    """
    SKILL_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    if SKILL_REGISTRY.exists():
        try:
            data = json.loads(SKILL_REGISTRY.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {"version": 1, "invocations": []}
    else:
        data = {"version": 1, "invocations": []}

    data.setdefault("invocations", []).append({
        "ts": datetime.now(timezone.utc).isoformat(),
        "agent": agent,
        "skill": skill,
        "task_excerpt": task_excerpt[:200],
    })
    # Keep last 500 invocations
    data["invocations"] = data["invocations"][-500:]

    SKILL_REGISTRY.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
