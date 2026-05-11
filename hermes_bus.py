#!/usr/bin/env python3
"""Hermes Message Bus — Inter-agent communication via SQLite.

Replaces noisy Discord delegation messages with a clean internal bus.
Discord only shows brief indicators, full communication goes through the bus.

Architecture:
- SQLite WAL-mode database for concurrent access from multiple bridge processes
- Async-safe with asyncio.Lock for bridge integration
- Fallback-friendly: if bus fails, bridge falls back to Discord-only mode
- Auto-cleanup: messages older than 24h are pruned

Usage:
    bus = HermesBus()
    msg_id = bus.send("general", "dev", "delegation", "Írj Python scriptet...")
    msgs = bus.receive("dev")  # Returns pending messages for dev
    bus.complete(msg_id, result="Script megírva...")
    history = bus.get_history("dev", limit=20)
    bus.cleanup()
"""

import json
import sqlite3
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


DB_PATH = Path.home() / ".hermes" / "discord-multi-agent" / "bus.db"
MAX_CONTENT_LENGTH = 50000  # 50KB max per message content
DEFAULT_MAX_AGE_HOURS = 24


@dataclass
class BusMessage:
    """A message in the bus."""
    id: int = 0
    from_agent: str = ""
    to_agent: str = ""  # "broadcast" for all agents
    type: str = ""  # delegation, result, info, escalation
    content: str = ""
    thread_id: str = ""
    parent_msg_id: str = ""  # Original Discord message ID (for reference)
    status: str = "pending"  # pending, in_progress, completed, failed
    created_at: float = 0.0
    completed_at: float = 0.0
    result: str = ""
    metadata: dict = field(default_factory=dict)  # Flexible JSON metadata

    @property
    def elapsed_seconds(self) -> float:
        """Time from creation to completion (0 if not completed)."""
        if self.completed_at and self.created_at:
            return self.completed_at - self.created_at
        return 0.0

    @property
    def age_seconds(self) -> float:
        """Time since creation."""
        return time.time() - self.created_at if self.created_at else 0.0


