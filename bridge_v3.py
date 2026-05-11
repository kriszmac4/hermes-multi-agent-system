#!/usr/bin/env python3
"""Hermes Discord Bridge v6 - Multi-model, SOUL.md, team delegation + Message Bus.

Architecture:
- #general: Krisztian's input → General (coordinator) processes it
- #team: Brief indicators only (bus handles full communication)
- #human: Bots ask Krisztian for approval
- Home channels: Direct questions to each specialist
- Message Bus (SQLite): Inter-agent communication — quiet, fast, traceable

Key changes over v5:
- Message Bus (hermes_bus.py) for inter-agent communication
- Discord #team shows brief indicators, not full conversations
- Full context goes through the bus (SQLite), not Discord channels
- Fallback to Discord-only mode if bus is unavailable
"""

import asyncio
import json
import os
import re
import time
import aiohttp
import discord
from pathlib import Path
from openai import AsyncOpenAI
from token_logger import TokenLogger as _TokenLogger

# Token usage logger — logs every API call to SQLite
_token_logger = _TokenLogger(db_path=str(Path(__file__).parent / "data" / "token_usage.db"))

# Message Bus for inter-agent communication
try:
    from hermes_bus import HermesBus, DB_PATH as BUS_DB_PATH
    _bus = HermesBus()
    BUS_AVAILABLE = True
    print(f"🚌 Message Bus initialized: {BUS_DB_PATH}")
except Exception as e:
    print(f"⚠️ Message Bus unavailable, falling back to Discord-only mode: {e}")
    _bus = None
    BUS_AVAILABLE = False

CONFIG_PATH = Path.home() / ".hermes" / "discord-multi-agent" / "config.json"
PROFILES_DIR = Path.home() / ".hermes" / "profiles"
ENV_PATH = Path.home() / ".hermes" / ".env"

# Bot IDs for detecting bot messages
BOT_IDS = {
    "general": "1501141496487870524",
    "research": "1501139324861681736",
    "dev": "1501140611506372760",
    "devops": "1501141067607707829",
    "news": "1501141173530792027",
    "study": "1501611238747013180",
    "fitness": "1502331755263426711",
}
ALL_BOT_IDS = set(BOT_IDS.values())

TASKS_FILE = Path.home() / ".hermes" / "discord-multi-agent" / "tasks.json"
DEV_FILE = Path.home() / ".hermes" / "discord-multi-agent" / "development.json"
KB_FILE = Path.home() / ".hermes" / "discord-multi-agent" / "team-knowledge.md"

# Thread tracking: thread_id -> {"parent": channel_id, "delegated_to": [agent_names], "original_msg": str, "created_at": float}
TEAM_THREADS = {}


