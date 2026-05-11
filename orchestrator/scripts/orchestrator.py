#!/usr/bin/env python3
"""
Hermes Orchestrator — Multi-agent task coordinator.

Runs tasks via hermes chat --profile X -q, collects results, synthesizes output.

Usage:
    ~/.hermes/.venv/bin/python3 orchestrator.py "Keress szállásokat Zürichben 600€ körül"
    ~/.hermes/.venv/bin/python3 orchestrator.py --profiles research,dev "Kutatás + kódolás"
"""

import asyncio
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


PROFILES = {
    "research": {
        "model": "glm-5.1",
        "keywords": ["kutatás", "research", "elemzés", "összehasonlítás", "keresés", "találj", "milyen"],
        "description": "Deep analysis, research, comparison",
        "timeout": 300,
    },
    "dev": {
        "model": "deepseek-v4-flash",
        "keywords": ["kód", "code", "implement", "script", "api", "python", "fejleszt", "build"],
        "description": "Coding, implementation, development",
        "timeout": 300,
    },
    "devops": {
        "model": "minimax-m2.5",
        "keywords": ["infra", "deploy", "docker", "server", "ci/cd", "nginx", "ssl"],
        "description": "Infrastructure, deployment, DevOps",
        "timeout": 300,
    },
    "news": {
        "model": "deepseek-v4-flash",
        "keywords": ["hír", "news", "aktual", "cikk", "tldr", "összefoglaló"],
        "description": "News, current events, summaries",
        "timeout": 180,
    },
    "study": {
        "model": "glm-5",
        "keywords": ["jog", "law", "tanul", "vizsga", "jogi", "polgári", "büntető"],
        "description": "Law, education, study materials",
        "timeout": 300,
    },
}


@dataclass
class TaskResult:
    profile: str
    success: bool
    output: str
    duration: float
    error: Optional[str] = None


def select_profiles(task: str, explicit_profiles: Optional[list] = None) -> list:
    if explicit_profiles:
        return [p for p in explicit_profiles if p in PROFILES]
    task_lower = task.lower()
    selected = []
    for profile, config in PROFILES.items():
        for keyword in config["keywords"]:
            if keyword in task_lower:
                selected.append(profile)
                break
    if not selected:
        selected = ["research"]
    return selected


def clean_hermes_output(output: str) -> str:
    lines = output.split('\n')
    cleaned = []
    skip_until_empty = False
    for line in lines:
        if any(c in line for c in ['╭', '╮', '╯', '╰', '│', '─', '═']):
            skip_until_empty = True; continue
        if '⣀' in line or '⣴' in line or '⣿' in line:
            skip_until_empty = True; continue
        if 'Available Tools' in line or 'Hermes Agent v' in line:
            skip_until_empty = True; continue
        if any(x in line for x in ['ctx --', '⏲', 'K/', '%', 'MB', '░', '█', '▓', '▒']):
            continue
        if skip_until_empty and not line.strip():
            skip_until_empty = False; continue
        if skip_until_empty: continue
        if '⚠' in line or 'hermes setup' in line.lower(): continue
        cleaned.append(line)
    return '\n'.join(cleaned).strip()


async def run_profile(profile: str, task: str) -> TaskResult:
    start = time.time()
    timeout = PROFILES[profile]["timeout"]
    
    # Load .env for API keys
    import os
    env = os.environ.copy()
    env_path = Path.home() / ".hermes" / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, _, value = line.partition('=')
                key, value = key.strip(), value.strip()
                if key and value:
                    env[key] = value
    
    cmd = f"hermes chat --profile {profile} -q '{task}'"
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        duration = time.time() - start
        raw_output = stdout.decode().strip()
        output = clean_hermes_output(raw_output)
        if proc.returncode == 0:
            return TaskResult(profile=profile, success=True, output=output, duration=duration)
        else:
            error = stderr.decode().strip()
            return TaskResult(profile=profile, success=False, output=output, duration=duration, error=error)
    except asyncio.TimeoutError:
        return TaskResult(profile=profile, success=False, output="", duration=timeout, error=f"Timeout after {timeout}s")
    except Exception as e:
        return TaskResult(profile=profile, success=False, output="", duration=time.time() - start, error=str(e))


async def orchestrate(task: str, profiles: list, parallel: bool = True) -> dict:
    print(f"🎯 Orchestrating: {task}")
    print(f"📋 Profiles: {', '.join(profiles)}")
    print(f"⚡ Mode: {'parallel' if parallel else 'sequential'}")
    results = []
    if parallel:
        tasks = [run_profile(p, task) for p in profiles]
        results = await asyncio.gather(*tasks)
    else:
        for profile in profiles:
            result = await run_profile(profile, task)
            results.append(result)
    print("\n" + "="*60)
    print("📊 EREDMÉNYEK")
    print("="*60)
    for result in results:
        status = "✅" if result.success else "❌"
        print(f"\n{status} [{result.profile}] ({result.duration:.1f}s)")
        if result.success:
            print(result.output[:500])
        else:
            print(f"Error: {result.error}")
    return {
        "task": task, "profiles": profiles,
        "results": [{"profile": r.profile, "success": r.success, "output": r.output, "duration": r.duration, "error": r.error} for r in results],
        "total_duration": sum(r.duration for r in results),
        "success_count": sum(1 for r in results if r.success),
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Hermes Multi-Agent Orchestrator")
    parser.add_argument("task", help="Task to execute")
    parser.add_argument("--profiles", "-p", help="Comma-separated profile names")
    parser.add_argument("--parallel", action="store_true", help="Run in parallel")
    parser.add_argument("--sequential", action="store_true", default=True, help="Run sequentially (default)")
    parser.add_argument("--json", action="store_true", help="Output JSON results")
    args = parser.parse_args()
    explicit_profiles = args.profiles.split(",") if args.profiles else None
    profiles = select_profiles(args.task, explicit_profiles)
    parallel = not args.sequential
    results = asyncio.run(orchestrate(args.task, profiles, parallel))
    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