class HermesBus:
    """SQLite-based message bus for inter-agent communication."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize database with WAL mode for concurrent access."""
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_agent TEXT NOT NULL,
                to_agent TEXT NOT NULL,
                type TEXT NOT NULL,
                content TEXT NOT NULL,
                thread_id TEXT DEFAULT '',
                parent_msg_id TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                created_at REAL NOT NULL,
                completed_at REAL DEFAULT 0,
                result TEXT DEFAULT '',
                metadata TEXT DEFAULT '{}'
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_to_agent_status 
            ON messages(to_agent, status)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_from_agent 
            ON messages(from_agent, created_at)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_created_at 
            ON messages(created_at)
        """)
        conn.commit()
        conn.close()

    def _get_conn(self) -> sqlite3.Connection:
        """Get a new connection (SQLite with WAL mode supports concurrent reads)."""
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.row_factory = sqlite3.Row
        return conn

    def _row_to_message(self, row) -> BusMessage:
        """Convert a database row to a BusMessage."""
        return BusMessage(
            id=row["id"],
            from_agent=row["from_agent"],
            to_agent=row["to_agent"],
            type=row["type"],
            content=row["content"],
            thread_id=row["thread_id"],
            parent_msg_id=row["parent_msg_id"],
            status=row["status"],
            created_at=row["created_at"],
            completed_at=row["completed_at"],
            result=row["result"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )

    def send(
        self,
        from_agent: str,
        to_agent: str,
        type: str,
        content: str,
        thread_id: str = "",
        parent_msg_id: str = "",
        metadata: Optional[dict] = None,
    ) -> int:
        """Send a message through the bus. Returns the message ID.

        Args:
            from_agent: Sender agent name (e.g., "general", "dev")
            to_agent: Recipient agent name, or "broadcast" for all
            type: Message type: delegation, result, info, escalation
            content: Message content (can be long)
            thread_id: Optional thread identifier for grouping related messages
            parent_msg_id: Optional Discord message ID of the original user message
            metadata: Optional JSON metadata dict

        Returns:
            Message ID
        """
        content = content[:MAX_CONTENT_LENGTH]
        metadata_json = json.dumps(metadata or {}, ensure_ascii=False)

        conn = self._get_conn()
        try:
            cursor = conn.execute(
                """INSERT INTO messages (from_agent, to_agent, type, content, 
                   thread_id, parent_msg_id, status, created_at, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
                (from_agent, to_agent, type, content, thread_id, parent_msg_id, time.time(), metadata_json),
            )
            conn.commit()
            msg_id = cursor.lastrowid
            return msg_id or 0
        finally:
            conn.close()

    def receive(self, agent: str, limit: int = 50) -> list[BusMessage]:
        """Get pending messages for an agent (status='pending' or 'in_progress').

        Also includes broadcast messages.

        Args:
            agent: Agent name to receive messages for
            limit: Maximum messages to return

        Returns:
            List of BusMessage objects, newest first
        """
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT * FROM messages 
                   WHERE (to_agent = ? OR to_agent = 'broadcast')
                   AND status IN ('pending', 'in_progress')
                   ORDER BY created_at ASC LIMIT ?""",
                (agent, limit),
            ).fetchall()
            messages = [self._row_to_message(row) for row in rows]

            # Mark as in_progress
            if messages:
                msg_ids = [str(m.id) for m in messages]
                conn.execute(
                    f"UPDATE messages SET status = 'in_progress' WHERE id IN ({','.join(msg_ids)})"
                )
                conn.commit()

            return messages
        finally:
            conn.close()

    def complete(self, msg_id: int, result: str = "") -> bool:
        """Mark a message as completed with a result.

        Args:
            msg_id: Message ID to complete
            result: Result content

        Returns:
            True if successful
        """
        result = result[:MAX_CONTENT_LENGTH]

        conn = self._get_conn()
        try:
            conn.execute(
                """UPDATE messages SET status = 'completed', completed_at = ?, result = ?
                   WHERE id = ?""",
                (time.time(), result, msg_id),
            )
            conn.commit()
            return conn.total_changes > 0
        finally:
            conn.close()

    def fail(self, msg_id: int, error: str = "") -> bool:
        """Mark a message as failed.

        Args:
            msg_id: Message ID to mark as failed
            error: Error description

        Returns:
            True if successful
        """
        conn = self._get_conn()
        try:
            conn.execute(
                """UPDATE messages SET status = 'failed', completed_at = ?, result = ?
                   WHERE id = ?""",
                (time.time(), error[:1000], msg_id),
            )
            conn.commit()
            return conn.total_changes > 0
        finally:
            conn.close()

    def get_completed(
        self, from_agent: str = "", to_agent: str = "", since: float = 0, limit: int = 50
    ) -> list[BusMessage]:
        """Get completed messages, optionally filtered by sender/receiver.

        Args:
            from_agent: Filter by sender (empty = all)
            to_agent: Filter by recipient (empty = all)
            since: Unix timestamp, only messages completed after this time
            limit: Maximum messages to return

        Returns:
            List of BusMessage objects, newest first
        """
        conn = self._get_conn()
        try:
            query = "SELECT * FROM messages WHERE status = 'completed' AND completed_at >= ?"
            params: list = [since]

            if from_agent:
                query += " AND from_agent = ?"
                params.append(from_agent)
            if to_agent:
                query += " AND to_agent = ?"
                params.append(to_agent)

            query += " ORDER BY completed_at DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            return [self._row_to_message(row) for row in rows]
        finally:
            conn.close()

    def get_pending_count(self, agent: str) -> int:
        """Get the number of pending messages for an agent."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                """SELECT COUNT(*) as cnt FROM messages
                   WHERE (to_agent = ? OR to_agent = 'broadcast')
                   AND status IN ('pending', 'in_progress')""",
                (agent,),
            ).fetchone()
            return row["cnt"] if row else 0
        finally:
            conn.close()

    def get_history(
        self, agent: str = "", from_agent: str = "", to_agent: str = "",
        limit: int = 50, offset: int = 0
    ) -> list[BusMessage]:
        """Get message history, optionally filtered.

        Args:
            agent: Show messages involving this agent (as sender OR receiver)
            from_agent: Filter by sender
            to_agent: Filter by receiver
            limit: Maximum messages to return
            offset: Offset for pagination

        Returns:
            List of BusMessage objects, newest first
        """
        conn = self._get_conn()
        try:
            query = "SELECT * FROM messages WHERE 1=1"
            params: list = []

            if agent:
                query += " AND (from_agent = ? OR to_agent = ? OR to_agent = 'broadcast')"
                params.extend([agent, agent])
            if from_agent:
                query += " AND from_agent = ?"
                params.append(from_agent)
            if to_agent:
                query += " AND to_agent = ?"
                params.append(to_agent)

            query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            rows = conn.execute(query, params).fetchall()
            return [self._row_to_message(row) for row in rows]
        finally:
            conn.close()

    def get_message(self, msg_id: int) -> Optional[BusMessage]:
        """Get a specific message by ID."""
        conn = self._get_conn()
        try:
            row = conn.execute("SELECT * FROM messages WHERE id = ?", (msg_id,)).fetchone()
            return self._row_to_message(row) if row else None
        finally:
            conn.close()

    def cleanup(self, max_age_hours: float = DEFAULT_MAX_AGE_HOURS) -> int:
        """Remove old messages from the bus.

        Args:
            max_age_hours: Maximum age in hours (default 24)

        Returns:
            Number of messages removed
        """
        cutoff = time.time() - (max_age_hours * 3600)
        conn = self._get_conn()
        try:
            # Clean up completed/failed messages older than cutoff
            cursor = conn.execute(
                "DELETE FROM messages WHERE created_at < ? AND status IN ('completed', 'failed')",
                (cutoff,),
            )
            # Also clean up stale in_progress messages (older than 1 hour = abandoned)
            stale_cursor = conn.execute(
                "DELETE FROM messages WHERE status = 'in_progress' AND created_at < ?",
                (time.time() - 3600,),
            )
            conn.commit()
            return cursor.rowcount + stale_cursor.rowcount
        finally:
            conn.close()

    def get_stats(self) -> dict:
        """Get bus statistics."""
        conn = self._get_conn()
        try:
            total = conn.execute("SELECT COUNT(*) as c FROM messages").fetchone()["c"]
            pending = conn.execute(
                "SELECT COUNT(*) as c FROM messages WHERE status = 'pending'"
            ).fetchone()["c"]
            in_progress = conn.execute(
                "SELECT COUNT(*) as c FROM messages WHERE status = 'in_progress'"
            ).fetchone()["c"]
            completed = conn.execute(
                "SELECT COUNT(*) as c FROM messages WHERE status = 'completed'"
            ).fetchone()["c"]
            failed = conn.execute(
                "SELECT COUNT(*) as c FROM messages WHERE status = 'failed'"
            ).fetchone()["c"]

            # By type
            by_type = {}
            for row in conn.execute(
                "SELECT type, COUNT(*) as c FROM messages GROUP BY type"
            ).fetchall():
                by_type[row["type"]] = row["c"]

            # By agent (from)
            by_from = {}
            for row in conn.execute(
                "SELECT from_agent, COUNT(*) as c FROM messages GROUP BY from_agent"
            ).fetchall():
                by_from[row["from_agent"]] = row["c"]

            # By agent (to)
            by_to = {}
            for row in conn.execute(
                "SELECT to_agent, COUNT(*) as c FROM messages GROUP BY to_agent"
            ).fetchall():
                by_to[row["to_agent"]] = row["c"]

            return {
                "total": total,
                "pending": pending,
                "in_progress": in_progress,
                "completed": completed,
                "failed": failed,
                "by_type": by_type,
                "by_from": by_from,
                "by_to": by_to,
                "db_path": str(self.db_path),
            }
        finally:
            conn.close()

    def format_indicator(self, msg: BusMessage) -> str:
        """Format a brief Discord indicator for a bus message.

        Returns a short string suitable for Discord #team channel,
        summarizing the bus activity without the full content.
        """
        type_emojis = {
            "delegation": "🔬",
            "result": "✅",
            "escalation": "🔄",
            "info": "💾",
        }

        emoji = type_emojis.get(msg.type, "📡")

        # Extract short topic from content (first 60 chars)
        topic = msg.content.replace("\n", " ")[:60]
        if len(msg.content) > 60:
            topic = topic.rstrip() + "..."

        if msg.type == "delegation":
            return f"{emoji} **{msg.from_agent.title()} → {msg.to_agent.title()}**: konzultáció indult"
        elif msg.type == "result":
            elapsed = msg.elapsed_seconds
            time_str = f" ({elapsed:.1f}s)" if elapsed else ""
            return f"{emoji} **{msg.from_agent.title()} válaszolt**{time_str}"
        elif msg.type == "escalation":
            skill = msg.metadata.get("skill_area", "")
            skill_str = f" ({skill})" if skill else ""
            return f"{emoji} **{msg.from_agent.title()} → {msg.to_agent.title()}**: eszkaláció{skill_str}"
        elif msg.type == "info":
            return f"{emoji} **{msg.from_agent.title()} → {msg.to_agent.title()}**: {topic}"
        else:
            return f"{emoji} **{msg.from_agent.title()} → {msg.to_agent.title()}**: {msg.type}"


# CLI interface for debugging and monitoring
if __name__ == "__main__":
    import sys

    bus = HermesBus()

    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "status":
        stats = bus.get_stats()
        print(f"📊 Hermes Bus Status")
        print(f"   DB: {stats['db_path']}")
        print(f"   Total: {stats['total']} messages")
        print(f"   Pending: {stats['pending']} | In Progress: {stats['in_progress']} | Completed: {stats['completed']} | Failed: {stats['failed']}")
        print(f"   By type: {json.dumps(stats['by_type'], ensure_ascii=False)}")
        print(f"   By from: {json.dumps(stats['by_from'], ensure_ascii=False)}")
        print(f"   By to: {json.dumps(stats['by_to'], ensure_ascii=False)}")

    elif cmd == "history":
        agent = ""
        from_agent = ""
        limit = 20

        args = sys.argv[2:]
        i = 0
        while i < len(args):
            if args[i] == "--from":
                from_agent = args[i + 1]
                i += 2
            elif args[i] == "--to":
                agent = args[i + 1]  # "to" filter
                i += 2
            elif args[i] == "--agent":
                agent = args[i + 1]
                i += 2
            elif args[i] == "--limit":
                limit = int(args[i + 1])
                i += 2
            else:
                i += 1

        messages = bus.get_history(
            agent=agent, from_agent=from_agent, to_agent=agent, limit=limit
        )
        if not messages:
            print("No messages found.")
        else:
            for m in messages:
                indicator = bus.format_indicator(m)
                print(f"  [{m.id}] {indicator}")
                print(f"      Status: {m.status} | From: {m.from_agent} → To: {m.to_agent}")
                print(f"      Content: {m.content[:120]}...")
                print()

    elif cmd == "cleanup":
        max_age = DEFAULT_MAX_AGE_HOURS
        args = sys.argv[2:]
        i = 0
        while i < len(args):
            if args[i] == "--max-age-hours":
                max_age = float(args[i + 1])
                i += 2
            else:
                i += 1

        removed = bus.cleanup(max_age)
        print(f"🧹 Cleaned up {removed} messages older than {max_age}h")

    elif cmd == "send":
        # Quick test: python hermes_bus.py send general dev delegation "Test message"
        from_ag = sys.argv[2] if len(sys.argv) > 2 else "general"
        to_ag = sys.argv[3] if len(sys.argv) > 3 else "dev"
        msg_type = sys.argv[4] if len(sys.argv) > 4 else "info"
        content = sys.argv[5] if len(sys.argv) > 5 else "Test message"
        msg_id = bus.send(from_ag, to_ag, msg_type, content)
        print(f"✅ Message sent: ID={msg_id}")

    elif cmd == "receive":
        agent = sys.argv[2] if len(sys.argv) > 2 else "dev"
        messages = bus.receive(agent)
        if not messages:
            print(f"No pending messages for {agent}")
        else:
            for m in messages:
                print(f"  [{m.id}] {m.from_agent} → {m.to_agent} ({m.type})")
                print(f"      {m.content[:200]}")
                print()

    elif cmd == "complete":
        msg_id = int(sys.argv[2]) if len(sys.argv) > 2 else 0
        result = sys.argv[3] if len(sys.argv) > 3 else "Done"
        if msg_id:
            bus.complete(msg_id, result)
            print(f"✅ Message {msg_id} completed")
        else:
            print("Usage: python hermes_bus.py complete <msg_id> [result]")

    elif cmd == "delegate":
        """Delegate a task with automatic mem0 context injection.
        
        Usage: python hermes_bus.py delegate <from_agent> <to_agent> <task_description>
        Example: python hermes_bus.py delegate general dev "Írj Python scriptet..."
        
        Automatically injects relevant mem0 facts (shared + specialist) into the task context.
        """
        from_ag = sys.argv[2] if len(sys.argv) > 2 else "general"
        to_ag = sys.argv[3] if len(sys.argv) > 3 else "dev"
        task = sys.argv[4] if len(sys.argv) > 4 else "No task description"
        
        # Inject mem0 context
        mem0_context = ""
        try:
            from mem0_integration import shared_memory
            facts = shared_memory.get_relevant_facts(task, to_ag)
            if facts:
                mem0_context = f"\n\n--- Relevant context from team memory ---\n{facts}\n--- End context ---"
                print(f"🧠 Injected {len(facts)} chars of mem0 context")
        except Exception as e:
            print(f"⚠️ mem0 context injection skipped: {e}")
        
        full_content = task + mem0_context
        msg_id = bus.send(from_ag, to_ag, "delegation", full_content)
        print(f"✅ Delegation sent: ID={msg_id} ({from_ag} → {to_ag})")

    elif cmd == "context":
        """Query mem0 context for an agent.
        
        Usage: python hermes_bus.py context <agent> <query>
        Example: python hermes_bus.py context dev "Python package manager"
        """
        agent = sys.argv[2] if len(sys.argv) > 2 else "general"
        query = sys.argv[3] if len(sys.argv) > 3 else ""
        
        if not query:
            print("Usage: python hermes_bus.py context <agent> <query>")
            sys.exit(1)
        
        try:
            from mem0_integration import shared_memory
            facts = shared_memory.get_relevant_facts(query, agent)
            if facts:
                print(f"🧠 Context for {agent} (query: '{query}'):")
                print(facts)
            else:
                print(f"No relevant context found for {agent}")
        except Exception as e:
            print(f"⚠️ mem0 unavailable: {e}")

    else:
        print(f"Unknown command: {cmd}")
        print("Commands: status, history, cleanup, send, receive, complete, delegate, context")