class DevelopmentTracker:
    """Track specialist capabilities and skill development over time."""

    def __init__(self):
        self.data = self._load()

    def _load(self) -> dict:
        if DEV_FILE.exists():
            try:
                return json.loads(DEV_FILE.read_text())
            except:
                pass
        return {
            "capabilities": {},  # agent -> {skill: {score, attempts, successes, last_used}}
            "escalations": [],   # [{from, to, reason, timestamp, resolution}]
            "learnings": [],     # [{agent, skill, note, timestamp}]
            "last_summary": 0,
        }

    def _save(self):
        # Keep only last 200 escalations and 100 learnings
        if len(self.data["escalations"]) > 200:
            self.data["escalations"] = self.data["escalations"][-200:]
        if len(self.data["learnings"]) > 100:
            self.data["learnings"] = self.data["learnings"][-100:]
        DEV_FILE.write_text(json.dumps(self.data, indent=2, ensure_ascii=False))

    def record_escalation(self, from_agent: str, reason: str, original_msg: str = ""):
        """Record that a specialist couldn't handle a task and escalated to General."""
        self.data["escalations"].append({
            "from": from_agent,
            "to": "general",
            "reason": reason[:200],
            "original_msg": original_msg[:200],
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "resolution": None,  # Filled after General resolves it
        })
        self._save()

    def record_resolution(self, from_agent: str, resolved_by: str, skill_area: str):
        """Record that General successfully resolved an escalation by delegating to the right specialist."""
        # Find the most recent unresolved escalation from this agent
        for esc in reversed(self.data["escalations"]):
            if esc["from"] == from_agent and esc["resolution"] is None:
                esc["resolution"] = resolved_by
                esc["skill_area"] = skill_area
                break

        # Update capability scores
        cap = self.data["capabilities"]
        if resolved_by not in cap:
            cap[resolved_by] = {}
        if skill_area not in cap[resolved_by]:
            cap[resolved_by][skill_area] = {"attempts": 0, "successes": 0, "score": 50, "last_used": ""}
        cap[resolved_by][skill_area]["attempts"] += 1
        cap[resolved_by][skill_area]["successes"] += 1
        cap[resolved_by][skill_area]["score"] = min(100, 50 + cap[resolved_by][skill_area]["successes"] * 10)
        cap[resolved_by][skill_area]["last_used"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        self._save()

    def record_task_success(self, agent: str, skill_area: str):
        """Record that an agent successfully completed a task in a skill area."""
        cap = self.data["capabilities"]
        if agent not in cap:
            cap[agent] = {}
        if skill_area not in cap[agent]:
            cap[agent][skill_area] = {"attempts": 0, "successes": 0, "score": 50, "last_used": ""}
        cap[agent][skill_area]["attempts"] += 1
        cap[agent][skill_area]["successes"] += 1
        cap[agent][skill_area]["score"] = min(100, 50 + cap[agent][skill_area]["successes"] * 10)
        cap[agent][skill_area]["last_used"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        self._save()

    def record_task_failure(self, agent: str, skill_area: str):
        """Record that an agent failed a task (escapable)."""
        cap = self.data["capabilities"]
        if agent not in cap:
            cap[agent] = {}
        if skill_area not in cap[agent]:
            cap[agent][skill_area] = {"attempts": 0, "successes": 0, "score": 50, "last_used": ""}
        cap[agent][skill_area]["attempts"] += 1
        cap[agent][skill_area]["score"] = max(0, cap[agent][skill_area].get("score", 50) - 2)
        cap[agent][skill_area]["last_used"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        self._save()

    def add_learning(self, agent: str, skill_area: str, note: str):
        """Record a learning/growth note for an agent."""
        self.data["learnings"].append({
            "agent": agent,
            "skill_area": skill_area,
            "note": note[:200],
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        self._save()

    def get_best_agent_for(self, skill_area: str) -> str:
        """Return the agent with the highest capability score for a skill area."""
        best_agent = None
        best_score = -1
        for agent, skills in self.data["capabilities"].items():
            if skill_area in skills:
                if skills[skill_area]["score"] > best_score:
                    best_score = skills[skill_area]["score"]
                    best_agent = agent
        return best_agent  # None if no agent has experience in this area

    def get_capability_report(self) -> str:
        """Generate a development report for General to see who's best at what."""
        lines = ["📊 **Képesség-pontszámok:**"]
        cap = self.data["capabilities"]
        for agent, skills in sorted(cap.items()):
            for skill, data in sorted(skills.items()):
                bar = "█" * (data["score"] // 10) + "░" * (10 - data["score"] // 10)
                lines.append(f"  {agent.title()} → {skill}: {bar} {data['score']}/100 ({data['successes']}/{data['attempts']} sikeres)")

        # Recent escalations
        recent_esc = [e for e in self.data["escalations"][-10:] if e.get("resolution")]
        if recent_esc:
            lines.append("\n🔄 **Utoljára eszkált feladatok:**")
            for e in recent_esc[-5:]:
                lines.append(f"  {e['from'].title()} → {e['resolution'].title()} ({e.get('skill_area', '?')})")

        return "\n".join(lines)

    def update_team_knowledge(self):
        """Auto-update team-knowledge.md with newly discovered capabilities.
        
        When a specialist successfully handles tasks outside their primary area,
        this appends a learning note to team-knowledge.md so the whole team
        knows about this new capability.
        """
        if not KB_FILE.exists():
            return
        
        try:
            kb_content = KB_FILE.read_text()
            new_entries = []
            
            for agent, skills in self.data["capabilities"].items():
                for skill_area, data in skills.items():
                    # Only record if the agent has proven competence (score >= 70, >= 3 successes)
                    if data["score"] >= 70 and data["successes"] >= 3:
                        # Check if this capability is already documented
                        search_line = f"{agent.title()} → {skill_area}"
                        if search_line.lower() not in kb_content.lower():
                            entry = f"- {agent.title()} → {skill_area}: {data['score']}/100 ({data['successes']}/{data['attempts']} sikeres) — *auto-tanult*"
                            new_entries.append(entry)
            
            if new_entries:
                # Find the "Fejlődési napló" section or append before "Delegációs Kulcsszavak"
                if "### Fejlődési napló" in kb_content:
                    # Append to existing section
                    insert_marker = "### Fejlődési napló"
                    idx = kb_content.index(insert_marker)
                    after_marker = kb_content[idx + len(insert_marker):]
                    # Find next ### or end
                    next_section = after_marker.find("\n### ")
                    if next_section == -1:
                        next_section = len(after_marker)
                    section_content = after_marker[:next_section]
                    new_section = section_content.rstrip() + "\n" + "\n".join(new_entries) + "\n"
                    kb_content = kb_content[:idx + len(insert_marker)] + new_section + after_marker[next_section:]
                else:
                    # Create new section before "Delegációs Kulcsszavak"
                    section = "\n### Fejlődési napló\n" + "\n".join(new_entries) + "\n\n"
                    kb_content = kb_content.replace("### Delegációs Kulcsszavak", section + "### Delegációs Kulcsszavak")
                
                KB_FILE.write_text(kb_content)
                return len(new_entries)
        except Exception as e:
            print(f"⚠️ Failed to update team-knowledge.md: {e}")
            return 0
        
        return 0


class TaskTracker:
    """LangGraph-inspired state machine for task lifecycle tracking."""

    def __init__(self):
        self.tasks = self._load()

    def _load(self) -> dict:
        if TASKS_FILE.exists():
            try:
                return json.loads(TASKS_FILE.read_text())
            except:
                pass
        return {"tasks": [], "last_cleanup": 0}

    def _save(self):
        # Cleanup old completed tasks (keep only last 50)
        if len(self.tasks["tasks"]) > 50:
            self.tasks["tasks"] = [t for t in self.tasks["tasks"] if t["status"] != "COMPLETED"][-50:]
        TASKS_FILE.write_text(json.dumps(self.tasks, indent=2, ensure_ascii=False))

    def create_task(self, original_msg: str, assigned_to: str, result_channel: str = "general") -> dict:
        """Create a new PENDING task. Returns task dict."""
        task_id = f"task_{int(time.time() * 1000)}"
        task = {
            "id": task_id,
            "status": "PENDING",
            "from": "Krisztian",
            "original_msg": original_msg[:500],
            "assigned_to": assigned_to,
            "delegated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "result_channel": result_channel,
            "general_summary": "",
            "result_summary": None,
            "skill_area": None,  # NEW: track what skill area this task belongs to
            "escalated_from": None,  # NEW: if this was an escalation, who escalated
        }
        self.tasks["tasks"].append(task)
        self._save()
        return task

    def start_task(self, task_id: str):
        """Mark task as IN_PROGRESS when specialist picks it up."""
        for t in self.tasks["tasks"]:
            if t["id"] == task_id:
                t["status"] = "IN_PROGRESS"
                self._save()
                return t
        return None

    def complete_task(self, task_id: str, result_summary: str):
        """Mark task as COMPLETED when specialist finishes."""
        for t in self.tasks["tasks"]:
            if t["id"] == task_id:
                t["status"] = "COMPLETED"
                t["result_summary"] = result_summary[:500]
                self._save()
                return t
        return None

    def find_pending_for(self, agent: str) -> list:
        """Find PENDING tasks assigned to this agent."""
        return [t for t in self.tasks["tasks"] if t["assigned_to"] == agent and t["status"] == "PENDING"]

    def find_recent_completed(self, since_minutes: int = 30) -> list:
        """Find recently completed tasks for synthesis."""
        cutoff = time.time() - (since_minutes * 60)
        return [t for t in self.tasks["tasks"] if t["status"] == "COMPLETED" and not t.get("synthesized")]

    def mark_synthesized(self, task_id: str):
        """Mark task as synthesized (General already summarized it to Krisztian)."""
        for t in self.tasks["tasks"]:
            if t["id"] == task_id:
                t["synthesized"] = True
                self._save()
                return


task_tracker = TaskTracker()
dev_tracker = DevelopmentTracker()


def load_env():
    """Load API keys from .env file if not in environment."""
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, _, value = line.partition('=')
                key = key.strip()
                value = value.strip()
                if key and value and key not in os.environ:
                    os.environ[key] = value


# Models that support vision (image input) through OpenCode Go API
VISION_CAPABLE_MODELS = {
    "glm-5.1",       # GLM-5.1 supports vision
    "glm-5",          # GLM-5 supports vision
    "deepseek-v4-pro", # DS-V4-Pro may support vision via OpenCode Go
}

AGENT_MODELS = {
    "general": "glm-5.1",
    "research": "glm-5.1",
    "dev": "deepseek-v4-flash",
    "devops": "minimax-m2.5",
    "news": "deepseek-v4-flash",
    "study": "glm-5",
    "fitness": "deepseek-v4-flash",
}

AGENT_EFFORT = {
    "general": "medium",
    "research": "high",
    "dev": "low",
    "devops": "low",
    "news": "low",
    "study": "medium",
    "fitness": "low",
}

# === AUTO-ESCALATION: Detect "I can't" responses and route to the right specialist ===
CANT_DO_PATTERNS = [
    r"(?i)nem tudom\s+(megcsinálni|létrehozni|megoldani|ellátni|kezelni|megválaszolni)",
    r"(?i)nem (vagyok|tudok|tudom) (képes|felkészült|hozzávalóded)",
    r"(?i)ez (nem az én |nem a |kívül) (szakterületem|területem|kompetenciám)",
    r"(?i)I can't (do|help with|handle|create|solve|access|perform)",
    "(?i)I don't have (access|capability|permission|the ability)",
    r"(?i)kívül (esik|van a) (szakterületem|területem|kompetenciámon)",
    r"(?i)javaslom.*(@|specialist|szakértő|kolléga)",
    r"(?i)nem támogatj?a (a )?(kép|képfeldolgozás|vision|image)",
    r"(?i)(képfeldolgozás|image processing|vision) (not supported|nem támogatott|not available)",
    r"(?i)nem (látom|tudom (leírni|értelmezni|olvasni)) (a )?kép(et|pet)",
    r"(?i)couldn't (process|read|analyze|see) (the |this )?(image|picture|photo)",
    r"(?i)ewn nem (tudom|tudom|tudtuk|tudtunk)",
    r"(?i)sajnos nem tud(om|ok|hatsz)",
]

# When specialist X can't handle something, route to GENERAL (the team coordinator).
# General knows everyone's capabilities, sees team development, and decides who picks it up.
ESCALATION_ROUTING = {
    "dev": "general",        # Dev can't → General decides routing
    "devops": "general",     # DevOps can't → General decides routing
    "research": "general",   # Research can't → General decides routing
    "news": "general",       # News can't → General decides routing
    "study": "general",      # Study can't → General decides routing
    "fitness": "general",    # Fitness can't → General decides routing
}

# Skill area detection from message keywords (for DevelopmentTracker)
SKILL_AREAS = {
    "code": ["kód", "code", "implement", "script", "api", "python", "web", "app", "build", "bug", "debug", "fejleszt", "program"],
    "infra": ["infra", "server", "docker", "deploy", "nginx", "dns", "ssl", "domain", "cloud", "ci/cd", "hosting"],
    "research": ["kutatás", "research", "keres", "search", "elemez", "analysis", "összehasonlít", "forrás", "adat"],
    "news": ["hír", "news", "aktual", "cikk", "tldr", "összefoglaló"],
    "law": ["jog", "law", "tanul", "vizsga", "jogi", "polgári", "büntető", "alkotmány"],
    "fitness": ["edzés", "fitness", "workout", "torna", "futás", "gyakorlat", "erőedzés", "hiit", "yoga", "sport"],
    "general": ["koordin", "szervez", "tervez", "project", "menedzs"],
}

def detect_skill_area(message: str) -> str:
    """Detect what skill area a message belongs to based on keywords."""
    msg_lower = message.lower()
    best_area = "general"
    best_count = 0
    for area, keywords in SKILL_AREAS.items():
        count = sum(1 for kw in keywords if kw in msg_lower)
        if count > best_count:
            best_count = count
            best_area = area
    return best_area

MAJOR_TASK_KEYWORDS = [
    'kód', 'code', 'implement', 'deploy', 'build', 'script', 'infra',
    'server', 'docker', 'api', 'webapp', 'app', 'fejleszt', 'program',
    'migráció', 'setup', 'konfiguráció'
]

def is_major_task(text: str) -> bool:
    """Check if a task is a major development/infra task (for #team milestone posts)."""
    text_lower = text.lower()
    return any(kw in text_lower for kw in MAJOR_TASK_KEYWORDS)


def detect_cant_do(response: str) -> bool:
    """Check if a response contains 'I can't do this' patterns."""
    import re
    for pattern in CANT_DO_PATTERNS:
        if re.search(pattern, response):
            return True
    return False


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def load_soul_md(agent: str) -> str:
    """Load SOUL.md personality for the agent."""
    soul_path = PROFILES_DIR / agent / "SOUL.md"
    if soul_path.exists():
        content = soul_path.read_text()
        return content[:2500].strip()
    return f"You are Hermes {agent.title()}, a helpful AI assistant."


def load_team_knowledge() -> str:
    """Load shared team knowledge base."""
    kb_path = Path.home() / ".hermes" / "discord-multi-agent" / "team-knowledge.md"
    if kb_path.exists():
        return kb_path.read_text().strip()[:1000]
    return ""


def extract_and_store_facts(agent: str, user_msg: str, ai_response: str, scope: str = "auto"):
    """Extract key facts from a specialist interaction and store to mem0.
    
    Args:
        agent: The agent name (dev, research, etc.)
        user_msg: Original user message
        ai_response: AI response text
        scope: "auto" (decide based on content), "shared", or "specialist"
    
    Facts are stored asynchronously — this function never raises exceptions.
    """
    try:
        from mem0_integration import shared_memory
        
        # Only extract from substantive interactions (skip short/generic responses)
        if len(ai_response) < 100 or ai_response.startswith("❌"):
            return
        
        # Auto-determine scope: if response contains broadly useful info, store as shared
        # Technical/environment details that only the specialist needs stay specialist
        if scope == "auto":
            # Keywords that indicate generally useful facts
            shared_keywords = ["krisztian", "prefer", "always", "never", "rule", "convention",
                              "timezone", "utc", "language", "format", "style", "home pc",
                              "routing", "channel", "bridge", "gateway", "architect"]
            content_lower = (user_msg + " " + ai_response).lower()
            if any(kw in content_lower for kw in shared_keywords):
                scope = "shared"
            else:
                scope = "specialist"
        
        # Create a concise fact summary (max 200 chars to avoid bloating mem0)
        fact = ai_response.replace("\n", " ").strip()[:200]
        if not fact or fact in ("", "⚠️ Empty response"):
            return
        
        # Store with appropriate scope
        success = shared_memory.add(
            content=f"{agent} learned: {fact}",
            agent=agent,
            scope=scope,
        )
        if success:
            print(f"    💾 [{agent}] Fact stored in {scope} scope")
    except Exception as e:
        # Never let mem0 failures break the bridge
        print(f"    ⚠️ [{agent}] mem0 fact extraction skipped: {e}")


async def send_discord_message(session, channel_id, content, token, return_msg_id=False):
    """Send message directly via Discord API. If return_msg_id=True, returns the message ID of the first chunk."""
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {"Authorization": f"Bot {token}", "Content-Type": "application/json", "User-Agent": "Hermes-Bridge/5.0 (Discord Bot)"}
    # Split long messages into chunks for Discord 2000 char limit
    chunks = []
    while content:
        if len(content) <= 2000:
            chunks.append(content)
            break
        split_at = content.rfind('\n', 0, 2000)
        if split_at == -1:
            split_at = 2000
        chunks.append(content[:split_at])
        content = content[split_at:].lstrip('\n')

    first_msg_id = None
    for i, chunk in enumerate(chunks):
        data = {"content": chunk}
        async with session.post(url, json=data, headers=headers) as resp:
            if resp.status not in (200, 201):
                body = await resp.text()
                print(f"    ❌ Discord send failed: {resp.status} {body[:200]}")
                return first_msg_id if return_msg_id else False
            if i == 0 and return_msg_id:
                try:
                    resp_data = await resp.json()
                    first_msg_id = resp_data.get("id")
                except:
                    pass
    return first_msg_id if return_msg_id else True


async def create_thread_from_message(session, channel_id, message_id, name, token):
    """Create a public thread from an existing message in Discord."""
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages/{message_id}/threads"
    headers = {"Authorization": f"Bot {token}", "Content-Type": "application/json", "User-Agent": "Hermes-Bridge/5.0 (Discord Bot)"}
    data = {"name": name, "type": 11}  # 11 = public thread
    async with session.post(url, json=data, headers=headers) as resp:
        if resp.status in (200, 201):
            thread_data = await resp.json()
            thread_id = thread_data.get("id")
            print(f"🧵 Thread created: {name} (ID: {thread_id})")
            return thread_data
        else:
            body = await resp.text()
            print(f"    ❌ Thread creation failed: {resp.status} {body[:200]}")
            return None


async def discover_active_threads(session, guild_id, token):
    """Discover active threads in the guild (especially under #team)."""
    url = f"https://discord.com/api/v10/guilds/{guild_id}/threads/active"
    headers = {"Authorization": f"Bot {token}", "User-Agent": "Hermes-Bridge/5.0 (Discord Bot)"}
    async with session.get(url, headers=headers) as resp:
        if resp.status == 200:
            data = await resp.json()
            return data.get("threads", [])
        return []


async def get_ai_response(agent: str, message: str, channel_context: str = "", image_urls: list = None) -> str:
    """Get response from OpenCode Go API with per-agent model. Supports vision (image URLs)."""
    start_time = time.time()
    api_key = os.environ.get("OPENCODE_GO_API_KEY", "") or os.environ.get("OPENCODE_ZEN_API_KEY", "")
    base_url = os.environ.get("OPENCODE_GO_BASE_URL", "https://opencode.ai/zen/go/v1")

    if not api_key:
        return "❌ Error: No API key configured"

    client = AsyncOpenAI(api_key=api_key, base_url=f"{base_url}/v1" if not base_url.endswith("/v1") else base_url)

    soul = load_soul_md(agent)
    dev_report = dev_tracker.get_capability_report()[:500] if dev_tracker.data.get("capabilities") else ""

    # === CONTEXT-AWARE PROMPT INJECTION (token diet) ===
    # Always: SOUL.md (identity + personality)
    # Conditional: team_knowledge (only for #team and delegation contexts)
    # Conditional: mem0 (only when relevant facts exist, limited to 500 chars)
    system_prompt = soul

    is_team_or_delegation = "team" in (channel_context or "").lower() or "delegation" in (channel_context or "").lower() or "escalation" in (channel_context or "").lower()
    is_human = "human" in (channel_context or "").lower()

    # Team knowledge: only inject for #team context, #human, delegation, or general agent
    if is_team_or_delegation or is_human or agent == "general":
        team_kb = load_team_knowledge()
        system_prompt += f"""

SHARED TEAM KNOWLEDGE:
{team_kb}
"""
        if dev_report and agent == "general":
            system_prompt += f"""
CURRENT TEAM CAPABILITIES (live data from development.json):
{dev_report}
"""

    # Inject mem0 shared + specialist memory context (limited to save tokens)
    try:
        from mem0_integration import shared_memory
        mem0_ctx = shared_memory.get_relevant_facts(message, agent)[:500]  # Hard limit
        if mem0_ctx:
            system_prompt += f"""

MEM0 MEMORY (shared + {agent} specialist):
{mem0_ctx}
"""
    except Exception as e:
        print(f"    ⚠️ Mem0 context injection failed for {agent}: {e}")

    system_prompt += """
IMPORTANT RULES:
- Respond in the same language as the user's message (Hungarian if Hungarian)
- You are on Discord. Use Discord formatting: **bold**, *italic*, `code`, ```code blocks```
- Keep responses concise (under 1500 chars). If longer, split into key points.
- If you need human approval, post in #human channel (1501617834952888455)
- For tasks longer than 5 minutes or involving risky operations, post a plan in #human first and wait for 👍
- When delegating in #team, always use <@BOT_ID> format to @mention the specialist

ESCALATION RULES (CRITICAL — NEVER just say "I can't"):
- If you cannot handle a request, NEVER just say "I can't" or "nem tudom" and stop.
  Instead: explain WHAT you can't do and WHY, then ESCALATE to the right specialist.
- Example: "Ez infra kérdés, nem code. @DevOps tud segíteni a Docker deploy-ban."
- If no specialist matches, post to #human for Krisztian.
- Available specialists: Dev (code/API), DevOps (infra/deploy), Research (deep analysis), News (current events), Study (law/education), Fitness (exercise/health), General (coordination).
- Bot-to-bot referral: mention the specialist with <@BOT_ID> in #team so they pick it up.

DEVELOPMENT AWARENESS (you see team growth over time):
- When you receive an escalation, check the development data embedded in the message (📊 skill scores).
- Use skill scores to decide WHO to delegate to — higher score = more experience in that area.
- If you see a specialist is developing a new skill (score increasing), note it: "Dev fejlődik infra területen (70/100)!"
- If all specialists have low scores in an area, that's a growth opportunity — delegate to the one most likely to learn.
- Every successful delegation you make is tracked. Your decisions shape the team's development.
- `!fejlodés` command shows the full capability report in any channel.
- Development data is stored in: ~/.hermes/discord-multi-agent/development.json
 """

    if channel_context:
        system_prompt += f"\nChannel context: {channel_context}"

    model = AGENT_MODELS.get(agent, "deepseek-v4-flash")

    try:
        # Build user message content — support vision (images)
        user_content = message
        if image_urls:
            # OpenAI vision API format: array of text + image_url parts
            content_parts = [{"type": "text", "text": message}]
            for img_url in image_urls[:4]:  # Max 4 images per message
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": img_url}
                })
            user_content = content_parts

        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            max_tokens=4096,
            temperature=0.7,
        )
        content = response.choices[0].message.content
        if not content or not content.strip():
            reasoning = getattr(response.choices[0].message, 'reasoning_content', None)
            if reasoning and reasoning.strip():
                content = reasoning

        # Log token usage
        try:
            usage = response.usage
            _token_logger.log(
                model=model,
                prompt_tokens=getattr(usage, 'prompt_tokens', 0) or 0,
                completion_tokens=getattr(usage, 'completion_tokens', 0) or 0,
                total_tokens=getattr(usage, 'total_tokens', 0) or 0,
                cached_tokens=getattr(getattr(usage, 'prompt_tokens_details', None), 'cached_tokens', 0) or 0,
                reasoning_tokens=getattr(getattr(usage, 'completion_tokens_details', None), 'reasoning_tokens', 0) or 0,
                agent_name=agent,
                channel_id=str(send_channel) if send_channel else "unknown",
                latency_ms=int((time.time() - start_time) * 1000),
            )
        except Exception as e:
            print(f"    ⚠️ Token log error: {e}")

        return content.strip() if content else "⚠️ Empty response"
    except Exception as e:
        print(f"    ❌ API error for {agent}: {e}")
        return f"❌ Error: {str(e)[:200]}"


async def gateway_presence(agent: str, token: str):
    """Maintain online presence via discord.py (stable Gateway with auto-reconnect)."""
    intents = discord.Intents.default()
    intents.guilds = True
    intents.message_content = False
    intents.guild_messages = False

    class PresenceBot(discord.Client):
        def __init__(self, **kwargs):
            super().__init__(intents=intents, **kwargs)

        async def on_ready(self):
            print(f"✅ [{agent}] Gateway connected as {self.user.name} (ID: {self.user.id})")

        async def on_disconnect(self):
            print(f"⚠️ [{agent}] Gateway disconnected, discord.py will auto-reconnect...")

        async def on_resumed(self):
            print(f"✅ [{agent}] Gateway reconnected (resumed)")

    try:
        bot = PresenceBot()
        activity = discord.Game(name=f"Hermes {agent.title()}")
        await bot.login(token)
        await bot.connect(reconnect=True)
    except asyncio.CancelledError:
        print(f"🛑 [{agent}] Gateway cancelled, exiting.")
    except discord.LoginFailure as e:
        print(f"❌ [{agent}] Gateway login failed: {e}")
    except Exception as e:
        print(f"❌ [{agent}] Gateway presence error: {e}")


async def run_bridge(agent: str, token: str, channels: list, config: dict):
    """Run one bridge connection monitoring multiple channels + threads under #team."""
    print(f"🚀 [{agent}] Starting (model: {AGENT_MODELS.get(agent, 'deepseek-v4-flash')})...")

    # Track processed message IDs per channel (set, not single ID)
    # On startup, mark all recent messages as processed to avoid replying to old messages
    processed_ids = {str(ch): set() for ch in channels}
    MAX_IDS = 200
    poll_count = 0  # For periodic thread discovery

    headers = {
        "Authorization": f"Bot {token}",
        "User-Agent": "Hermes-Bridge/5.0 (Discord Bot)",
    }

    bot_id = BOT_IDS.get(agent)
    team_channel = str(config["channels"].get("team", ""))
    human_channel = str(config["channels"].get("human", ""))
    general_channel = str(config["channels"].get("general", ""))
    home_channel = str(config["channels"].get(agent, ""))
    server_id = str(config.get("server_id", "1501144914333925376"))

    async with aiohttp.ClientSession() as session:
        # Verify bot identity
        async with session.get("https://discord.com/api/v10/users/@me", headers=headers) as resp:
            if resp.status == 200:
                bot_data = await resp.json()
                print(f"✅ [{agent}] REST API ready as {bot_data.get('username')} (ID: {bot_data.get('id')})")
            else:
                print(f"⚠️ [{agent}] Could not get bot ID: {resp.status}")

        # Pre-load recent message IDs to avoid replying to old messages on startup
        for channel_id in channels:
            url = f"https://discord.com/api/v10/channels/{channel_id}/messages?limit=10"
            async with session.get(url, headers={**headers, "Authorization": f"Bot {token}"}) as resp:
                if resp.status == 200:
                    msgs = await resp.json()
                    for m in msgs:
                        processed_ids[str(channel_id)].add(m.get("id", ""))
                    print(f"📖 [{agent}] Pre-loaded {len(msgs)} message IDs for channel {channel_id}")

        while True:
            try:
                # Periodic thread discovery: every 30 polls, discover active threads under ALL channels we monitor
                # This ensures specialists can see threads in #general, #team, and their own channels
                poll_count += 1
                if poll_count % 30 == 0 and team_channel:
                    try:
                        active_threads = await discover_active_threads(session, server_id, token)
                        # Track threads from any channel we monitor (not just #team)
                        monitored_channel_ids = set(str(ch) for ch in channels)
                        for thread in active_threads:
                            tid = str(thread.get("id", ""))
                            parent_id = str(thread.get("parent_id", ""))
                            # Track threads from any monitored channel OR threads we created via delegation
                            if parent_id in monitored_channel_ids or tid in TEAM_THREADS:
                                if tid not in processed_ids:
                                    processed_ids[tid] = set()
                                    # Pre-load recent messages to avoid responding to old ones
                                    url_pre = f"https://discord.com/api/v10/channels/{tid}/messages?limit=5"
                                    async with session.get(url_pre, headers={**headers, "Authorization": f"Bot {token}"}) as resp_pre:
                                        if resp_pre.status == 200:
                                            pre_msgs = await resp_pre.json()
                                            for pm in pre_msgs:
                                                processed_ids[tid].add(pm.get("id", ""))
                                            print(f"📖 [{agent}] Started monitoring thread {tid} (parent: {parent_id})")
                                if tid not in [str(ch) for ch in channels]:
                                    channels.append(tid)
                                    # Track in TEAM_THREADS if not already known
                                    if tid not in TEAM_THREADS:
                                        TEAM_THREADS[tid] = {"parent": parent_id, "delegated_to": [], "original_msg": "", "created_at": time.time()}
                    except Exception as e:
                        print(f"⚠️ [{agent}] Thread discovery failed: {e}")

                # Also add any globally known TEAM_THREADS that aren't in our channels yet
                for tid in list(TEAM_THREADS.keys()):
                    if tid not in [str(ch) for ch in channels]:
                        channels.append(tid)
                        if tid not in processed_ids:
                            processed_ids[tid] = set()

                for channel_id in channels:
                    url = f"https://discord.com/api/v10/channels/{channel_id}/messages?limit=10"
                    headers_with_auth = {**headers, "Authorization": f"Bot {token}"}
                    async with session.get(url, headers=headers_with_auth) as resp:
                        if resp.status != 200:
                            if resp.status == 429:
                                retry_after = int(resp.headers.get("Retry-After", "5"))
                                print(f"⏳ [{agent}] Rate limited, waiting {retry_after}s...")
                                await asyncio.sleep(retry_after)
                            elif resp.status == 403:
                                pass  # No access, skip
                            continue

                        messages = await resp.json()
                        ch_set = processed_ids[str(channel_id)]

                        for msg in reversed(messages):
                            msg_id = msg.get("id", "")
                            author_id = msg.get("author", {}).get("id", "")

                            # Skip already processed messages
                            if msg_id in ch_set:
                                continue

                            # Add to processed set immediately (prevent re-processing)
                            ch_set.add(msg_id)
                            # Trim set if too large
                            if len(ch_set) > MAX_IDS:
                                # Keep only the most recent IDs
                                ch_set.discard(min(ch_set))

                            content = msg.get("content", "").strip()
                            
                            # Extract image attachments from the message
                            attachments = msg.get("attachments", [])
                            image_urls = []
                            for att in attachments:
                                content_type = att.get("content_type", "")
                                url = att.get("url", att.get("proxy_url", ""))
                                if content_type.startswith("image/") or any(url.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp", ".gif"]):
                                    image_urls.append(url)
                            
                            # If message has images but no text, add a placeholder
                            if image_urls and not content:
                                content = "[képet küldött]"
                            
                            # Skip empty messages with no images
                            if not content and not image_urls:
                                continue

                            # Determine WHERE to send response (needed before vision escalation)
                            send_channel = channel_id  # Default: respond in same channel

                            # === VISION SHORT-CIRCUIT: If images but model doesn't support vision, route to General (Hermes has vision_analyze!) ===
                            if image_urls and AGENT_MODELS.get(agent, "") not in VISION_CAPABLE_MODELS and agent != "general":
                                model_name = AGENT_MODELS.get(agent, "unknown")
                                print(f"🖼️ [{agent}] Image received but {model_name} doesn't support vision → routing to General")

                                # Route to #team with @mention for General — General has vision tools (vision_analyze, OCR, browser)
                                general_bot_id = BOT_IDS.get("general", "")
                                esc_msg = (
                                    f"**🖼️ Kép eszkaláció: {agent.title()} ({model_name}) nem tud képet olvasni**\n"
                                    f"> Eredeti üzenet: {content[:200]}\n"
                                    f"> Terület: {skill_area}\n"
                                    f"> Kép URL: {image_urls[0]}\n\n"
                                    f"<@{general_bot_id}> Kérlek elemezd a képet! Használd a vision/OCR eszközeidet, "
                                    f"majd válaszolj {agent.title()} nevében a képről.\n\n"
                                    f"*Auto-eszkaláció: {agent.title()} modellje nem támogatja a vision-t.*"
                                )
                                # Post escalation in #team for General
                                await send_discord_message(session, team_channel, esc_msg, token)
                                # Post notice in original channel so user knows it's being handled
                                notice_msg = f"📸 Képet kaptam, de a modelljem ({model_name}) nem támogatja a képfeldolgozást. Továbbítottam a Generalnak elemzésre — hamarosan válaszol! 🔍"
                                await send_discord_message(session, send_channel, notice_msg, token)
                                dev_tracker.record_escalation(agent, "image_vision_not_supported", content[:200])
                                dev_tracker.record_task_failure(agent, skill_area)
                                print(f"🖼️ [{agent}] Image escalated to General via #team ✅")
                                continue

                            # Determine channel type (needed before bot-skip for General synthesis)
                            is_home = str(channel_id) == home_channel
                            is_general = str(channel_id) == general_channel
                            is_team = str(channel_id) == team_channel
                            is_human = str(channel_id) == human_channel
                            is_thread = str(channel_id) in TEAM_THREADS
                            # A thread under #team is treated like #team for routing
                            is_team_context = is_team or (is_thread and TEAM_THREADS.get(str(channel_id), {}).get("parent") == team_channel)

                            # Skip bot messages — EXCEPT general bot seeing specialist responses in #team or threads
                            is_bot_msg = msg.get("author", {}).get("bot", False)
                            is_specialist_in_team = (agent == "general" and is_team_context and author_id in ALL_BOT_IDS and author_id != BOT_IDS.get("general", ""))
                            if is_bot_msg and not is_specialist_in_team:
                                continue

                            # Skip messages from any Hermes bot — same exception for general synthesis
                            if author_id in ALL_BOT_IDS and not is_specialist_in_team:
                                continue


                            # Check if this bot is @mentioned
                            mentions = msg.get("mentions", [])
                            is_mentioned = any(m.get("id") == bot_id for m in mentions)

                            # === ROUTING LOGIC ===

                            # General bot: responds in #general (Krisztian's input) and #team/threads (delegating and synthesis)
                            # Other bots: respond only in home channel or when @mentioned in #team/threads
                            if agent == "general":
                                # General responds to: #general (Krisztian), #human (if mentioned), #team/threads (own messages + specialist responses for synthesis)
                                if is_general or is_home:
                                    pass  # Always respond in home/general
                                elif is_human and is_mentioned:
                                    pass  # Respond in #human if mentioned
                                elif is_team_context and is_mentioned:
                                    pass  # Respond in #team or thread if mentioned back
                                elif is_team_context and author_id in ALL_BOT_IDS and author_id != BOT_IDS.get("general", ""):
                                    # Synthesize specialist response back to #general
                                    specialist_names = [name for name, bid in BOT_IDS.items() if bid == author_id]
                                    specialist_name = specialist_names[0] if specialist_names else "specialist"
                                    
                                    # Try to get result from bus first (bus-based synthesis)
                                    # NOTE: Bus messages have original direction (general→specialist),
                                    # so we query from=general, to=specialist
                                    specialist_result = content  # fallback to Discord content
                                    bus_messages = []
                                    if BUS_AVAILABLE:
                                        try:
                                            bus_messages = _bus.get_completed(from_agent="general", to_agent=specialist_name, since=time.time() - 300, limit=5)
                                            if bus_messages:
                                                # Use the most recent bus result instead of Discord content
                                                specialist_result = bus_messages[0].result or bus_messages[0].content
                                                print(f"🚌 [general] Synthesizing from bus result (msg_id={bus_messages[0].id})")
                                                # Complete the corresponding bus task if not already done
                                                for bm in bus_messages:
                                                    if bm.status == "completed":
                                                        _bus.cleanup(max_age_hours=0.01)  # quick cleanup of old completed
                                        except Exception as e:
                                            print(f"⚠️ [general] Bus read failed, using Discord content: {e}")
                                    
                                    synthesis_prompt = f"""A team specialist ({specialist_name}) just responded about a task. Here's what they said:

---
{specialist_result[:1500]}
---

Summarize this result for Krisztian in #general. Be concise, highlight the key findings. Write in Hungarian. Keep under 800 chars. Format: "🔬 {specialist_name.title()} eredménye: [summary]"
"""
                                    
                                    synthesis = await get_ai_response("general", synthesis_prompt, "Synthesizing team results for Krisztian in #general.")
                                    
                                    if synthesis and synthesis.strip() and not synthesis.startswith("❌"):
                                        # Send synthesis to original context (thread/channel where user is talking)
                                        # not just #general — the bot responds WHERE the conversation is
                                        target_channel = general_channel  # default fallback
                                        # Check if there's a thread context from the delegation
                                        pending_tasks = task_tracker.find_pending_for(specialist_name) if specialist_name in BOT_IDS else []
                                        if pending_tasks and pending_tasks[0].get("original_thread"):
                                            target_channel = pending_tasks[0]["original_thread"]
                                        elif pending_tasks and pending_tasks[0].get("original_channel"):
                                            target_channel = pending_tasks[0]["original_channel"]

                                        sent = await send_discord_message(session, target_channel, synthesis, token)
                                        if sent:
                                            print(f"📤 [general] Synthesis sent to {target_channel} ✅ ({len(synthesis)} chars)")
                                        # Milestone on #team only for major tasks
                                        task_data = pending_tasks[0] if pending_tasks else {}
                                        task_content = task_data.get("original_msg", "")
                                        if is_major_task(task_content):
                                            await send_discord_message(session, team_channel, f"✅ **{specialist_name.title()}**: {skill_area.title()} feladat befejeződött", token)
                                        # Mark recent completed tasks as synthesized
                                        for t in task_tracker.find_recent_completed():
                                            task_tracker.mark_synthesized(t["id"])
                                        # Record resolution in development tracker
                                        if specialist_name and specialist_name in BOT_IDS:
                                            skill_area = "general"
                                            pending = task_tracker.find_pending_for(specialist_name)
                                            if pending:
                                                skill_area = pending[0].get("skill_area") or detect_skill_area(pending[0].get("original_msg", ""))
                                                task_tracker.start_task(pending[0]["id"])
                                                task_tracker.complete_task(pending[0]["id"], synthesis[:200])
                                            dev_tracker.record_resolution(specialist_name, specialist_name, skill_area)

                                        # Store delegation result to mem0 (shared + specialist)
                                        try:
                                            from mem0_integration import shared_memory
                                            task_desc = pending_tasks[0].get("original_msg", specialist_result[:100]) if pending_tasks else specialist_result[:100]
                                            shared_memory.store_delegation_result(
                                                from_agent="general",
                                                to_agent=specialist_name,
                                                task=task_desc,
                                                result=synthesis[:200],
                                            )
                                        except Exception:
                                            pass  # Never break the bridge
                                    continue
                                else:
                                    continue
                            else:
                                # Specialists: delegate response to gateway for home channels.
                                # Gateway handles home channel conversations with auto_thread + memory.
                                # Bridge only handles delegation (#team, @mentions, #general coordination).
                                if is_home:
                                    # Skip home channel responses — gateway already handles these
                                    # with auto_thread, session memory, and proper thread isolation.
                                    # This prevents duplicate responses (gateway thread + bridge channel).
                                    print(f"⏭️ [{agent}] Skipping home channel response — gateway handles {channel_name}")
                                    continue
                                elif is_team_context and is_mentioned:
                                    pass  # Respond in #team or thread if delegated (@mentioned)
                                elif is_human and is_mentioned:
                                    pass  # Respond in #human if mentioned
                                else:
                                    continue

                            # Build channel context
                            channel_name = "home" if is_home else ("team" if is_team else ("thread" if is_thread else ("general" if is_general else ("human" if is_human else str(channel_id)))))

                            # === COMMANDS: Special commands that skip AI processing ===
                            content_lower = content.strip().lower()
                            if content_lower in ["!fejlodés", "!fejlodes", "!fejlesztés", "!stats", "!képességek", "!kepessegek"]:
                                # Development report command — show team capability scores + auto-update KB
                                dev_tracker.update_team_knowledge()  # Always update KB on explicit request
                                report = dev_tracker.get_capability_report()
                                if report == "📊 **Képesség-pontszámok:**":
                                    report = "📊 Még nincsenek képesség-adatok. A csapat még nem végzett elég feladatot a pontszámításhez."
                                await send_discord_message(session, channel_id, report, token)
                                print(f"📊 [{agent}] Development report sent to #{channel_name}")
                                continue
                            print(f"📩 [{agent}] ({channel_name}) {msg['author']['username']}: {content[:80]}...")

                            # Initialize skill_area for tracking (overridden by detect_skill_area when applicable)
                            skill_area = detect_skill_area(content)

                            # Build mention context for specialists
                            mention_context = ""
                            if is_team_context and is_mentioned and not is_home:
                                if is_thread:
                                    mention_context = "You were @mentioned in a #team thread — this is a delegated task from the team coordinator. The delegation message includes full context. Follow the instructions precisely. Respond IN THIS THREAD with your detailed findings."
                                else:
                                    mention_context = "You were @mentioned in #team — this is a delegated task from the team coordinator. The delegation message includes full context (original request + General's analysis). Follow the instructions precisely. Respond in #team with your detailed findings."
                            elif is_human and is_mentioned:
                                mention_context = "You were @mentioned in #human — Krisztian needs your input."

                            response = await get_ai_response(agent, content, mention_context, image_urls=image_urls)

                            # Extract and store facts from specialist response to mem0
                            if response and response.strip() and not response.startswith("❌") and agent != "general":
                                extract_and_store_facts(agent, content, response)

# If the model couldn't handle images after responding (fallback detection), escalate to General via #team
                            if image_urls and detect_cant_do(response) and agent != "general":
                                print(f"🖼️ [{agent}] Model said 'can't do' with image → escalating to General via #team")
                                general_bot_id = BOT_IDS.get("general", "")
                                esc_msg = (
                                    f"**🖼️ Kép eszkaláció (fallback): {agent.title()} nem tudta olvasni a képet**\n"
                                    f"> Eredeti üzenet: {content[:200]}\n"
                                    f"> {agent.title()} válasza: *{response[:150]}...*\n"
                                    f"> Terület: {skill_area}\n"
                                    f"> Kép URL: {image_urls[0]}\n\n"
                                    f"<@{general_bot_id}> Kérlek elemezd a képet és válaszolj {agent.title()} nevében!\n\n"
                                    f"*Fallback eszkaláció: {agent.title()} modellje nem tudta értelmezni a képet.*"
                                )
                                await send_discord_message(session, team_channel, esc_msg, token)
                                dev_tracker.record_escalation(agent, "image_vision_not_supported_fallback", content[:200])

                            # Determine WHERE to send the response
                            # (Already set to channel_id above — vision escalation needs it early)

                            if agent == "general" and is_general:
                                # General always responds in #general with a summary
                                # Use return_msg_id=True so we can create a thread from General's response
                                sent_general_msg_id = await send_discord_message(session, channel_id, response, token, return_msg_id=True)
                                sent_general = bool(sent_general_msg_id)
                                if sent_general:
                                    print(f"📤 [{agent}] Response sent to #general ✅ ({len(response)} chars, msg_id={sent_general_msg_id})")

                                # ALWAYS delegate — via Message Bus (quiet) + brief Discord indicator
                                delegation_lines = [line for line in response.split('\n') if '<@' in line and '>' in line]
                                delegates = []

                                if delegation_lines:
                                    # Model included @mentions — use them directly
                                    for line in delegation_lines:
                                        for name, bid in BOT_IDS.items():
                                            if name != "general" and bid in line:
                                                delegates.append((f"<@{bid}>", name.title(), ""))
                                else:
                                    # No @mentions in response — auto-delegate based on keywords
                                    user_lower = content.lower()

                                    if any(kw in user_lower for kw in ['kód', 'code', 'implement', 'bug', 'debug', 'script', 'deploy', 'api', 'python', 'web', 'app', 'build', 'fejleszt', 'program', 'szoftver']):
                                        delegates.append(("<@1501140611506372760>", "Dev", "implementáció és kódolás"))
                                    if any(kw in user_lower for kw in ['infra', 'server', 'docker', 'ci/cd', 'nginx', 'dns', 'ssl', 'domain', 'hosting', 'deploy', 'cloud']):
                                        delegates.append(("<@1501141067607707829>", "DevOps", "infrastruktúra és deployment"))
                                    if any(kw in user_lower for kw in ['hír', 'news', 'aktual', 'cikk', 'tldr', 'összefoglaló', 'hírek', 'információ', 'keresés', 'search', 'kutatás', 'research', 'elemez', 'analysis']):
                                        delegates.append(("<@1501141173530792027>", "News", "információ és kutatás"))
                                    if any(kw in user_lower for kw in ['jog', 'law', 'tanul', 'vizsga', 'jogi', 'polgári', 'büntető', 'tanuld', 'egytem', 'felkészülés']):
                                        delegates.append(("<@1501611238747013180>", "Study", "tanulás és jogi elemzés"))
                                    if any(kw in user_lower for kw in ['edzés', 'edző', 'fitness', 'fitnesz', 'workout', 'torna', 'futás', 'futni', 'gyakorlat', 'erőedzés', 'hiit', 'yoga', 'jóga', 'kocogás', 'súly', 'izom', 'test', 'sport', 'mozgás', 'stretching', 'bemelegítés', 'lezárás', 'pulzus', 'bdnf', 'kardió', 'két sé']):
                                        delegates.append(("<@1502331755263426711>", "Fitness", "edzés és fitnesz tanácsadás"))
                                    if any(kw in user_lower for kw in ['keres', 'search', 'find', 'talál', 'vizsgál', 'research', 'elemez', 'review', 'összehasonlít', 'szállás', 'hotel', 'utazás', 'ár', 'árak']):
                                        delegates.append(("<@1501139324861681736>", "Research", "kutatás és részletes elemzés"))

                                    # Default: at least Research if nothing matched
                                    if not delegates:
                                        delegates.append(("<@1501139324861681736>", "Research", "általános kutatás"))

                                # Build delegation context
                                orig_snippet = content[:300] + ("..." if len(content) > 300 else "")
                                general_analysis = response[:500] + ("..." if len(response) > 500 else "")
                                delegate_mentions = " ".join([d[0] for d in delegates])
                                delegate_tasks = "\n".join([f"• {d[0]} ({d[1]}): {d[2]}" for d in delegates])
                                delegate_names = ", ".join([d[1] for d in delegates])

                                # === BUS-BASED DELEGATION (quiet) ===
                                # Full delegation context goes through the message bus, not Discord
                                bus_delegation_content = (
                                    f"📋 Feladat Krisztiantól:\n> {orig_snippet}\n\n"
                                    f"🧠 General elemzése:\n{general_analysis}\n\n"
                                    f"Szakértők:\n{delegate_tasks}\n\n"
                                    f"Kérlek vizsgáld meg és válaszolj részletesen!"
                                )

                                # Detect if this is a "major task" for #team milestone post
                                is_major_flag = is_major_task(content)

                                for delegate in delegates:
                                    delegate_mention_str, delegate_name, delegate_task_desc = delegate
                                    # Find the agent name for this delegate
                                    delegate_agent = "research"  # default
                                    for name, bid in BOT_IDS.items():
                                        if bid != BOT_IDS["general"] and bid == delegate_mention_str.strip("<>@"):
                                            delegate_agent = name
                                            break

                                    if BUS_AVAILABLE:
                                        # Inject mem0 context into delegation content
                                        delegation_with_context = bus_delegation_content
                                        try:
                                            from mem0_integration import shared_memory
                                            mem0_ctx = shared_memory.get_relevant_facts(content, delegate_agent)
                                            if mem0_ctx:
                                                delegation_with_context += f"\n\n--- Team Memory (shared + {delegate_agent}) ---\n{mem0_ctx}\n--- End Memory ---"
                                        except Exception:
                                            pass  # Never break the bridge
                                        
                                        # Send full delegation through the bus (quiet, no Discord noise)
                                        bus_msg_id = _bus.send(
                                            from_agent="general",
                                            to_agent=delegate_agent,
                                            type="delegation",
                                            content=delegation_with_context,
                                            parent_msg_id=msg.get("id", ""),
                                            metadata={
                                                "skill_area": skill_area,
                                                "delegate_name": delegate_name,
                                                "original_user_msg": content[:500],
                                                "general_analysis": general_analysis[:500],
                                                "original_channel": str(channel_id),
                                                "original_thread": str(orig_context_id) if 'orig_context_id' in dir() else str(channel_id),
                                            }
                                        )
                                        print(f"🚌 [{agent}] Bus delegation → {delegate_agent} (msg_id={bus_msg_id})")
                                    else:
                                        print(f"⚠️ [{agent}] Bus unavailable, delegation to {delegate_agent} goes through Discord only")

                                # #team only gets MILESTONE posts for major tasks (not every delegation)
                                if is_major_flag:
                                    milestone_msg = f"🚀 **{delegate_names}**: {skill_area.title()} feladat elkezdve"
                                    await send_discord_message(session, team_channel, milestone_msg, token)
                                # For minor tasks: NO #team post — bus handles it silently

# Send @mention delegation — IN A THREAD, not in the main channel
                                # If we're already in a thread: delegate there
                                # If we're in a main channel (#general): create thread from General's response, delegate there
                                if is_thread or (str(channel_id) in TEAM_THREADS):
                                    # Already in a thread — delegate directly here
                                    orig_context_id = channel_id
                                    delegation_msg = f"**📋 Feladat:**\n> {orig_snippet}\n\n🧠 **General elemzése:** {general_analysis}\n\n{delegate_mentions} Kérlek vizsgáljátok meg és válaszoljatok itt!"
                                    sent_delegation = await send_discord_message(session, orig_context_id, delegation_msg, token)
                                    if sent_delegation:
                                        print(f"📤 [{agent}] Delegation sent to thread {orig_context_id} ✅ ({len(delegation_msg)} chars)")
                                else:
                                    # In a main channel (#general) — create thread from General's response, then delegate IN that thread
                                    # This keeps the main channel clean — delegation only appears in the thread
                                    # We already have General's message ID from send_discord_message(return_msg_id=True)
                                    gen_msg_id = sent_general_msg_id
                                    
                                    if gen_msg_id:
                                        thread_name = f"📋 {delegate_names}: {orig_snippet[:50]}"
                                        thread_data = await create_thread_from_message(session, general_channel, gen_msg_id, thread_name, token)
                                        if thread_data:
                                            orig_context_id = thread_data.get("id")
                                            # Register the new thread so all agents discover it
                                            TEAM_THREADS[str(orig_context_id)] = {
                                                "parent": general_channel,
                                                "delegated_to": [d[1] for d in delegates],
                                                "original_msg": content[:300],
                                                "created_at": time.time()
                                            }
                                            # Also add to channels list so this agent monitors it
                                            if orig_context_id not in [str(ch) for ch in channels]:
                                                channels.append(orig_context_id)
                                            if str(orig_context_id) not in processed_ids:
                                                processed_ids[str(orig_context_id)] = set()
                                            delegation_msg = f"**📋 Feladat:**\n> {orig_snippet}\n\n🧠 **General elemzése:** {general_analysis}\n\n{delegate_mentions} Kérlek vizsgáljátok meg és válaszoljatok itt!"
                                            sent_delegation = await send_discord_message(session, orig_context_id, delegation_msg, token)
                                            if sent_delegation:
                                                print(f"📤 [{agent}] Delegation sent to new thread {orig_context_id} ✅ ({len(delegation_msg)} chars)")
                                        else:
                                            # Thread creation failed — fallback: delegate in main channel (not ideal but functional)
                                            orig_context_id = channel_id
                                            print(f"⚠️ [{agent}] Thread creation failed — delegating in main channel (fallback)")
                                            delegation_msg = f"**📋 Feladat:**\n> {orig_snippet}\n\n🧠 **General elemzése:** {general_analysis}\n\n{delegate_mentions} Kérlek vizsgáljátok meg!"
                                            await send_discord_message(session, orig_context_id, delegation_msg, token)
                                    else:
                                        # Couldn't find General's message — fallback to main channel
                                        orig_context_id = channel_id
                                        print(f"⚠️ [{agent}] Couldn't find General's message — delegating in main channel")
                                        delegation_msg = f"**📋 Feladat:**\n> {orig_snippet}\n\n🧠 **General elemzése:** {general_analysis}\n\n{delegate_mentions} Kérlek vizsgáljátok meg!"
                                        await send_discord_message(session, orig_context_id, delegation_msg, token)

                                # Create tasks in TaskTracker for each delegate
                                for delegate in delegates:
                                    delegate_mention, delegate_name, _ = delegate
                                    delegate_agent = "research"  # default
                                    for name, bid in BOT_IDS.items():
                                        if bid != BOT_IDS["general"] and bid == delegate_mention.strip("<>@"):
                                            delegate_agent = name
                                            break
                                    task = task_tracker.create_task(content, delegate_agent, "general")
                                    task["original_thread"] = str(orig_context_id)
                                    task["original_channel"] = str(channel_id)
                                    task_tracker._save()
                                    print(f"📋 [{agent}] Created task {task['id']} → {delegate_agent} (context: {orig_context_id})")
                                # Skip the default send below
                                continue

                            # Send response
                            sent = await send_discord_message(session, send_channel, response, token)
                            if sent:
                                print(f"📤 [{agent}] Response sent ✅ ({len(response)} chars)")
                                # Track successful task completion (skill development) — ALL agents including General
                                if not detect_cant_do(response):
                                    dev_tracker.record_task_success(agent, skill_area)
                                    # Auto-update team-knowledge.md every 10 successful tasks (don't spam)
                                    total_successes = sum(
                                        s["successes"] 
                                        for skills in dev_tracker.data["capabilities"].values() 
                                        for s in skills.values()
                                    )
                                    if total_successes % 10 == 0:
                                        new_count = dev_tracker.update_team_knowledge()
                                        if new_count:
                                            print(f"📚 [{agent}] Auto-updated team-knowledge.md with {new_count} new capabilities")
                            else:
                                print(f"📤 [{agent}] Failed to send ❌")

                            # === BUS: Specialist sends result to General (quiet, not Discord noise) ===
                            if agent != "general" and BUS_AVAILABLE and not detect_cant_do(response):
                                # Check if there's a pending delegation from General in the bus
                                pending_msgs = _bus.receive(agent)
                                if pending_msgs:
                                    # Complete the bus task with the specialist's response
                                    for pm in pending_msgs:
                                        if pm.type == "delegation" and pm.from_agent == "general":
                                            _bus.complete(pm.id, result=response[:5000])
                                            print(f"🚌 [{agent}] Bus result sent → General (msg_id={pm.id})")
                                            # Milestone on #team only for major tasks
                                            task_content = pm.metadata.get("original_user_msg", "") if pm.metadata else ""
                                            if is_major_task(task_content):
                                                skill_area = pm.metadata.get("skill_area", "general") if pm.metadata else "general"
                                                elapsed = pm.age_seconds
                                                await send_discord_message(
                                                    session, team_channel,
                                                    f"✅ **{agent.title()} válaszolt** ({elapsed:.0f}s) — {skill_area.title()}",
                                                    token
                                                )

                            # === AUTO-ESCALATION: If specialist says "I can't", escalate to General ===
                            if agent != "general" and detect_cant_do(response):
                                # Always escalate to General — the team coordinator who knows everyone's capabilities
                                general_bot_id = BOT_IDS.get("general", "")
                                if general_bot_id:
                                    orig_snippet = content[:200] + ("..." if len(content) > 200 else "")
                                    # Get capability context for General to make informed decision
                                    best_agent = dev_tracker.get_best_agent_for(skill_area)
                                    capability_hint = f"\n📊 *Fejlesztési adat: {skill_area} területen {best_agent.title()} a legjobb ({dev_tracker.data['capabilities'].get(best_agent, {}).get(skill_area, {}).get('score', '?')}/100)*" if best_agent else ""

                                    # === BUS: Send escalation through the bus (quiet) ===
                                    if BUS_AVAILABLE:
                                        esc_bus_id = _bus.send(
                                            from_agent=agent,
                                            to_agent="general",
                                            type="escalation",
                                            content=f"🔄 Eszkaláció: {agent.title()} nem tudta kezelni\n\nEredeti kérés: {orig_snippet}\n{agent.title()} válasza: {response[:300]}\nTerület: {skill_area}{capability_hint}",
                                            metadata={
                                                "skill_area": skill_area,
                                                "original_msg": content[:500],
                                                "agent_response": response[:500],
                                                "best_agent": best_agent or "",
                                            }
                                        )
                                        print(f"🚌 [{agent}] Bus escalation → General (msg_id={esc_bus_id})")

                                    # Brief Discord indicator on #team (NOT full escalation text)
                                    esc_indicator = f"🔄 **{agent.title()} → General**: eszkaláció ({skill_area})"
                                    esc_msg_id = await send_discord_message(session, team_channel, esc_indicator, token, return_msg_id=True)

                                    # Still create a thread for the escalation (backward compat)
                                    esc_thread_created = False
                                    if esc_msg_id:
                                        esc_thread_name = f"🔄 Eszkaláció: {agent.title()} → General ({skill_area})"
                                        esc_thread_data = await create_thread_from_message(session, team_channel, esc_msg_id, esc_thread_name, token)
                                        if esc_thread_data:
                                            esc_thread_id = esc_thread_data.get("id")
                                            TEAM_THREADS[esc_thread_id] = {
                                                "parent": team_channel,
                                                "delegated_to": ["general"],
                                                "original_msg": content[:300],
                                                "created_at": time.time()
                                            }
                                            # Full escalation detail goes in the THREAD (not #team main)
                                            escalation_msg = (
                                                f"<@{general_bot_id}>\n\n"
                                                f"**🔄 Eszkaláció: {agent.title()} nem tudta kezelni**\n"
                                                f"> Eredeti kérés: {orig_snippet}\n"
                                                f"> {agent.title()} válasza: *{response[:150]}...*\n"
                                                f"> Terület: {skill_area}{capability_hint}\n\n"
                                                f"Kérlek vizsgáld meg — döntsd el ki tudja ezt csinálni és delegáld a megfelelő szakértőnek!"
                                            )
                                            esc_sent = await send_discord_message(session, esc_thread_id, escalation_msg, token)
                                            if esc_sent:
                                                print(f"🔄 [{agent}] Auto-escalated to General in thread {esc_thread_id} ✅")
                                                esc_thread_created = True

                                    if not esc_thread_created:
                                        # Fallback: brief indicator already sent to #team, escalation in bus
                                        print(f"🔄 [{agent}] Thread creation failed, escalation in bus only")

                                    # Track tasks and development
                                    task = task_tracker.create_task(content, "general", "general")
                                    task["skill_area"] = skill_area
                                    task["escalated_from"] = agent
                                    task_tracker._save()
                                    dev_tracker.record_escalation(agent, response[:200], content[:200])
                                    dev_tracker.record_task_failure(agent, skill_area)

                                    # Store escalation fact to mem0 (shared scope — all agents should know)
                                    extract_and_store_facts(agent, content, f"Escalated: {response[:150]}", scope="shared")

                            # Process only one new message per cycle per channel
                            break

                await asyncio.sleep(3)  # Poll interval

            except Exception as e:
                print(f"❌ [{agent}] Error: {e}")
                await asyncio.sleep(5)


async def main():
    load_env()
    config = load_config()

    # Initialize message bus (clean up old messages)
    if BUS_AVAILABLE:
        cleaned = _bus.cleanup(max_age_hours=24)
        print(f"🧹 Bus cleanup: removed {cleaned} old messages")
        stats = _bus.get_stats()
        print(f"🚌 Bus status: {stats['total']} messages, {stats['pending']} pending, {stats['in_progress']} in_progress")

    agents = ["general", "research", "dev", "devops", "news", "study", "fitness"]

    tasks = []
    for agent in agents:
        token = config["tokens"].get(agent)
        home_channel = str(config["channels"].get(agent, ""))
        team_channel = str(config["channels"].get("team", ""))
        human_channel = str(config["channels"].get("human", ""))

        if agent == "general":
            # General monitors: #general (Krisztian input) + #team + #human + home
            general_channel = str(config["channels"].get("general", ""))
            channels = list(set([ch for ch in [home_channel, general_channel, team_channel, human_channel] if ch]))
        else:
            # Specialists monitor: home channel + #team + #human
            channels = list(set([ch for ch in [home_channel, team_channel, human_channel] if ch]))

        if token and home_channel:
            tasks.append(run_bridge(agent, token, channels, config))
            tasks.append(gateway_presence(agent, token))

    print(f"🎉 Starting {len(agents)} Discord bridges (REST + Gateway + Message Bus)...")
    print(f"📋 Models: {json.dumps(AGENT_MODELS, indent=2)}")
    print(f"📋 Channels: home + #team + #human (general also: #general)")
    print(f"📋 Bus: {'✅ available' if BUS_AVAILABLE else '❌ unavailable (Discord-only mode)'}")
    print()
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())