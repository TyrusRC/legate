#!/bin/bash
# Serve local model(s) via llama.cpp with an OpenAI-compatible endpoint.
#
# Two modes:
#   • single-model (default): serve LEGATE_MODEL_PATH. Tuned for RTX 3060 12GB —
#     MoE experts spilled to RAM (-ncmoe), KV cache q8_0 (needs -fa on).
#   • router (when LEGATE_SECURITY_MODEL_PATH is set to a different file): serve the
#     coding model AND the security model by name on one port, loading at most one
#     at a time (--models-max 1) and swapping on demand. This is what lets the agent
#     route coding→coding-model and security→uncensored-model on a single GPU.
#
# Config comes from .env (see .env.example); any var already set in the environment
# OVERRIDES .env, so callers can sweep LEGATE_NCMOE without editing .env.
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

CODING_MODEL="${1:-${LEGATE_MODEL_PATH:?set LEGATE_MODEL_PATH in .env}}"
CODING_NAME="${LEGATE_MODEL:-qwen3-coder}"
SEC_MODEL="${LEGATE_SECURITY_MODEL_PATH:-}"
SEC_NAME="${LEGATE_SECURITY_MODEL:-$CODING_NAME}"
NCMOE="${LEGATE_NCMOE:-30}"
PORT="${LEGATE_PORT:-8080}"
CTX="${LEGATE_CTX:-32768}"
HOST="${LEGATE_HOST:-127.0.0.1}"
# Dedicated llama-server binary (>= b10435 for Qwen3-Coder tool-call parsing).
LLAMA_BIN="${LEGATE_LLAMA_BIN:-llama-server}"

if [ -n "$SEC_MODEL" ] && [ "$SEC_MODEL" != "$CODING_MODEL" ]; then
  # ── router mode: coding + security models, swap one at a time ────────────────
  PRESET="$HERE/.legate-models.ini"
  {
    echo "version = 1"
    echo "[*]"
    echo "c = $CTX"
    echo "flash-attn = on"
    echo "cache-type-k = q8_0"
    echo "cache-type-v = q8_0"
    echo "jinja = true"
    echo "n-gpu-layers = 99"
    echo ""
    echo "[$CODING_NAME]"
    echo "model = $CODING_MODEL"
    echo "n-cpu-moe = $NCMOE"          # coding model is MoE; spill experts to RAM
    echo ""
    echo "[$SEC_NAME]"
    echo "model = $SEC_MODEL"          # security model (dense) — no -ncmoe
  } > "$PRESET"
  echo "router mode: '$CODING_NAME' + '$SEC_NAME' on $HOST:$PORT (max 1 loaded, swaps on demand)"
  exec "$LLAMA_BIN" --models-preset "$PRESET" --models-max 1 --models-autoload \
    --host "$HOST" --port "$PORT"
else
  # ── single-model mode (backward compatible) ──────────────────────────────────
  exec "$LLAMA_BIN" -m "$CODING_MODEL" \
    -ngl 99 -ncmoe "$NCMOE" -fa on -c "$CTX" \
    -ctk q8_0 -ctv q8_0 --jinja \
    --host "$HOST" --port "$PORT" --alias "$CODING_NAME"
fi
