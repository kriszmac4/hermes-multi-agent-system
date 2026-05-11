#!/usr/bin/env python3
"""
Discord Task Sender — Posts tasks to Discord channels for the bridge_v3.py bots to handle.

Usage:
    ~/.hermes/.venv/bin/python3 discord_task.py "Keress szállásokat Zürichben 600€ körül"
    ~/.hermes/.venv/bin/python3 discord_task.py --channel research "Keress szállásokat"
    ~/.hermes/.venv/bin/python3 discord_task.py --channel team --mention research "Keress szállásokat"
"""

import asyncio
import json
import sys
from pathlib import Path

import aiohttp

CONFIG_PATH = Path.home() / ".hermes" / "discord-multi-agent" / "config.json"

# Bot IDs for mentions
BOT_IDS = {
    "general": "1501141496487870524",
    "research": "1501139324861681736",
    "dev": "1501140611506372760",
    "devops": "1501141067607707829",
    "news": "1501141173530792027",
    "study": "1501611238747013180",
}


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


async def send_task_to_discord(channel_name: str, task: str, mention: str = None, token: str = None) -> bool:
    """Send a task to a Discord channel."""
    config = load_config()
    channel_id = config["channels"].get(channel_name)
    
    if not token:
        token = config["tokens"].get("general")  # Default to general bot
    
    if not channel_id:
        print(f"❌ Channel '{channel_name}' not found")
        return False
    
    # Build message with optional mention
    message = ""
    if mention and mention in BOT_IDS:
        message = f"<@{BOT_IDS[mention]}> "
    
    message += task
    
    # Send via Discord API
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json",
        "User-Agent": "Hermes-Orchestrator/1.0",
    }
    
    async with aiohttp.ClientSession() as session:
        data = {"content": message}
        async with session.post(url, json=data, headers=headers) as resp:
            if resp.status not in (200, 201):
                body = await resp.text()
                print(f"❌ Discord send failed: {resp.status} {body[:200]}")
                return False
    
    return True


async def send_parallel_tasks(tasks: list) -> dict:
    """Send multiple tasks to Discord in parallel.
    
    tasks: list of {"channel": "team", "task": "description", "mention": "research"}
    """
    config = load_config()
    results = []
    
    async def send_one(task_spec):
        channel = task_spec.get("channel", "team")
        task = task_spec["task"]
        mention = task_spec.get("mention")
        token = config["tokens"].get("general")
        
        success = await send_task_to_discord(channel, task, mention, token)
        return {
            "channel": channel,
            "task": task[:100],
            "mention": mention,
            "success": success,
        }
    
    # Send all tasks in parallel
    coros = [send_one(t) for t in tasks]
    results = await asyncio.gather(*coros)
    
    return {
        "total": len(tasks),
        "sent": sum(1 for r in results if r["success"]),
        "failed": sum(1 for r in results if not r["success"]),
        "results": results,
    }


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Discord Task Sender")
    parser.add_argument("task", help="Task description")
    parser.add_argument("--channel", "-c", default="team", help="Channel (default: team)")
    parser.add_argument("--mention", "-m", help="Mention agent (research, dev, devops, news, study)")
    
    args = parser.parse_args()
    
    result = asyncio.run(send_task_to_discord(args.channel, args.task, args.mention))
    
    if result:
        print(f"✅ Task sent to #{args.channel}")
        if args.mention:
            print(f"   Mentioned: @{args.mention}")
    else:
        print("❌ Failed to send task")
        sys.exit(1)


if __name__ == "__main__":
    main()
