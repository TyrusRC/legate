#!/usr/bin/env bash
# Legate setup: install dependencies and generate a .env with auto-detected paths
# (so nothing is hardcoded). Idempotent — re-run any time; it only fills in blank
# or placeholder values and never clobbers config you've already set.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV="$HERE/.env"
cd "$HERE"

say()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
ok()   { printf '  \033[1;32mok\033[0m   %s\n' "$*"; }
warn() { printf '  \033[1;33mwarn\033[0m %s\n' "$*"; }

# --- .env helpers: set a key only if it's missing or still a placeholder -------
current_val() { grep -E "^$1=" "$ENV" 2>/dev/null | head -1 | cut -d= -f2- || true; }
needs_fill()  { local v; v="$(current_val "$1")"; [ -z "$v" ] || printf '%s' "$v" | grep -q '/path/to'; }
set_env() {  # set_env KEY VALUE  (upsert)
  local key="$1" val="$2"
  if grep -qE "^${key}=" "$ENV" 2>/dev/null; then
    # sed with | delimiter since values are paths; escape any | in the value
    local esc="${val//|/\\|}"
    sed -i "s|^${key}=.*|${key}=${esc}|" "$ENV"
  else
    printf '%s=%s\n' "$key" "$val" >> "$ENV"
  fi
}
fill_if_empty() {  # fill_if_empty KEY VALUE  (only when missing/placeholder)
  local key="$1" val="$2"
  if [ -n "$val" ] && needs_fill "$key"; then set_env "$key" "$val"; ok "$key = $val"; fi
}

# --- 1. prerequisites ---------------------------------------------------------
say "Checking prerequisites"
command -v python3 >/dev/null && ok "python3 $(python3 -V 2>&1 | awk '{print $2}')" || { warn "python3 missing"; MISS=1; }
if command -v uv >/dev/null; then ok "uv $(uv --version 2>&1 | awk '{print $2}')"
else warn "uv missing — install: curl -LsSf https://astral.sh/uv/install.sh | sh"; MISS=1; fi
command -v git >/dev/null && ok "git" || { warn "git missing"; MISS=1; }
command -v goose >/dev/null && ok "goose" || warn "goose CLI not found — needed to run solves (https://github.com/block/goose)"
command -v nvidia-smi >/dev/null && ok "nvidia-smi" || warn "nvidia-smi not found — GPU serving unavailable"
[ "${MISS:-0}" = 1 ] && { warn "install the missing required tools above, then re-run"; exit 1; }

# --- 2. python deps -----------------------------------------------------------
say "Installing Python dependencies (uv sync)"
uv sync
ok "legate installed (run via 'uv run legate ...')"

# --- 3. .env ------------------------------------------------------------------
say "Configuring .env"
if [ ! -f "$ENV" ]; then cp "$HERE/.env.example" "$ENV"; ok "created .env from .env.example"; else ok ".env exists — filling only blanks/placeholders"; fi

# 3a. llama-server binary (needs >= b10435 for Qwen3-Coder tool calls)
LLAMA=""
if command -v llama-server >/dev/null; then LLAMA="$(command -v llama-server)"
else for c in "$HOME/llama.cpp/build/bin/llama-server" "$HOME/src/llama.cpp/build/bin/llama-server" \
              "/opt/llama.cpp/build/bin/llama-server"; do [ -x "$c" ] && LLAMA="$c" && break; done
fi
[ -n "$LLAMA" ] && fill_if_empty LEGATE_LLAMA_BIN "$LLAMA" || warn "llama-server not found — set LEGATE_LLAMA_BIN in .env"

# 3b. model GGUF (first Qwen3-Coder*.gguf found in common model dirs)
MODEL=""
for dir in "${LEGATE_MODEL_DIR:-}" /mnt/d/LLModel "$HOME/models" "$HOME/.cache/llama.cpp" "$HERE/models"; do
  [ -n "$dir" ] && [ -d "$dir" ] || continue
  MODEL="$(find "$dir" -maxdepth 1 -iname 'Qwen3-Coder*.gguf' 2>/dev/null | head -1)"
  [ -n "$MODEL" ] && break
done
[ -n "$MODEL" ] && fill_if_empty LEGATE_MODEL_PATH "$MODEL" || warn "no Qwen3-Coder*.gguf found — set LEGATE_MODEL_PATH in .env"

# 3c. Praetor MCP server (optional; sibling checkout by convention)
for p in "$HERE/../praetor/mcp-server" "$HOME/project/trc/praetor/mcp-server"; do
  if [ -x "$p/.venv/bin/python" ]; then
    fill_if_empty LEGATE_PRAETOR_CMD "$(cd "$p" && pwd)/.venv/bin/python"
    fill_if_empty LEGATE_PRAETOR_ARGS "-m burpsuite_mcp"
    fill_if_empty LEGATE_PRAETOR_CWD "$(cd "$p" && pwd)"
    break
  fi
done
grep -q '^LEGATE_PRAETOR_CMD=' "$ENV" 2>/dev/null && [ -n "$(current_val LEGATE_PRAETOR_CMD)" ] \
  && ok "Praetor configured" || warn "Praetor not found (optional) — set LEGATE_PRAETOR_* in .env to drive it"

# --- 4. report ----------------------------------------------------------------
say "Setup complete. Detected hardware:"
uv run legate doctor || true
echo
say "Next: 'bash scripts/serve.sh &' to serve, then 'uv run legate' to open the agent"
