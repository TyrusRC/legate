# Legate

A local coding/agent harness that drives a small local model (via [Goose](https://github.com/block/goose)
and llama.cpp) to work at a useful fraction of a frontier subscription agent — self-hosted, no subscription,
uncensored-capable. Designed to also drive MCP servers such as [Praetor](https://github.com/TyrusRC/praetor).

**Status:** MVP, proven end-to-end. On an RTX 3060 12GB (WSL2), Qwen3-Coder-30B-A3B Q4 serves at ~27 tok/s
with reliable native tool-calling (5/5) and **solved the `wordy` polyglot problem — all 25 tests — in one
40-turn run (~6 min)**. Praetor's 390-tool MCP surface enumerates and routes to a ≤15-tool working set. See
[`docs/gap-analysis.md`](docs/gap-analysis.md) for an honest comparison to Claude Code + Opus 5.

## What it is
A thin Python controller that CLI-wraps Goose (no fork): it manages a llama.cpp OpenAI-compatible server,
drives Goose headless in isolated git worktrees, collects edits via `git diff`, and scores results against a
task's tests. The novel work lives above Goose:

- **Best-of-N execution-grounded repair** — N candidates in worktrees, ranked on the real tests, repaired with
  the actual traceback.
- **MCP tool-selection router** — phase-grouping + BM25 keeps a ≤15-tool working set from a 390-tool server.
- **Model-fit flow** — detect the machine, recommend the right model slot + serve flags.
- **bwrap sandbox** — model-generated code runs confined (no network, fail-closed).

## Requirements
- Python 3.11+, [uv](https://docs.astral.sh/uv/); git; [Goose CLI](https://github.com/block/goose)
- **llama.cpp ≥ b10435** `llama-server` (earlier builds drop Qwen3-Coder tool calls) with a served GGUF

## Setup
```bash
bash scripts/setup.sh     # installs deps + writes .env with auto-detected paths
bash scripts/serve.sh &   # serve the model (llama-server, KV-quant, -ncmoe)
```
`setup.sh` is idempotent: it installs Python deps (`uv sync`), creates `.env` from
`.env.example`, and auto-detects `llama-server`, the model GGUF, and Praetor —
filling only blank/placeholder values. Anything it can't find, it tells you to set
in `.env`. (Manual path: `cp .env.example .env` and edit `LEGATE_*`.)

## Use
```bash
legate doctor                     # detect GPU/VRAM/RAM/WSL2
legate models recommend           # rank vetted models by fit, with serve flags
legate solve problems/wordy       # solve one problem end-to-end
legate solve problems/wordy --best-of 6 --repair-rounds 1
legate eval problems              # polyglot resolve rate + % of Opus 5
```

## Develop
```bash
uv run pytest
```
