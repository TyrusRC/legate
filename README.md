# Legate

A local agent harness that drives small local models — through
[Goose](https://github.com/block/goose) and llama.cpp — to perform coding and
security tasks without a subscription. It can also drive MCP servers such as
[Praetor](https://github.com/TyrusRC/praetor).

Legate is a thin Python controller: it manages a llama.cpp server, runs Goose
headless in isolated git worktrees, and scores results against a task's tests.
The added value is above Goose — execution-grounded best-of-N, tool selection for
large MCP servers, model-fit recommendation, and a sandbox for untrusted code.

## Requirements

- Python 3.11+ and [uv](https://docs.astral.sh/uv/)
- git
- [Goose CLI](https://github.com/block/goose) (`goose`)
- llama.cpp `llama-server`, build **b10435 or newer** (older builds drop
  Qwen3-Coder tool calls)
- bubblewrap (`bwrap`) for sandboxed execution
- An NVIDIA GPU for serving (CPU-only serving is out of scope)

## Install

```
bash scripts/setup.sh
```

Installs Python dependencies, creates `.env` from `.env.example`, and auto-detects
`llama-server`, the model file, and Praetor. It only fills blank values; edit
`.env` for anything it cannot find. Manual path: `cp .env.example .env` and edit
the `LEGATE_*` variables.

## Usage

Serve a model, then run a command:

```
bash scripts/serve.sh &

legate doctor                              # report detected hardware
legate models recommend                    # rank local models by fit
legate solve <problem_dir>                 # solve one problem
legate solve <problem_dir> --best-of 6     # generate N candidates, pick the best
legate eval problems                       # run the polyglot suite
legate pentest plan --phase exploit --query "sql injection"
```

A problem directory is any directory containing a `.legate-problem.json` manifest
(`id`, `language`, `test_cmd`, and `protect` — files restored before scoring).

## How it works

- **Isolation.** Each attempt runs in a throwaway git worktree; the outcome comes
  from the task's own tests, not from the model's self-report. Protected files
  (the tests) are restored before scoring.
- **Best-of-N.** Generates N candidate patches, ranks them by test outcome, and
  repairs the best one using the real test output.
- **Tool selection.** For an MCP server with a large tool surface, tools are
  grouped by phase and ranked with BM25, exposing a small working set per step.
- **Sandbox.** Model-generated code runs under bubblewrap with no network, a
  cleared environment, and a single writable working directory.

Configuration is read from `.env` (see `.env.example`); paths are never hardcoded.

## Development

```
uv run pytest
```

## License

Apache-2.0. See [LICENSE](LICENSE).
