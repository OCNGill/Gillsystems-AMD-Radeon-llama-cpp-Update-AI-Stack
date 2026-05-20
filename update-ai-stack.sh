#!/usr/bin/env bash
# ============================================================
# Gillsystems AI Stack Updater — Linux Launcher
# update-ai-stack.sh
#
# Requests sudo if needed, checks Python 3.11+, installs
# dependencies, then invokes the Python agent.
# All CLI arguments are forwarded to main.py.
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# -----------------------------------------------------------
# Privilege check — re-execute with sudo if not root
# -----------------------------------------------------------
if [[ $EUID -ne 0 ]]; then
    echo "[Gillsystems AI Stack Updater] Requesting sudo privileges..."
    exec sudo -E bash "$0" "$@"
fi

# -----------------------------------------------------------
# Python version check
# -----------------------------------------------------------
PYTHON_BIN=""
for candidate in python3.12 python3.11 python3 python; do
    if command -v "$candidate" &>/dev/null; then
        version=$("$candidate" -c "import sys; print(sys.version_info >= (3,11))" 2>/dev/null || echo "False")
        if [[ "$version" == "True" ]]; then
            PYTHON_BIN="$candidate"
            break
        fi
    fi
done

if [[ -z "$PYTHON_BIN" ]]; then
    echo "[Gillsystems AI Stack Updater] ERROR: Python 3.11+ is required but not found."
    echo "  Ubuntu/Debian: sudo apt install python3.11"
    echo "  Fedora/RHEL:   sudo dnf install python3.11"
    exit 1
fi

echo "[Gillsystems AI Stack Updater] Using Python: $($PYTHON_BIN --version)"

# -----------------------------------------------------------
# Install dependencies (once or when requirements change)
# -----------------------------------------------------------
cd "$SCRIPT_DIR"

DEPS_MARKER=".deps_installed"
if [[ ! -f "$DEPS_MARKER" ]] || [[ "requirements.txt" -nt "$DEPS_MARKER" ]]; then
    echo "[Gillsystems AI Stack Updater] Installing Python dependencies..."
    "$PYTHON_BIN" -m pip install --quiet -r requirements.txt
    touch "$DEPS_MARKER"
fi

# -----------------------------------------------------------
# Run the agent — pass all args through and tee output to logs/
# -----------------------------------------------------------
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"

NODE_NAME="$(hostname)"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="$LOG_DIR/run_${NODE_NAME}_${TIMESTAMP}.log"

echo ""
echo "[Gillsystems AI Stack Updater] Logging to: $LOG_FILE"
echo ""

set +e
"$PYTHON_BIN" -u -m src.main "$@" 2>&1 | tee -a "$LOG_FILE"
EXIT_CODE=${PIPESTATUS[0]}
set -e

echo ""
if [[ $EXIT_CODE -eq 0 ]]; then
    echo "[Gillsystems AI Stack Updater] Completed successfully."
elif [[ $EXIT_CODE -eq 130 ]]; then
    echo "[Gillsystems AI Stack Updater] Cancelled by user."
else
    echo "[Gillsystems AI Stack Updater] ERROR: Exit code $EXIT_CODE"
    echo "[Gillsystems AI Stack Updater] Review log: $LOG_FILE"
fi

exit $EXIT_CODE
