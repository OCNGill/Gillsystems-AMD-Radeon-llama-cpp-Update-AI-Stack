#!/usr/bin/env bash
# ============================================================
# Gillsystems AI Stack Updater — Linux Bootstrap
# bootstrap-linux.sh
#
# Handles Python discovery, virtualenv management, a single sudo
# prompt with keep-alive, and repo-local logging before launching
# the Python agent.
# ============================================================

set -euo pipefail

resolve_script_path() {
    local source_path="$1"

    if command -v readlink >/dev/null 2>&1; then
        while [[ -L "$source_path" ]]; do
            local source_dir
            source_dir="$(cd "$(dirname "$source_path")" && pwd)"
            source_path="$(readlink "$source_path")"
            if [[ "$source_path" != /* ]]; then
                source_path="$source_dir/$source_path"
            fi
        done
    fi

    printf '%s\n' "$(cd "$(dirname "$source_path")" && pwd)/$(basename "$source_path")"
}

arg_present() {
    local expected="$1"
    shift

    local arg
    for arg in "$@"; do
        if [[ "$arg" == "$expected" ]]; then
            return 0
        fi
    done
    return 1
}

lookup_home_dir() {
    local user_name="$1"

    if [[ -z "$user_name" ]]; then
        return 0
    fi

    if command -v getent >/dev/null 2>&1; then
        getent passwd "$user_name" | awk -F: '{print $6}'
        return 0
    fi

    if [[ -r /etc/passwd ]]; then
        awk -F: -v user="$user_name" '$1 == user { print $6 }' /etc/passwd
    fi
}

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

SCRIPT_PATH="$(resolve_script_path "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
LAUNCHER_PATH="$SCRIPT_DIR/update-ai-stack.sh"
VENV_DIR="$SCRIPT_DIR/.venv"
LOG_DIR="$SCRIPT_DIR/logs"
STATE_DIR="$SCRIPT_DIR/state"
PYTHON_BIN=""
PIP_BIN=""
SUDO_KEEPALIVE_PID=""

IS_HELP=0
IS_CHECK_ENV=0
IS_DRY_RUN=0
if arg_present "--help" "$@" || arg_present "-h" "$@"; then
    IS_HELP=1
fi
if arg_present "--check-env" "$@"; then
    IS_CHECK_ENV=1
fi
if arg_present "--dry-run" "$@"; then
    IS_DRY_RUN=1
fi

REPO_OWNER="${GILLSYSTEMS_REPO_OWNER:-}"
if [[ -z "$REPO_OWNER" ]]; then
    if [[ $EUID -eq 0 && -n "${SUDO_USER:-}" ]]; then
        REPO_OWNER="$SUDO_USER"
    else
        REPO_OWNER="$(id -un 2>/dev/null || echo "")"
    fi
fi

REPO_OWNER_HOME="${GILLSYSTEMS_REPO_OWNER_HOME:-}"
if [[ -z "$REPO_OWNER_HOME" ]]; then
    REPO_OWNER_HOME="$(lookup_home_dir "$REPO_OWNER")"
fi
if [[ -z "$REPO_OWNER_HOME" ]]; then
    REPO_OWNER_HOME="$HOME"
fi

export GILLSYSTEMS_REPO_OWNER="$REPO_OWNER"
export GILLSYSTEMS_REPO_OWNER_HOME="$REPO_OWNER_HOME"
export GILLSYSTEMS_REPO_ROOT="$SCRIPT_DIR"
export PIP_DISABLE_PIP_VERSION_CHECK=1
export PIP_NO_CACHE_DIR=1
export PYTHONUTF8=1

is_steamos() {
    if [[ -f /etc/os-release ]] && grep -qi "steamos" /etc/os-release; then
        return 0
    fi
    return 1
}

if [[ $EUID -eq 0 && -n "$REPO_OWNER_HOME" ]]; then
    export HOME="$REPO_OWNER_HOME"
fi

print_profile_warning() {
    echo ""
    echo "[Gillsystems AI Stack Updater] Linux launcher warning:"
    echo "  If Konsole or SteamOS says:"
    echo "    Warning: Could not find '$LAUNCHER_PATH', starting '/bin/bash' instead."
    echo "  then either the repo path changed OR the execute bit was stripped."
    echo "  Safe profile command:"
    echo "    /bin/bash \"$LAUNCHER_PATH\""
    echo ""
}

ensure_launcher_mode() {
    local repaired=0
    local candidate

    for candidate in "$LAUNCHER_PATH" "$SCRIPT_PATH"; do
        if [[ -f "$candidate" && ! -x "$candidate" && -w "$candidate" ]]; then
            chmod +x "$candidate" >/dev/null 2>&1 || true
            repaired=1
        fi
    done

    if [[ $repaired -eq 1 ]]; then
        echo "[Gillsystems AI Stack Updater] Repaired Linux launcher execute bit(s)."
    fi
}

show_usage() {
    echo "Gillsystems AI Stack Updater — Linux Launcher"
    echo ""
    echo "Usage:  ./update-ai-stack.sh [--dry-run] [--force] [--resume] [--verbose]"
    echo "        ./update-ai-stack.sh --check-env  (validate environment only)"
    echo "        ./update-ai-stack.sh --help       (this message)"
    echo ""
    echo "Linux live runs request sudo once, keep it warm for the run, and keep"
    echo "the Python venv/log management in user space so Kubuntu and Steam Deck"
    echo "do not get stuck with root-owned runtime files."
    print_profile_warning
}

show_environment() {
    echo "[Gillsystems AI Stack Updater] Checking environment..."
    echo "  SCRIPT_DIR=$SCRIPT_DIR"
    echo "  LAUNCHER_PATH=$LAUNCHER_PATH"
    echo "  BOOTSTRAP_PATH=$SCRIPT_PATH"
    echo "  launcher executable: $([[ -x "$LAUNCHER_PATH" ]] && echo 'yes' || echo 'NO')"
    echo "  bootstrap executable: $([[ -x "$SCRIPT_PATH" ]] && echo 'yes' || echo 'no (bash invocation is fine)')"
    echo "  repo owner: ${REPO_OWNER:-unknown}"
    echo "  repo owner home: ${REPO_OWNER_HOME:-unknown}"
    echo "  current user: $(id -un 2>/dev/null || echo 'unknown')"
    echo "  $(python3 --version 2>&1 || echo 'python3 not found')"
    echo "  $(python3.12 --version 2>&1 || echo 'python3.12 not found')"
    echo "  $(python3.11 --version 2>&1 || echo 'python3.11 not found')"
    if command -v sudo >/dev/null 2>&1; then
        echo "  sudo: available"
    else
        echo "  sudo: MISSING"
    fi
    if [[ -d "$VENV_DIR" ]]; then
        echo "  .venv: exists"
    else
        echo "  .venv: not yet created"
    fi
    echo "  pyproject.toml: $([[ -f "$SCRIPT_DIR/pyproject.toml" ]] && echo 'found' || echo 'MISSING')"
    echo "  requirements.txt: $([[ -f "$SCRIPT_DIR/requirements.txt" ]] && echo 'found' || echo 'MISSING')"

    if [[ ! -x "$LAUNCHER_PATH" ]]; then
        echo ""
        echo "  WARNING: update-ai-stack.sh is not executable."
        echo "  Direct Konsole profile launches will fail until the execute bit is restored."
    fi

    print_profile_warning
}

ensure_sudo_session() {
    if [[ $IS_DRY_RUN -eq 1 || $IS_HELP -eq 1 || $IS_CHECK_ENV -eq 1 || $EUID -eq 0 ]]; then
        return
    fi

    if [[ "${GILLSYSTEMS_SUDO_NONINTERACTIVE:-}" == "1" ]] && sudo -n -v >/dev/null 2>&1; then
        return
    fi

    if ! command -v sudo >/dev/null 2>&1; then
        echo "[Gillsystems AI Stack Updater] ERROR: sudo is required for live Linux runs."
        echo "  Install sudo or run the updater from a root shell."
        exit 1
    fi

    echo "[Gillsystems AI Stack Updater] Administrator privileges are required for ROCm installs, /opt deployment, and systemd resume registration."
    echo "[Gillsystems AI Stack Updater] Requesting sudo once; it will stay warm for the rest of this run."
    if ! sudo -v; then
        echo "[Gillsystems AI Stack Updater] ERROR: sudo authentication failed."
        exit 1
    fi

    export GILLSYSTEMS_SUDO_NONINTERACTIVE=1

    if is_steamos; then
        echo "[Gillsystems AI Stack Updater] SteamOS detected. Unlocking read-only filesystem globally for this run..."
        if sudo -n steamos-readonly disable; then
            export STEAMOS_UNLOCKED=1
        else
            echo "[Gillsystems AI Stack Updater] WARNING: Failed to unlock SteamOS filesystem."
        fi
    fi

    if [[ -z "$SUDO_KEEPALIVE_PID" ]]; then
        (
            while true; do
                sudo -n -v >/dev/null 2>&1 || exit
                sleep 30
            done
        ) &
        SUDO_KEEPALIVE_PID=$!
    fi
}

repair_runtime_permissions() {
    if [[ $EUID -eq 0 ]]; then
        return
    fi

    local repair_targets=()
    local candidate
    for candidate in "$VENV_DIR" "$LOG_DIR" "$STATE_DIR"; do
        if [[ -e "$candidate" && ! -w "$candidate" ]]; then
            repair_targets+=("$candidate")
        fi
    done

    if [[ ${#repair_targets[@]} -eq 0 ]]; then
        return
    fi

    if [[ $IS_DRY_RUN -eq 1 ]]; then
        echo "[Gillsystems AI Stack Updater] WARNING: runtime paths are not writable in dry-run mode: ${repair_targets[*]}"
        return
    fi

    ensure_sudo_session

    local owner_group
    owner_group="$(id -gn "$REPO_OWNER" 2>/dev/null || id -gn)"

    echo "[Gillsystems AI Stack Updater] Repairing root-owned runtime paths from an earlier all-sudo Linux run..."
    sudo -n chown -R "$REPO_OWNER:$owner_group" "${repair_targets[@]}"
}

resolve_llama_source_dir() {
    if [[ -z "$PYTHON_BIN" || ! -x "$PYTHON_BIN" ]]; then
        return 0
    fi

    HOME="$REPO_OWNER_HOME" "$PYTHON_BIN" - <<'PY' 2>/dev/null || true
from pathlib import Path
from src.config import load_config

cfg = load_config()
print(Path(cfg.paths.llama_cpp_source).expanduser())
PY
}

restore_user_owned_paths() {
    if [[ $EUID -ne 0 ]]; then
        return
    fi

    if [[ -z "$REPO_OWNER" || "$REPO_OWNER" == "root" ]]; then
        return
    fi

    local owner_group
    owner_group="$(id -gn "$REPO_OWNER" 2>/dev/null || echo "$REPO_OWNER")"
    local llama_source_dir
    llama_source_dir="$(resolve_llama_source_dir)"
    local restore_targets=("$SCRIPT_DIR")

    if [[ -n "$llama_source_dir" ]]; then
        restore_targets+=("$llama_source_dir")
    fi

    local target
    for target in "${restore_targets[@]}"; do
        if [[ -e "$target" ]]; then
            chown -R "$REPO_OWNER:$owner_group" "$target" >/dev/null 2>&1 || true
        fi
    done
}

cleanup() {
    local exit_code=$?

    if [[ -n "$SUDO_KEEPALIVE_PID" ]]; then
        kill "$SUDO_KEEPALIVE_PID" >/dev/null 2>&1 || true
        wait "$SUDO_KEEPALIVE_PID" 2>/dev/null || true
    fi

    # Restore file ownership BEFORE re-locking the filesystem.
    # Privileged build steps may leave root-owned artifacts in the repo directory;
    # chowning them back here prevents permission errors on subsequent runs.
    if [[ $EUID -eq 0 ]]; then
        restore_user_owned_paths || true
    elif [[ -n "${REPO_OWNER:-}" && "${REPO_OWNER}" != "root" ]]; then
        local owner_group
        owner_group="$(id -gn "$REPO_OWNER" 2>/dev/null || id -gn)"
        sudo -n chown -R "$REPO_OWNER:$owner_group" "$SCRIPT_DIR" >/dev/null 2>&1 || true
    fi

    # Re-lock LAST — after all writes are done.
    if [[ "${STEAMOS_UNLOCKED:-0}" -eq 1 ]]; then
        echo "[Gillsystems AI Stack Updater] Re-locking SteamOS filesystem..."
        if ! sudo -n steamos-readonly enable >/dev/null 2>&1; then
            echo "[Gillsystems AI Stack Updater] WARNING: Failed to re-lock SteamOS. Run manually: sudo steamos-readonly enable"
        fi
    fi

    exit "$exit_code"
}

trap cleanup EXIT

ensure_launcher_mode

if [[ ! -f "$SCRIPT_DIR/pyproject.toml" ]]; then
    echo "[Gillsystems AI Stack Updater] ERROR: Could not find project root."
    echo "  Run this script from inside the Gillsystems-update-ai-engine-software repo."
    echo "  Current SCRIPT_DIR=$SCRIPT_DIR"
    exit 1
fi

if [[ $IS_HELP -eq 1 ]]; then
    show_usage
    if [[ $IS_CHECK_ENV -eq 0 ]]; then
        exit 0
    fi
fi

if [[ $IS_CHECK_ENV -eq 1 ]]; then
    show_environment
    exit 0
fi

cd "$SCRIPT_DIR"
repair_runtime_permissions
ensure_sudo_session

for candidate in python3.12 python3.11 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        version_ok="$("$candidate" -c "import sys; print(sys.version_info >= (3,11))" 2>/dev/null || echo "False")"
        if [[ "$version_ok" == "True" ]]; then
            PYTHON_BIN="$candidate"
            break
        fi
    fi
done

if [[ -z "$PYTHON_BIN" ]]; then
    echo "[Gillsystems AI Stack Updater] ERROR: Python 3.11+ is required but not found."
    echo "  Ubuntu/Debian: sudo apt install python3.11 python3-venv"
    echo "  SteamOS:       sudo pacman -S python"
    exit 1
fi

echo "[Gillsystems AI Stack Updater] Using Python: $($PYTHON_BIN --version)"

if ! "$PYTHON_BIN" -c "import venv" >/dev/null 2>&1; then
    echo "[Gillsystems AI Stack Updater] ERROR: python3-venv is required."
    echo "  Kubuntu/Debian: sudo apt install python3-venv"
    echo "  SteamOS:        python ships with venv in the main package"
    exit 1
fi

VENV_FRESH=false
if [[ ! -d "$VENV_DIR" ]]; then
    echo "[Gillsystems AI Stack Updater] Creating virtual environment..."
    "$PYTHON_BIN" -m venv "$VENV_DIR"
    VENV_FRESH=true
fi

PYTHON_BIN="$VENV_DIR/bin/python"
PIP_BIN="$VENV_DIR/bin/pip"

if [[ "$VENV_FRESH" == true || "$SCRIPT_DIR/requirements.txt" -nt "$VENV_DIR/.deps_installed" ]]; then
    echo "[Gillsystems AI Stack Updater] Installing Python dependencies..."
    "$PIP_BIN" install --quiet -r "$SCRIPT_DIR/requirements.txt"
    touch "$VENV_DIR/.deps_installed"
fi

mkdir -p "$LOG_DIR"

NODE_NAME="$(resolve_node_name)"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="$LOG_DIR/run_${NODE_NAME}_${TIMESTAMP}.log"

echo ""
echo "[Gillsystems AI Stack Updater] Logging to: $LOG_FILE"
echo ""

export GILLSYSTEMS_LINUX_BOOTSTRAP=1

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