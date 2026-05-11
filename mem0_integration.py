#!/usr/bin/env python3
"""Mem0 Shared Memory Integration for Bridge_v3.

Provides shared + specialist memory access for Discord bots.
Uses the same Qdrant collection as the Hermes gateway mem0 plugin,
with agent_id-based scope filtering (shared vs specialist).

Architecture:
- Shared scope (agent_id="shared"): Organizational facts visible to all agents
- Specialist scope (agent_id="dev"/"research"/...): Agent-specific knowledge
- Hierarchical read: shared first, then own specialist memories
- Write: defaults to own specialist scope, can write to shared via scope parameter

Usage:
    mem = SharedMemory()
    
    # Read: shared + specialist context for a query
    context = mem.search("Docker deployment", agent="dev")
    # Returns shared org facts + dev specialist facts, ranked by relevance
    
    # Write: store a new fact
    mem.add("uv pip install is the package manager", agent="dev")
    mem.add("Krisztian prefers concise responses", agent="shared")
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Add hermes-agent to path for mem0 import
HERMES_AGENT_DIR = Path.home() / ".hermes" / "hermes-agent"
if str(HERMES_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(HERMES_AGENT_DIR))

logger = logging.getLogger("mem0_integration")

# Cache the Memory instance (expensive to create)
_memory_instance = None
_config_cache = None


def _get_config_path(agent: str) -> Path:
    """Get the mem0 config path for a given agent."""
    # Profile-specific config
    profile_config = Path.home() / ".hermes" / "profiles" / agent / "mem0.json"
    if profile_config.exists():
        return profile_config
    # Fallback to global config
    global_config = Path.home() / ".hermes" / "mem0.json"
    if global_config.exists():
        return global_config
    raise FileNotFoundError(f"No mem0 config found for agent '{agent}'")


def _get_memory_for_agent(agent: str):
    """Get or create a mem0 Memory instance for a given agent.
    
    Uses the profile-specific mem0.json config which contains the agent_id.
    Each agent gets its own Memory instance (different agent_id).
    """
    global _memory_instance, _config_cache
    
    try:
        config_path = _get_config_path(agent)
        config = json.loads(config_path.read_text())
        
        # Ensure agent_id matches the requested agent
        config["agent_id"] = agent
        
        # Create a new instance per agent (different agent_id)
        from mem0 import Memory
        m = Memory.from_config(config)
        return m
    except FileNotFoundError as e:
        logger.warning(f"Mem0 config not found for agent '{agent}': {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to create mem0 instance for agent '{agent}': {e}")
        return None


class SharedMemory:
    """Shared memory interface for bridge_v3 and other components.
    
    Provides hierarchical memory access:
    - search(agent, query): shared + specialist memories, ranked by relevance
    - add(agent, content, scope): write to shared or specialist scope
    - get_context(agent, query): formatted context string for AI prompts
    """
    
    def __init__(self):
        self._instances = {}  # Cache per-agent Memory instances
    
    def _get_memory(self, agent: str):
        """Get cached Memory instance for an agent."""
        if agent not in self._instances:
            self._instances[agent] = _get_memory_for_agent(agent)
        return self._instances[agent]
    
    def search(
        self,
        query: str,
        agent: Optional[str] = None,
        scope: str = "all",
        top_k: int = 5,
    ) -> List[Dict[str, str]]:
        """Search shared + specialist memories.
        
        Args:
            query: Search query
            agent: Agent ID (e.g., "dev", "research"). If None, only shared scope.
            scope: "shared" (org facts only), "specialist" (own scope only), 
                   "all" (shared + own scope, default)
            top_k: Max results per scope
        
        Returns:
            List of dicts with keys: memory, score, agent_id, scope
        """
        results = []
        seen = set()
        
        # 1. Always search shared scope (unless explicitly excluded)
        if scope in ("shared", "all"):
            try:
                m = self._get_memory("shared")
                if m:
                    shared = m.search(
                        query=query,
                        filters={"user_id": "krisztian", "agent_id": "shared"},
                        top_k=top_k,
                    )
                    for r in shared.get("results", shared) if isinstance(shared, dict) else shared:
                        mem = r.get("memory", "")
                        if mem and mem not in seen:
                            seen.add(mem)
                            results.append({
                                "memory": mem,
                                "score": r.get("score", 0),
                                "agent_id": "shared",
                                "scope": "shared",
                            })
            except Exception as e:
                logger.debug(f"Shared memory search failed: {e}")
        
        # 2. Search specialist scope (if agent specified and scope includes it)
        if agent and scope in ("specialist", "all"):
            try:
                m = self._get_memory(agent)
                if m:
                    own = m.search(
                        query=query,
                        filters={"user_id": "krisztian", "agent_id": agent},
                        top_k=top_k,
                    )
                    for r in own.get("results", own) if isinstance(own, dict) else own:
                        mem = r.get("memory", "")
                        if mem and mem not in seen:
                            seen.add(mem)
                            results.append({
                                "memory": mem,
                                "score": r.get("score", 0),
                                "agent_id": agent,
                                "scope": "specialist",
                            })
            except Exception as e:
                logger.debug(f"Specialist memory search failed for {agent}: {e}")
        
        # Sort by score descending
        results.sort(key=lambda x: x.get("score", 0), reverse=True)
        return results[:top_k * 2]  # Allow up to 2x top_k for merged results
    
    def add(
        self,
        content: str,
        agent: str = "shared",
        scope: str = "shared",
        metadata: Optional[Dict] = None,
    ) -> bool:
        """Write a fact to shared or specialist memory.
        
        Args:
            content: The fact to store
            agent: Agent ID for specialist scope (default: "shared")
            scope: "shared" (visible to all) or "specialist" (own scope only)
            metadata: Optional metadata dict
        
        Returns:
            True if successful, False otherwise
        """
        write_agent = "shared" if scope == "shared" else agent
        try:
            m = self._get_memory(write_agent)
            if m:
                m.add(
                    [{"role": "user", "content": content}],
                    user_id="krisztian",
                    agent_id=write_agent,
                    infer=False,
                    metadata=metadata or {},
                )
                logger.info(f"Stored fact in {scope} scope (agent_id={write_agent}): {content[:60]}...")
                return True
        except Exception as e:
            logger.error(f"Failed to store fact in {scope} scope: {e}")
        return False
    
    def get_context(
        self,
        query: str,
        agent: Optional[str] = None,
        scope: str = "all",
        top_k: int = 5,
    ) -> str:
        """Get formatted context string for AI system prompts.
        
        Returns a formatted string with relevant memories, suitable for
        injecting into bridge_v3's system prompt.
        """
        results = self.search(query=query, agent=agent, scope=scope, top_k=top_k)
        if not results:
            return ""
        
        lines = []
        # Group by scope for clarity
        shared_facts = [r for r in results if r["scope"] == "shared"]
        specialist_facts = [r for r in results if r["scope"] == "specialist"]
        
        if shared_facts:
            lines.append(" organizational memory (shared across all agents):")
            for r in shared_facts:
                lines.append(f" - {r['memory']}")
        
        if specialist_facts and agent:
            lines.append(f" {agent} specialist memory:")
            for r in specialist_facts:
                lines.append(f" - {r['memory']}")
        
        return "\n".join(lines) if lines else ""
    
    def get_relevant_facts(self, message: str, agent: str) -> str:
        """Convenience method for bridge_v3: get relevant facts for a message.
        
        This is the main entry point for the bridge to inject mem0 context
        into AI system prompts. Searches both shared and specialist memories.
        """
        return self.get_context(query=message, agent=agent, scope="all", top_k=5)
    
    def store_delegation_result(
        self,
        from_agent: str,
        to_agent: str,
        task: str,
        result: str,
    ) -> bool:
        """Store a delegation result as a shared or specialist fact.
        
        Delegation results are stored in the specialist's scope, with
        a brief shared summary if the result is generally useful.
        """
        # Store specialist fact
        specialist_fact = f"Delegation from {from_agent}: {task[:80]} → {result[:80]}"
        ok1 = self.add(specialist_fact, agent=to_agent, scope="specialist")
        
        # Store brief shared summary for generally useful results
        shared_fact = f"{to_agent} completed: {task[:60]} → {result[:60]}"
        ok2 = self.add(shared_fact, agent="shared", scope="shared")
        
        return ok1 or ok2


# Singleton instance for easy import
shared_memory = SharedMemory()