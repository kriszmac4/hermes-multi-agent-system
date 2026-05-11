#!/usr/bin/env python3
"""
Intelligent Task Router — elemzi a feladat komplexitását és kiválasztja a legjobb modellt.
Használat: python route_task.py "feladat leírása"
"""

import sys
import re

# Modell konfiguráció
MODELS = {
    "trivial":   {"model": None, "timeout": 0},           # Válaszol maga az agent
    "simple":    {"model": "groq/llama-3.1-8b-instant", "timeout": 30},
    "moderate":  {"model": "groq/llama-3.3-70b-versatile", "timeout": 120},
    "complex":   {"model": "openrouter/claude-haiku", "timeout": 300},
    "expert":    {"model": "openrouter/claude-sonnet-4", "timeout": 600},
}

# Complexity markerek
COMPLEXITY_PATTERNS = {
    "expert": [
        r"kutass", r"research", r"tanulmány", r"benchmark", r"compare",
        r"evaluate", r"paper", r"experiment", r"HBO", r"novel", r"innovat",
        r"eredeti megoldás", r"publikáció", r"PhD"
    ],
    "complex": [
        r"tervezd", r"architektúra", r"architecture", r"system design",
        r"redesign", r"migrate", r"optimize", r"security audit",
        r"refactor entire", r"multi-.*file", r"distributed", r"microservices"
    ],
    "moderate": [
        r"írd meg", r"code", r"write", r"edit", r"analyze", r"compile",
        r"build", r"convert", r"refactor", r"debug", r"fix", r"szerkeszt",
        r"elemezd", r"fordítsd", r"create", r"implement", r"generate"
    ],
    "simple": [
        r"keress", r"találj", r"info", r"details", r"search", r"find",
        r"lookup", r"read", r"fetch", r"listázd", r"részletek", r"mutasd"
    ],
    "trivial": [
        r"^mi az \w", r"^what is", r"^miért", r"^why", r"^hogyan",
        r"^how to", r"^mikor", r"^when", r"^hol", r"^where",
        r"^ki ", r"^who", r"^lista", r"^list", r"^define"
    ]
}

def analyze_complexity(task: str) -> str:
    """Elemezi a feladatot és visszaadja a komplexitási szintet."""
    task_lower = task.lower()
    
    # Expert first (highest priority)
    for pattern in COMPLEXITY_PATTERNS["expert"]:
        if re.search(pattern, task_lower, re.IGNORECASE):
            return "expert"
    
    # Complex
    for pattern in COMPLEXITY_PATTERNS["complex"]:
        if re.search(pattern, task_lower, re.IGNORECASE):
            return "complex"
    
    # Moderate
    for pattern in COMPLEXITY_PATTERNS["moderate"]:
        if re.search(pattern, task_lower, re.IGNORECASE):
            return "moderate"
    
    # Simple
    for pattern in COMPLEXITY_PATTERNS["simple"]:
        if re.search(pattern, task_lower, re.IGNORECASE):
            return "simple"
    
    # Trivial (default for very short questions)
    if len(task.split()) <= 5 and ("?" in task or "mi" in task_lower):
        return "trivial"
    
    # Default to medium if no pattern matches
    return "moderate"

def get_model_for_task(task: str, force: str = None) -> dict:
    """Visszaadja a feladathoz legmegfelelőbb modellt és timeout-ot."""
    if force and force in MODELS:
        complexity = force
    else:
        complexity = analyze_complexity(task)
    
    config = MODELS[complexity]
    
    return {
        "complexity": complexity,
        "model": config["model"],
        "timeout": config["timeout"],
        "delegate": config["model"] is not None  # True ha delegálni kell
    }

def main():
    if len(sys.argv) < 2:
        print("Használat: python route_task.py \"feladat leírása\" [--force MODEL]")
        print("Modellek: trivial, fast, medium, strong, expert")
        sys.exit(1)
    
    # Parse arguments
    task = sys.argv[1]
    force = None
    
    if len(sys.argv) > 2 and sys.argv[2] == "--force":
        force = sys.argv[3] if len(sys.argv) > 3 else None
        # Alias mapping
        aliases = {"fast": "simple", "medium": "moderate", "strong": "complex"}
        force = aliases.get(force, force)
    
    # Analyze
    result = get_model_for_task(task, force)
    
    print(f"Feladat: {task}")
    print(f"Komplexitás: {result['complexity']}")
    print(f"Modell: {result['model'] or '(agent maga válaszol)'}")
    print(f"Timeout: {result['timeout']}s")
    print(f"Delegálás: {'Igen' if result['delegate'] else 'Nem'}")

if __name__ == "__main__":
    main()
