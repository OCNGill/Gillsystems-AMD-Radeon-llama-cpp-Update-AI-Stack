#!/usr/bin/env bash

set -euo pipefail

MODEL_PATH="/home/deck/Desktop/Models/gemma-4-E4B.Q6_K.gguf"
SERVER_EXE="/home/deck/src/llama.cpp/bin/llama-server"
LLAMA_LIB_DIR="/home/deck/src/llama.cpp/build-vulkan/bin"
HOST="10.0.0.139"
PORT="8013"
CTX_SIZE="32768"
BATCH_SIZE="2048"
UBATCH_SIZE="512"
GPU_LAYERS="99"
PARALLEL_REQUESTS="1"
FLASH_ATTN="on"
TEMPERATURE="0.20"
TOP_K="20"
MIN_P="0.05"

echo "Starting Steam Deck AI Server..."
echo "Model:   $MODEL_PATH"
echo "Host:    $HOST:$PORT"
echo "Context: $CTX_SIZE"
echo "Binary:  $SERVER_EXE"
echo "Lib dir: $LLAMA_LIB_DIR"
echo

if [[ "${1:-}" == "--dry-run" ]]; then
    echo "Dry run only. Command would launch the Steam Deck AI Server configuration above."
    exit 0
fi

if [[ ! -x "$SERVER_EXE" ]]; then
    echo "[Gillsystems] ERROR: Binary not found at $SERVER_EXE"
    exit 1
fi

if [[ ! -d "$LLAMA_LIB_DIR" ]]; then
    echo "[Gillsystems] ERROR: Library directory not found at $LLAMA_LIB_DIR"
    exit 1
fi

if [[ ! -f "$MODEL_PATH" ]]; then
    echo "[Gillsystems] ERROR: Model not found at $MODEL_PATH"
    exit 1
fi

export LD_LIBRARY_PATH="$LLAMA_LIB_DIR:${LD_LIBRARY_PATH:-}"

exec "$SERVER_EXE" \
  -m "$MODEL_PATH" \
  -c "$CTX_SIZE" \
  -ngl "$GPU_LAYERS" \
  -fa "$FLASH_ATTN" \
  -np "$PARALLEL_REQUESTS" \
  -b "$BATCH_SIZE" \
  -ub "$UBATCH_SIZE" \
  --port "$PORT" \
  --host "$HOST" \
  --jinja \
  --context-shift \
  --temperature "$TEMPERATURE" \
  --top-k "$TOP_K" \
  --min-p "$MIN_P" \
  -r "<|im_end|>,<|im_start|>" \
  --metrics \
  --no-mmap