#!/usr/bin/env python3
"""
Hermes Memory MCP Server
========================

MCP (Model Context Protocol) server for Hermes Memory system.
Communicates via stdio JSON-RPC as expected by the Hermes gateway.

Register in ~/.hermes/config.yaml:
    mcp_servers:
      hermes-memory:
        command: /home/artofphotogrphyy/.hermes/.venv/bin/python3
        args:
        - /home/artofphotogrphyy/.hermes/memory/mcp_server.py
        connect_timeout: 5
        timeout: 30
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

# Ensure memory module is importable
HERMES_HOME = Path.home() / ".hermes"
if str(HERMES_HOME) not in sys.path:
    sys.path.insert(0, str(HERMES_HOME))

from mcp.server import Server, NotificationOptions
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from memory import get_memory

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("hermes-memory-mcp")

# ─── Server Setup ──────────────────────────────────────────────────

server = Server("hermes-memory")

# ─── Tool Schemas ──────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="hermes_remember",
            description=(
                "Store a durable memory in Hermes Memory (Mnemosyne-backed with sqlite-vec + FTS5). "
                "Use for ANY fact, preference, identity, insight, or context that should persist "
                "across sessions. Higher importance (0.0-1.0) surfaces the memory more often. "
                "Use scope='global' for user-level facts; scope='session' for conversation-specific "
                "context. Set extract_entities=True for named entity fuzzy matching. "
                "Set extract=True for LLM fact triple extraction."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "The memory content to store."},
                    "importance": {"type": "number", "description": "Importance 0.0-1.0. Default 0.5.", "default": 0.5},
                    "source": {"type": "string", "description": "Source tag: preference, fact, insight, identity, task, environment, etc.", "default": "user"},
                    "scope": {"type": "string", "description": "'session' (default) or 'global'.", "default": "session"},
                    "valid_until": {"type": "string", "description": "Optional expiry date YYYY-MM-DD.", "default": ""},
                    "extract_entities": {"type": "boolean", "description": "Extract named entities for fuzzy recall.", "default": False},
                    "extract": {"type": "boolean", "description": "Extract fact triples via LLM.", "default": False},
                    "veracity": {"type": "string", "description": "'stated' | 'inferred' | 'tool' | 'unknown'", "default": "unknown"},
                },
                "required": ["content"],
            },
        ),
        Tool(
            name="hermes_recall",
            description=(
                "Search Hermes Memory with hybrid ranking: vector similarity (50%) + "
                "keyword/FTS5 (30%) + importance (20%) + optional temporal boost. "
                "Returns ranked memories with detailed scores."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Natural language search query."},
                    "limit": {"type": "integer", "description": "Max results. Default 5.", "default": 5},
                    "temporal_weight": {"type": "number", "description": "Recency boost (0.0-0.5). Default 0.0.", "default": 0.0},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="hermes_triple_add",
            description=(
                "Add a fact triple (subject, predicate, object) to the knowledge graph. "
                "Example: ('user', 'prefers', 'concise answers'). Use for structured relationships."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "description": "Subject entity."},
                    "predicate": {"type": "string", "description": "Relationship type."},
                    "object": {"type": "string", "description": "Object entity."},
                    "valid_from": {"type": "string", "description": "ISO date YYYY-MM-DD.", "default": ""},
                    "confidence": {"type": "number", "description": "Confidence 0.0-1.0. Default 1.0.", "default": 1.0},
                },
                "required": ["subject", "predicate", "object"],
            },
        ),
        Tool(
            name="hermes_triple_query",
            description="Query the knowledge graph for facts matching subject/predicate/object patterns.",
            inputSchema={
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "description": "Filter by subject.", "default": ""},
                    "predicate": {"type": "string", "description": "Filter by predicate.", "default": ""},
                    "object": {"type": "string", "description": "Filter by object.", "default": ""},
                },
            },
        ),
        Tool(
            name="hermes_scratchpad",
            description="Read or write the agent scratchpad (temporary reasoning workspace).",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["read", "write", "clear"], "description": "Action to perform."},
                    "content": {"type": "string", "description": "Content to write (only for action='write')."},
                },
                "required": ["action"],
            },
        ),
        Tool(
            name="hermes_memory_stats",
            description="Get Hermes Memory system statistics: memory counts, BEAM tiers, DB size.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="hermes_memory_sleep",
            description=(
                "Run BEAM consolidation: compresses old working memories into episodic summaries. "
                "Call after long sessions or when memory feels stale."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "all_sessions": {"type": "boolean", "description": "Consolidate all sessions.", "default": False},
                    "dry_run": {"type": "boolean", "description": "Preview without writing.", "default": False},
                },
            },
        ),
        Tool(
            name="hermes_memory_forget",
            description="Permanently delete a memory by its ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "memory_id": {"type": "string", "description": "ID of memory to delete."},
                },
                "required": ["memory_id"],
            },
        ),
        Tool(
            name="hermes_memory_diagnose",
            description="Run Hermes Memory system diagnostics: availability, DB health, embedding status.",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


# ─── Tool Handlers ─────────────────────────────────────────────────

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    mem = get_memory()
    
    try:
        if name == "hermes_remember":
            result = mem.remember(
                content=arguments["content"],
                importance=arguments.get("importance", 0.5),
                source=arguments.get("source", "user"),
                scope=arguments.get("scope", "session"),
                valid_until=arguments.get("valid_until", ""),
                extract_entities=arguments.get("extract_entities", False),
                extract=arguments.get("extract", False),
                veracity=arguments.get("veracity", "unknown"),
            )
            
        elif name == "hermes_recall":
            results = mem.recall(
                query=arguments["query"],
                limit=arguments.get("limit", 5),
                temporal_weight=arguments.get("temporal_weight", 0.0),
            )
            result = {"status": "ok", "count": len(results), "results": results}
            
        elif name == "hermes_triple_add":
            result = mem.triple_add(
                subject=arguments["subject"],
                predicate=arguments["predicate"],
                object=arguments["object"],
                valid_from=arguments.get("valid_from", ""),
                confidence=arguments.get("confidence", 1.0),
            )
            
        elif name == "hermes_triple_query":
            results = mem.triple_query(
                subject=arguments.get("subject", ""),
                predicate=arguments.get("predicate", ""),
                object=arguments.get("object", ""),
            )
            result = {"status": "ok", "count": len(results), "triples": results}
            
        elif name == "hermes_scratchpad":
            action = arguments["action"]
            if action == "read":
                entries = mem.scratchpad_read()
                result = {"status": "ok", "count": len(entries), "entries": entries}
            elif action == "write":
                entry_id = mem.scratchpad_write(arguments["content"])
                result = {"status": "stored", "entry_id": entry_id}
            elif action == "clear":
                mem.scratchpad_clear()
                result = {"status": "cleared"}
            else:
                result = {"status": "error", "error": f"Unknown action: {action}"}
                
        elif name == "hermes_memory_stats":
            result = mem.stats()
            
        elif name == "hermes_memory_sleep":
            result = mem.sleep(
                all_sessions=arguments.get("all_sessions", False),
                dry_run=arguments.get("dry_run", False),
            )
            
        elif name == "hermes_memory_forget":
            result = mem.forget(arguments["memory_id"])
            
        elif name == "hermes_memory_diagnose":
            result = mem.diagnose()
            
        else:
            result = {"status": "unknown_tool", "tool": name}
        
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
        
    except Exception as e:
        logger.error(f"Tool {name} failed: {e}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({"status": "error", "error": str(e)}))]


# ─── Main ─────────────────────────────────────────────────────────

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )

if __name__ == "__main__":
    asyncio.run(main())
