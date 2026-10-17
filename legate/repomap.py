"""Compact repo map for the coding path: a stdlib-`ast` symbol skeleton (each
Python file → its top-level functions and classes, with signatures and method
names) injected into the dev recipe, so a small, short-context model gets the
*shape* of the codebase without reading every file first.

Python-only by design — the coding path is Python-centric, and other languages
are skipped rather than adding a tree-sitter dependency. NOTE (ceiling): top-level
defs plus one level of class methods, signatures only — no call graph, no
cross-file references, no docstrings. That's the lazy 80% of what a repo map buys
at this model size; a deeper map is the upgrade path if it proves worth it.
"""
from __future__ import annotations

import ast
import os
from pathlib import Path

_SKIP_DIRS = {
    ".git", ".venv", "venv", "env", "__pycache__", "node_modules", ".legate",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", "build", "dist",
    ".eggs", "site-packages",
}


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """`name(arg, arg, *args, **kwargs)` — argument names only (types/defaults
    dropped to keep the map compact)."""
    a = node.args
    parts = [arg.arg for arg in [*a.posonlyargs, *a.args]]
    if a.vararg:
        parts.append("*" + a.vararg.arg)
    parts += [arg.arg for arg in a.kwonlyargs]
    if a.kwarg:
        parts.append("**" + a.kwarg.arg)
    return f"{node.name}({', '.join(parts)})"


def _file_symbols(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (SyntaxError, ValueError, OSError):
        return []  # unparseable file → no symbols, never raise
    out: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append("def " + _signature(node))
        elif isinstance(node, ast.ClassDef):
            methods = [n.name for n in node.body
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            out.append(f"class {node.name}" + (": " + ", ".join(methods) if methods else ""))
    return out


def build_repo_map(root: str | Path, max_files: int = 60, max_chars: int = 4000) -> str:
    """A compact per-file symbol listing for the Python files under `root`, bounded
    by `max_files` and `max_chars` so it can't blow the model's context. Returns ""
    when there's nothing to map (no Python, or not a directory)."""
    root = Path(root)
    if not root.is_dir():
        return ""
    lines: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # prune noise dirs in place so os.walk doesn't descend into them
        dirnames[:] = sorted(d for d in dirnames
                             if d not in _SKIP_DIRS and not d.startswith("."))
        for fn in sorted(filenames):
            if not fn.endswith(".py"):
                continue
            p = Path(dirpath) / fn
            syms = _file_symbols(p)
            if not syms:
                continue
            lines.append(f"{p.relative_to(root)}: " + "; ".join(syms))
            if len(lines) >= max_files:
                break
        if len(lines) >= max_files:
            break
    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[:max_chars].rsplit("\n", 1)[0] + "\n… (repo map truncated)"
    return text
