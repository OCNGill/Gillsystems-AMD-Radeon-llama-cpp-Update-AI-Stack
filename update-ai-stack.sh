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
if [[ -L "$0" ]] && command -v readlink &>/dev/null; then
    REAL_PATH="$(readlink -f "$0" 2>/dev/null || echo "")"
    if [[ -n "$REAL_PATH" ]]; then
        SCRIPT_DIR="$(cd "$(dirname "$REAL_PATH")" && pwd)"
    fi
fi

# -----------------------------------------------------------
# Repo structure self-check — don't proceed if broken
# -----------------------------------------------------------
if [[ ! -f "$SCRIPT_DIR/pyproject.toml" ]]; then
    echo "[Gillsystems AI Stack Updater] ERROR: Could not find project root."
    echo "  Run this script from the Gillsystems-update-ai-engine-software directory."
    echo "  Current SCRIPT_DIR=$SCRIPT_DIR"
    exit 1
fi

# -----------------------------------------------------------
# Fast help / env-check mode
# -----------------------------------------------------------
if [[ "$#" -gt 0 ]]; then
    case "$1" in
        --help|-h|--check-env)
            echo "Gillsystems AI Stack Updater — Linux Launcher"
            echo ""
            echo "Usage:  ./update-ai-stack.sh [--dry-run] [--force] [--resume] [--verbose]"
            echo "        ./update-ai-stack.sh --check-env  (validate environment only)"
            echo "        ./update-ai-stack.sh --help       (this message)"
            echo ""
            if [[ "$1" == "--check-env" ]]; then
                echo "[Gillsystems AI Stack Updater] Checking environment..."
                echo "  SCRIPT_DIR=$SCRIPT_DIR"
                echo "  $(python3 --version 2>&1 || echo 'python3 not found')"
                echo "  $(python3.12 --version 2>&1 || echo 'python3.12 not found')"
                echo "  $(python3.11 --version 2>&1 || echo 'python3.11 not found')"
                if command -v sudo &>/dev/null; then echo "  sudo: available"; else echo "  sudo: MISSING"; fi
                if [[ -d .venv ]]; then echo "  .venv: exists"; else echo "  .venv: not yet created"; fi
                echo "  pyproject.toml: $([[ -f pyproject.toml ]] && echo 'found' || echo 'MISSING')"
                echo "  requirements.txt: $([[ -f requirements.txt ]] && echo 'found' || echo 'MISSING')"
            fi
            exit 0
            ;;
    esac
fi

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

VENV_DIR="$SCRIPT_DIR/.venv"

# python3-venv check — required for venv creation on Debian/Kubuntu
if ! "$PYTHON_BIN" -c "import venv" &>/dev/null; then
    echo "[Gillsystems AI Stack Updater] ERROR: python3-venv is required."
    echo "  Kubuntu/Debian: sudo apt install python3-venv"
    echo "  Fedora:         sudo dnf install python3-virtualenv"
    exit 1
fi

# PEP 668 guard: Kubuntu 24.04+ / Debian 12+ mark system Python as
# externally-managed. Auto-create a project venv to avoid the pip block.
VENV_FRESH=false
if [[ ! -d "$VENV_DIR" ]]; then
    echo "[Gillsystems AI Stack Updater] Creating virtual environment..."
    "$PYTHON_BIN" -m venv "$VENV_DIR"
    VENV_FRESH=true
fi

# Activate venv
PYTHON_BIN="$VENV_DIR/bin/python"
PIP_BIN="$VENV_DIR/bin/pip"

if $VENV_FRESH || [[ "requirements.txt" -nt "$VENV_DIR/.deps_installed" ]]; then
    echo "[Gillsystems AI Stack Updater] Installing Python dependencies..."
    "$PIP_BIN" install --quiet -r requirements.txt
    touch "$VENV_DIR/.deps_installed"
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
