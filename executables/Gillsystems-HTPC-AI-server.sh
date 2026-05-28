#!/usr/bin/env bash
# ============================================================
# Gillsystems HTPC Server Launcher (Linux / Dedicated RX 7600)
# Round 4 Stabilized Profile - 32K Context Bounded Runtime
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

MODEL_FILENAME="gemma-4-E4B.Q6_K.gguf"
MODEL_PATH="${GILLSYSTEMS_HTPC_MODEL_PATH:-}"

if [[ -z "$MODEL_PATH" ]]; then
    for candidate in \
        "/home/gillsystems-htpc/Desktop/Models/$MODEL_FILENAME" \
        "/home/gillsystems-htpc/Desktop/Models/Working_Models/$MODEL_FILENAME" \
        "/gillsystems_zfs_pool/AI_storage/Models/$MODEL_FILENAME"; do
        if [[ -z "$MODEL_PATH" && -f "$candidate" ]]; then
            MODEL_PATH="$candidate"
        fi
    done
fi

if [[ -z "$MODEL_PATH" ]]; then
    MODEL_PATH="/home/gillsystems-htpc/Desktop/Models/$MODEL_FILENAME"
fi

HOST="10.0.0.42"
PORT="8011"
CTX_SIZE="32768"
N_PREDICT="1536"
BATCH_SIZE="2048"
UBATCH_SIZE="512"
GPU_LAYERS="99"  
PARALLEL_REQUESTS="1"
FLASH_ATTN="on"
CHAT_TEMPLATE="gemma"

# Deterministic Google-tuned baseline
TEMPERATURE="0"
MIN_P="0.05"
TOP_K="20"
TOP_P="1.0"
REPEAT_PENALTY="1.15"
REPEAT_LAST_N="128"

LOG_DIR="$SCRIPT_DIR/../logs"

SERVER_EXE=""
LLAMA_LIB_DIR=""
for candidate in \
    "/opt/gillsystems/llama.cpp/bin/llama-server|/opt/gillsystems/llama.cpp/lib" \
    "/home/gillsystems-htpc/src/llama.cpp/bin/llama-server|/home/gillsystems-htpc/src/llama.cpp/build-hip/bin" \
    "/home/gillsystems-htpc/src/llama.cpp/build-hip/bin/llama-server|/home/gillsystems-htpc/src/llama.cpp/build-hip/bin"; do
        IFS='|' read -r exe_path lib_path <<<"$candidate"
        if [[ -z "$SERVER_EXE" && -x "$exe_path" ]]; then
                SERVER_EXE="$exe_path"
                LLAMA_LIB_DIR="$lib_path"
        fi
done

mkdir -p "$LOG_DIR"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
NODE_NAME="$(resolve_node_name)"
LOG_FILE="$LOG_DIR/server_${NODE_NAME}_${TIMESTAMP}.log"

echo "Starting Gillsystems HTPC LLM Server... (Dedicated HIP Core)"
echo "Model:   $MODEL_PATH"
echo "Host:    $HOST:$PORT"
echo "Context: $CTX_SIZE"
echo "Log:     $LOG_FILE"
echo

if [[ "${1:-}" == "--dry-run" ]]; then
    [[ -x "$SERVER_EXE" ]] || echo "[Gillsystems] WARN: llama-server executable not found at $SERVER_EXE"
    [[ -f "$MODEL_PATH" ]] || echo "[Gillsystems] WARN: Model not found at $MODEL_PATH"
    echo "Dry run only. Command would launch the HTPC server configuration above."
    exit 0
fi

if [[ -z "$SERVER_EXE" ]]; then
    echo "[Gillsystems] ERROR: llama-server executable was not found."
    exit 1
fi

if [[ ! -f "$MODEL_PATH" ]]; then
    echo "[Gillsystems] ERROR: Model not found at $MODEL_PATH"
    echo "[Gillsystems] Set GILLSYSTEMS_HTPC_MODEL_PATH to override the detected model path."
    exit 1
fi

LLAMA_BIN_DIR="$(dirname "$SERVER_EXE")"
ROCBLAS_TENSILE_DIR=""
for candidate in \
  "$LLAMA_BIN_DIR/rocblas/library" \
  "/opt/gillsystems/llama.cpp/bin/rocblas/library" \
  "/opt/rocm/lib/rocblas/library"; do
    if [[ -z "$ROCBLAS_TENSILE_DIR" && -d "$candidate" ]]; then
        ROCBLAS_TENSILE_DIR="$candidate"
    fi
done

if [[ -d "$LLAMA_LIB_DIR" ]]; then
    export LD_LIBRARY_PATH="$LLAMA_LIB_DIR:${LD_LIBRARY_PATH:-}"
fi

if [[ -n "$ROCBLAS_TENSILE_DIR" ]]; then
    export ROCBLAS_TENSILE_LIBPATH="$ROCBLAS_TENSILE_DIR"
fi

echo "Executable: $SERVER_EXE"
echo "LD_LIBRARY_PATH: ${LD_LIBRARY_PATH:-}"
echo "ROCBLAS_TENSILE_LIBPATH: ${ROCBLAS_TENSILE_LIBPATH:-}"
echo "[Gillsystems] Terminating any existing llama-server instances..."
pkill -f llama-server >/dev/null 2>&1 || true
sleep 2
pkill -9 -f llama-server >/dev/null 2>&1 || true
echo "[Gillsystems] Waiting for Linux to release VRAM allocations..."
sleep 2

set +e
"$SERVER_EXE" \
  -m "$MODEL_PATH" \
  -c "$CTX_SIZE" \
    -n "$N_PREDICT" \
  -ngl "$GPU_LAYERS" \
  -fa "$FLASH_ATTN" \
  -np "$PARALLEL_REQUESTS" \
  -b "$BATCH_SIZE" \
  -ub "$UBATCH_SIZE" \
  --port "$PORT" \
  --host "$HOST" \
  --jinja \
    --chat-template "$CHAT_TEMPLATE" \
  --context-shift \
  --temperature "$TEMPERATURE" \
    --min-p "$MIN_P" \
  --top-k "$TOP_K" \
    --top-p "$TOP_P" \
    --repeat-penalty "$REPEAT_PENALTY" \
    --repeat-last-n "$REPEAT_LAST_N" \
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