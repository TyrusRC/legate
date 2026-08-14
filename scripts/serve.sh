#!/bin/bash
# Serve the local coder model via llama.cpp with an OpenAI-compatible endpoint.
# Config comes from .env (see .env.example). Tuned for RTX 3060 12GB: MoE experts
# spilled to RAM via -ncmoe (lower LEGATE_NCMOE if OOM).
set -e
HERE="$(cd "$(dirname "$0")/.." && pwd)"
[ -f "$HERE/.env" ] && set -a && . "$HERE/.env" && set +a

MODEL="${1:-${LEGATE_MODEL_PATH:?set LEGATE_MODEL_PATH in .env}}"
NCMOE="${LEGATE_NCMOE:-24}"
PORT="${LEGATE_PORT:-8080}"
ALIAS="${LEGATE_MODEL:-qwen3-coder}"

exec llama serve -m "$MODEL" \
  -ngl 99 -ncmoe "$NCMOE" -fa on -c 32768 --jinja \
  --host 127.0.0.1 --port "$PORT" --alias "$ALIAS"
