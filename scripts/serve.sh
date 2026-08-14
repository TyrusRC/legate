#!/bin/bash
# Serve the local coder model via llama.cpp with an OpenAI-compatible endpoint.
# Tuned for RTX 3060 12GB: MoE experts spilled to RAM via -ncmoe (lower NCMOE if OOM).
set -e
MODEL="${1:-/mnt/d/LLModel/Qwen3-Coder-30B-A3B-Instruct-UD-Q4_K_XL.gguf}"
NCMOE="${NCMOE:-24}"
PORT="${PORT:-8080}"
exec llama serve -m "$MODEL" \
  -ngl 99 -ncmoe "$NCMOE" -fa on -c 32768 --jinja \
  --host 127.0.0.1 --port "$PORT" --alias qwen3-coder
