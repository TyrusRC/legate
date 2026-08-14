# Legate

A local coding/agent harness that drives a small local model (via [Goose](https://github.com/block/goose)
and llama.cpp) to work at a useful fraction of a frontier subscription agent — self-hosted, no subscription,
uncensored-capable. Designed to also drive MCP servers such as [Praetor](https://github.com/TyrusRC/praetor).

**Status:** early scaffolding (walking skeleton). See `docs/` for the design spec and plans.

## What it is
A thin Python controller that CLI-wraps Goose (no fork): it manages a llama.cpp OpenAI-compatible server,
drives Goose headless in isolated git worktrees, collects edits via `git diff`, and scores results against a
task's tests. The novel work lives above Goose — a best-of-N execution-grounded repair loop, MCP tool-selection
for large tool sets, and an eval runner that measures capability.

## Requirements
- Python 3.11+, [uv](https://docs.astral.sh/uv/)
- [Goose CLI](https://github.com/block/goose) (`goose`)
- llama.cpp (`llama` / `llama-server`) with a served GGUF model
- git

## Develop
```bash
uv run pytest
```
