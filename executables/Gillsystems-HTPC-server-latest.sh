#!/usr/bin/env bash
# ============================================================
# Gillsystems HTPC Server Launcher (Linux / RX 7600)
# Adapted with iGPU optimizations, tailored for 16GB RAM + 8GB VRAM.
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Explicitly set the library path for local custom builds

MODEL_PATH="/home/gillsystems-htpc/Desktop/Models/gemma-4-E4B.Q6_K.gguf"
HOST="10.0.0.42"
PORT="8011"
# 16384 (16k) context fits comfortably in 8GB VRAM alongside the ~5GB model.
CTX_SIZE="16384" 
GPU_LAYERS="99"  # Offloads all layers
PARALLEL_REQUESTS="1"
FLASH_ATTN="on"
LOG_DIR="$SCRIPT_DIR/../logs"

# Use the custom `go` binary if available, or fallback to standard ones
SERVER_EXE=""
for candidate in \
  "/home/gillsystems-htpc/src/llama.cpp/bin/llama-server" \
  "/home/gillsystems-htpc/src/llama.cpp/build-hip/bin/llama-server" \
  "/opt/gillsystems/llama.cpp/bin/llama-server"; do
    if [[ -z "$SERVER_EXE" && -x "$candidate" ]]; then
        SERVER_EXE="$candidate"
    fi
done

mkdir -p "$LOG_DIR"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
NODE_NAME="$(hostname)"
LOG_FILE="$LOG_DIR/server_${NODE_NAME}_${TIMESTAMP}.log"

echo "Starting Gillsystems HTPC LLM Server..."
echo "Model:   $MODEL_PATH"
echo "Host:    $HOST:$PORT"
echo "Context: $CTX_SIZE"
echo "Log:     $LOG_FILE"
echo

if [[ "${1:-}" == "--dry-run" ]]; then
    echo "Dry run only. Command would launch the HTPC server configuration above."
    exit 0
fi

if [[ -z "$SERVER_EXE" ]]; then
    echo "[Gillsystems] ERROR: llama-server executable (or 'go') was not found."
    exit 1
fi

if [[ ! -f "$MODEL_PATH" ]]; then
    echo "[Gillsystems] ERROR: Model not found at $MODEL_PATH"
    exit 1
fi

# Link binary and library paths dynamically for canonical installs
LLAMA_BIN_DIR="$(dirname "$SERVER_EXE")"
LLAMA_LIB_DIR="/opt/gillsystems/llama.cpp/lib"

if [[ -d "$LLAMA_LIB_DIR" ]]; then
    export LD_LIBRARY_PATH="$LLAMA_LIB_DIR:${LD_LIBRARY_PATH:-}"
fi

# Steam Deck/iGPU Optimization checks for tensile libraries
TENSILE_LIBPATH="$LLAMA_BIN_DIR/rocblas/library"
if [[ -d "$TENSILE_LIBPATH" ]]; then
    export ROCBLAS_TENSILE_LIBPATH="$TENSILE_LIBPATH"
fi

echo "Executable: $SERVER_EXE"
echo "LD_LIBRARY_PATH: ${LD_LIBRARY_PATH:-}"

set +e
"$SERVER_EXE" \
  -m "$MODEL_PATH" \
  -c "$CTX_SIZE" \
  -ngl "$GPU_LAYERS" \
  -fa "$FLASH_ATTN" \
  -np "$PARALLEL_REQUESTS" \
  --port "$PORT" \
  --host "$HOST" \
  --jinja \
  --context-shift \
  --metrics \
  --no-mmap 2>&1 | tee -a "$LOG_FILE"
EXIT_CODE=${PIPESTATUS[0]}
set -e

echo
if [[ $EXIT_CODE -eq 0 ]]; then
    echo "[Gillsystems] Server exited cleanly."
elif [[ $EXIT_CODE -eq 130 ]]; then
    echo "[Gillsystems] Server cancelled by user."
else
    echo "[Gillsystems] ERROR: Server exited with code $EXIT_CODE"
    echo "[Gillsystems] Review log: $LOG_FILE"
fi
