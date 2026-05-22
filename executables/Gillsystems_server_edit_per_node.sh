#!/usr/bin/env bash
# ============================================================
# Gillsystems Editable Server Launcher (Linux)
# Edit the values below for each node before production use.
#
# Note: Gemma 4 MTP flags are intentionally omitted for now.
# Current upstream GGUF conversion does not emit Gemma MTP layers,
# so forcing draft-mtp will fail model load.
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

resolve_node_name() {
    local candidate=""

    if [[ -n "${GILLSYSTEMS_NODE_NAME:-}" ]]; then
        candidate="$GILLSYSTEMS_NODE_NAME"
    elif [[ -n "${HOSTNAME:-}" ]]; then
        candidate="$HOSTNAME"
    elif command -v hostname >/dev/null 2>&1; then
        candidate="$(hostname 2>/dev/null || true)"
    elif [[ -x /usr/bin/hostname ]]; then
        candidate="$(/usr/bin/hostname 2>/dev/null || true)"
    elif [[ -r /etc/hostname ]]; then
        candidate="$(tr -d '[:space:]' < /etc/hostname)"
    elif command -v uname >/dev/null 2>&1; then
        candidate="$(uname -n 2>/dev/null || true)"
    elif [[ -x /usr/bin/uname ]]; then
        candidate="$(/usr/bin/uname -n 2>/dev/null || true)"
    fi

    if [[ -z "$candidate" ]]; then
        candidate="unknown-node"
    fi

    printf '%s\n' "$candidate"
}

LLAMA_BIN_DIR="/opt/gillsystems/llama.cpp/bin"
MODEL_PATH="/models/gemma-4-31B.Q4_K_M.gguf"
HOST="0.0.0.0"
PORT="8010"
CTX_SIZE="102400"
GPU_LAYERS="99"
PARALLEL_REQUESTS="1"
FLASH_ATTN="on"
CACHE_TYPE_K="q4_0"
CACHE_TYPE_V="q4_0"

SERVER_EXE="$LLAMA_BIN_DIR/llama-server"
TENSILE_LIBPATH="$LLAMA_BIN_DIR/rocblas/library"
LOG_DIR="$SCRIPT_DIR/logs"

mkdir -p "$LOG_DIR"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
NODE_NAME="$(resolve_node_name)"
LOG_FILE="$LOG_DIR/server_${NODE_NAME}_${TIMESTAMP}.log"

echo "Starting Gillsystems server launcher..."
echo "Model: $MODEL_PATH"
echo "Log:   $LOG_FILE"
echo

if [[ "${1:-}" == "--dry-run" ]]; then
    echo "Dry run only. Command would launch llama-server with the configuration above."
    exit 0
fi

if [[ ! -x "$SERVER_EXE" ]]; then
    echo "[Gillsystems] ERROR: llama-server not found at $SERVER_EXE"
    exit 1
fi

if [[ ! -f "$MODEL_PATH" ]]; then
    echo "[Gillsystems] ERROR: Model not found at $MODEL_PATH"
    exit 1
fi

if [[ -d "$TENSILE_LIBPATH" ]]; then
    export ROCBLAS_TENSILE_LIBPATH="$TENSILE_LIBPATH"
fi

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
  --cache-type-k "$CACHE_TYPE_K" \
  --cache-type-v "$CACHE_TYPE_V" \
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

exit $EXIT_CODE