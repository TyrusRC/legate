#!/bin/bash
# Serve the local coder model via llama.cpp with an OpenAI-compatible endpoint.
# Tuned for RTX 3060 12GB: MoE experts spilled to RAM via -ncmoe, KV cache
# quantized to q8_0 to free VRAM (needs -fa on). Config comes from .env
# (see .env.example); any var already set in the environment OVERRIDES .env,
# so callers (e.g. the model-fit probe) can sweep LEGATE_NCMOE without editing .env.
set -e
HERE="$(cd "$(dirname "$0")/.." && pwd)"

# Load .env as DEFAULTS only — never clobber a var the caller already exported.
if [ -f "$HERE/.env" ]; then
  while IFS='=' read -r k v; do
    case "$k" in ''|\#*) continue ;; esac          # skip blanks/comments
    [[ "$k" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    [ -z "${!k+x}" ] && export "$k=$v"             # set only if unset
  done < "$HERE/.env"
fi

MODEL="${1:-${LEGATE_MODEL_PATH:?set LEGATE_MODEL_PATH in .env}}"
NCMOE="${LEGATE_NCMOE:-30}"
PORT="${LEGATE_PORT:-8080}"
ALIAS="${LEGATE_MODEL:-qwen3-coder}"
CTX="${LEGATE_CTX:-32768}"
HOST="${LEGATE_HOST:-127.0.0.1}"
# Use the dedicated llama-server binary (not the unified `llama serve` launcher).
# Needs llama.cpp >= b10435 for Qwen3-Coder tool-call parsing (missing <tool_call>).
LLAMA_BIN="${LEGATE_LLAMA_BIN:-llama-server}"

exec "$LLAMA_BIN" -m "$MODEL" \
  -ngl 99 -ncmoe "$NCMOE" -fa on -c "$CTX" \
  -ctk q8_0 -ctv q8_0 --jinja \
  --host "$HOST" --port "$PORT" --alias "$ALIAS"
