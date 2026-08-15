"""Generate a phase-scoped Goose recipe that mounts Praetor's MCP server but
surfaces only a small, relevant tool subset.

Goose enforces an extension's `available_tools` allowlist at BOTH tool-listing
and dispatch, so writing the router's selection into the recipe is how we keep
Praetor's ~390 tools from drowning a small model. We always keep the two control
tools (`search_tools`, `advance_phase`) so the model can pivot cross-phase or
move to the next phase without us re-generating mid-turn.
"""
from __future__ import annotations

import json

from legate.toolselect import Router

# Control tools always surfaced alongside the phase working set. These map to
# Praetor/Legate meta-capabilities (search the full catalog; advance the phase).
CONTROL_TOOLS = ["search_tools", "advance_phase"]
DEVELOPER_TOOLS = ["edit", "write", "shell"]


def select_praetor_tools(router: Router, phase: str, query: str | None,
                         cap: int = 15) -> list[str]:
    """Router selection for a phase/query, with control tools reserved and the
    total held to `cap` (so surfaced schema stays within the model's working set)."""
    room = max(0, cap - len(CONTROL_TOOLS))
    picked = [t.name for t in router.select(phase=phase, query=query, cap=room)]
    # control tools first so they're never squeezed out by the cap
    return CONTROL_TOOLS + [n for n in picked if n not in CONTROL_TOOLS]


def build_dev_recipe(prompt: str, tools: list[str] | None = None) -> dict:
    """A developer-editor-only recipe carrying the task as its prompt. Goose
    forbids `--recipe` with `--text`, so the task must ride inside the recipe."""
    return {
        "version": "1.0.0",
        "title": "legate-dev",
        "description": "Developer editor only.",
        "extensions": [
            {"type": "builtin", "name": "developer",
             "available_tools": tools or DEVELOPER_TOOLS},
        ],
        "prompt": prompt,
    }


def build_recipe(praetor_cmd: str, praetor_args: list[str], phase: str,
                 tools: list[str], praetor_cwd: str | None = None,
                 timeout: int = 300, prompt: str | None = None) -> dict:
    ext = [
        {"type": "builtin", "name": "developer", "available_tools": DEVELOPER_TOOLS},
        {"type": "stdio", "name": "praetor", "cmd": praetor_cmd,
         "args": praetor_args, "timeout": timeout, "available_tools": tools},
    ]
    if praetor_cwd:
        ext[1]["cwd"] = praetor_cwd
    rec = {
        "version": "1.0.0",
        "title": f"legate-praetor-{phase}",
        "description": f"Phase '{phase}': developer editor + {len(tools)} Praetor tools.",
        "extensions": ext,
    }
    if prompt:
        rec["prompt"] = prompt
    return rec


def render_recipe(recipe: dict) -> str:
    """Emit YAML for a recipe dict. Inline lists use JSON (a valid YAML flow
    sequence) to sidestep a yaml dependency; the shape here is fixed and shallow."""
    lines = [
        f'version: "{recipe["version"]}"',
        f'title: "{recipe["title"]}"',
        f'description: "{recipe["description"]}"',
        "extensions:",
    ]
    for e in recipe["extensions"]:
        lines.append(f'  - type: {e["type"]}')
        lines.append(f'    name: {e["name"]}')
        if "cmd" in e:
            lines.append(f'    cmd: "{e["cmd"]}"')
        if "args" in e:
            lines.append(f'    args: {json.dumps(e["args"])}')
        if "cwd" in e:
            lines.append(f'    cwd: "{e["cwd"]}"')
        if "timeout" in e:
            lines.append(f'    timeout: {e["timeout"]}')
        if "available_tools" in e:
            lines.append(f'    available_tools: {json.dumps(e["available_tools"])}')
    if recipe.get("prompt"):
        lines.append("prompt: |")
        for pl in recipe["prompt"].splitlines() or [""]:
            lines.append(f"  {pl}")
    return "\n".join(lines) + "\n"
