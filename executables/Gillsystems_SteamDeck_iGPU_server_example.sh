#!/usr/bin/env bash
# ============================================================
# Gillsystems Steam Deck iGPU Server Launcher (Linux / Tier 2)
# Dedicated second-set example launcher for the Steam Deck node.
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

MODEL_PATH="/home/deck/Desktop/Models/gemma-4-E4B.Q6_K.gguf"
HOST="10.0.0.139"
PORT="8012"
CTX_SIZE="49152"
GPU_LAYERS="99"
PARALLEL_REQUESTS="1"
FLASH_ATTN="on"
TEMPERATURE="0.20"
TOP_K="20"
MIN_P="0.05"
LOG_DIR="$SCRIPT_DIR/../logs"

SERVER_EXE=""
for candidate in \
  "/home/deck/src/llama.cpp/bin/llama-server" \
  "/home/deck/src/llama.cpp/build-hip/bin/llama-server" \
  "/opt/gillsystems/llama.cpp/bin/llama-server"; do
    if [[ -z "$SERVER_EXE" && -x "$candidate" ]]; then
        SERVER_EXE="$candidate"
    fi
done

mkdir -p "$LOG_DIR"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
NODE_NAME="$(resolve_node_name)"
LOG_FILE="$LOG_DIR/server_${NODE_NAME}_${TIMESTAMP}.log"

echo "Starting Gillsystems Steam Deck iGPU example server..."
echo "Model: $MODEL_PATH"
echo "Log:   $LOG_FILE"
echo

if [[ "${1:-}" == "--dry-run" ]]; then
    echo "Dry run only. Command would launch the Steam Deck / Tier 2 server configuration above."
    exit 0
fi

if [[ -z "$SERVER_EXE" ]]; then
    echo "[Gillsystems] ERROR: llama-server was not found in any expected Steam Deck path."
    echo "[Gillsystems] Checked: /home/deck/src/llama.cpp/bin, /home/deck/src/llama.cpp/build-hip/bin, /opt/gillsystems/llama.cpp/bin"
    exit 1
fi

if [[ ! -f "$MODEL_PATH" ]]; then
    echo "[Gillsystems] ERROR: Model not found at $MODEL_PATH"
    exit 1
fi

LLAMA_BIN_DIR="$(dirname "$SERVER_EXE")"
TENSILE_LIBPATH="$LLAMA_BIN_DIR/rocblas/library"

if [[ -d "$TENSILE_LIBPATH" ]]; then
    export ROCBLAS_TENSILE_LIBPATH="$TENSILE_LIBPATH"
fi

echo "Executable: $SERVER_EXE"

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
  --temperature "$TEMPERATURE" \
  --top-k "$TOP_K" \
  --min-p "$MIN_P" \
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