#!/usr/bin/env bash
# ============================================================
# Gillsystems Steam Deck AI Server Launcher (Linux / Vulkan Backend)
# Round 4 Stabilized Profile - 32K Context Bounded Runtime
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

MODEL_FILENAME="gemma-4-E4B.Q6_K.gguf"
MODEL_PATH="${GILLSYSTEMS_STEAMDECK_MODEL_PATH:-}"

if [[ -z "$MODEL_PATH" ]]; then
  for candidate in \
    "/home/deck/Desktop/Models/$MODEL_FILENAME" \
    "/home/deck/Desktop/Models/Working_Models/$MODEL_FILENAME" \
    "/gillsystems_zfs_pool/AI_storage/Models/$MODEL_FILENAME"; do
    if [[ -z "$MODEL_PATH" && -f "$candidate" ]]; then
      MODEL_PATH="$candidate"
    fi
  done
fi

if [[ -z "$MODEL_PATH" ]]; then
  MODEL_PATH="/home/deck/Desktop/Models/$MODEL_FILENAME"
fi

HOST="10.0.0.139"
PORT="8013"
CTX_SIZE="32768"
N_PREDICT="1024"
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

SERVER_EXE=""
LLAMA_LIB_DIR=""
for candidate in \
  "/home/deck/src/llama.cpp/bin/llama-server|/home/deck/src/llama.cpp/build-vulkan/bin" \
  "/home/deck/src/llama.cpp/build-vulkan/bin/llama-server|/home/deck/src/llama.cpp/build-vulkan/bin" \
  "/opt/gillsystems/llama.cpp/bin/llama-server|/opt/gillsystems/llama.cpp/lib"; do
    IFS='|' read -r exe_path lib_path <<<"$candidate"
    if [[ -z "$SERVER_EXE" && -x "$exe_path" ]]; then
        SERVER_EXE="$exe_path"
        LLAMA_LIB_DIR="$lib_path"
    fi
done

if [[ -z "$SERVER_EXE" ]]; then
    SERVER_EXE="/home/deck/src/llama.cpp/bin/llama-server"
fi

if [[ -z "$LLAMA_LIB_DIR" ]]; then
    LLAMA_LIB_DIR="/home/deck/src/llama.cpp/build-vulkan/bin"
fi

LOG_DIR="$SCRIPT_DIR/../logs"
mkdir -p "$LOG_DIR"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="$LOG_DIR/server_deck_${TIMESTAMP}.log"

echo "Starting Steam Deck AI Server..."
echo "Model:   $MODEL_PATH"
echo "Host:    $HOST:$PORT"
echo "Context: $CTX_SIZE"
echo "Binary:  $SERVER_EXE"
echo "Lib dir: $LLAMA_LIB_DIR"
echo "Log:     $LOG_FILE"
echo

if [[ "${1:-}" == "--dry-run" ]]; then
  [[ -x "$SERVER_EXE" ]] || echo "[Gillsystems] WARN: Binary not found at $SERVER_EXE"
  [[ -f "$MODEL_PATH" ]] || echo "[Gillsystems] WARN: Model not found at $MODEL_PATH"
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
  echo "[Gillsystems] Set GILLSYSTEMS_STEAMDECK_MODEL_PATH to override the detected model path."
    exit 1
fi

export LD_LIBRARY_PATH="$LLAMA_LIB_DIR:${LD_LIBRARY_PATH:-}"

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

exit $EXIT_CODE