# Legate

A command-line agent for coding and cybersecurity tasks that runs against a local
model (llama.cpp) via [Goose](https://github.com/block/goose). You describe a task
in natural language; Legate classifies it as coding or security, mounts the
relevant tools, and runs it.

Legate is a Python controller around Goose and llama.cpp. On top of Goose it adds:

- intent and kill-chain-phase routing that narrows a large MCP tool surface (e.g.
  [Praetor](https://github.com/TyrusRC/praetor), ~390 tools) to a working set a
  small model can handle;
- an optional separate (uncensored) model slot for authorized offensive work;
- hardware detection and model-fit recommendation for local serving.

## Requirements

- Python 3.11+ and [uv](https://docs.astral.sh/uv/)
- git
- [Goose CLI](https://github.com/block/goose) (`goose`)
- llama.cpp `llama-server`, build b10435 or newer (older builds drop Qwen3-Coder
  tool calls)
- An NVIDIA GPU for serving (CPU-only serving is not supported)
- Optional, for security work: an MCP server such as Praetor and its backends
  (Burp Suite, CLIs like `nmap` / `katana` / `gau`)

## Install

```
bash scripts/setup.sh
```

Installs Python dependencies, creates `.env` from `.env.example`, and auto-detects
`llama-server`, the model file, and Praetor. It fills only blank values. To
configure manually: `cp .env.example .env` and edit the `LEGATE_*` variables.

## Usage

Serve a model, then run the agent:

```
bash scripts/serve.sh &

legate                                           # interactive session
legate chat "fix the failing test in ./parser"   # one-shot coding task
legate chat "recon http://target/ and list URLs and parameters"
legate chat "test the login at http://target/ for sql injection"
```

- Coding requests use the developer editor (edit / write / shell).
- Security requests are routed to a kill-chain phase (recon / scan / exploit /
  post / report) and driven through Praetor, plus the shell.
- In an interactive session, context carries across turns and output streams as it
  is produced.

Live security engagements require Praetor configured (`LEGATE_PRAETOR_*` in `.env`)
and its backends running. Without them the Praetor tools error and the agent falls
back to shell tooling.

Additional subcommands:

```
legate doctor              # report detected hardware
legate models recommend    # rank local models by fit for this machine
```

## How it works

- **Routing.** A request is classified (coding vs. security, and for security which
  kill-chain phase) deterministically before the model runs. Only the matching
  phase's tools, ranked by BM25, are mounted — a small model cannot be given
  hundreds of MCP tools at once.
- **Execution.** Goose runs headless with `GOOSE_MODE=auto` in the working
  directory you specify. Goose owns the edit/write/shell tools; scope the agent to
  a directory you are willing to let it modify. Legate does not sandbox Goose's
  tool calls.
- **Streaming.** Goose's stream-json output is rendered live (assistant text,
  `⚙ tool(args)`, `↳ result`). Interactive context is kept via Goose sessions; a
  change of phase starts a new session so the new phase's tools are mounted.
- **Timeouts.** Each model run is time-bounded — the Goose process is killed past
  the deadline, so a runaway generation or a dead model server fails fast.

Configuration is read from `.env` (see `.env.example`).

## Development

```
uv run pytest
```

## License

Apache-2.0. See [LICENSE](LICENSE).
