#!/usr/bin/env bash
# ============================================================
# Gillsystems AI Stack Updater — Linux Launcher
# update-ai-stack.sh
#
# Thin launcher that resolves the repo root and hands off to
# bootstrap-linux.sh for Python setup, logging, and sudo flow.
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

SCRIPT_PATH="$(resolve_script_path "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
BOOTSTRAP_PATH="$SCRIPT_DIR/bootstrap-linux.sh"

if [[ ! -f "$SCRIPT_DIR/pyproject.toml" ]]; then
    echo "[Gillsystems AI Stack Updater] ERROR: Could not find project root."
    echo "  Run this script from inside the Gillsystems-update-ai-engine-software repo."
    echo "  Launcher path: $SCRIPT_PATH"
    echo "  Resolved repo dir: $SCRIPT_DIR"
    exit 1
fi

if [[ ! -f "$BOOTSTRAP_PATH" ]]; then
    echo "[Gillsystems AI Stack Updater] ERROR: Missing Linux bootstrap: $BOOTSTRAP_PATH"
    exit 1
fi

if [[ -w "$SCRIPT_PATH" ]]; then
    chmod +x "$SCRIPT_PATH" >/dev/null 2>&1 || true
fi
if [[ -w "$BOOTSTRAP_PATH" ]]; then
    chmod +x "$BOOTSTRAP_PATH" >/dev/null 2>&1 || true
fi

exec /usr/bin/env bash "$BOOTSTRAP_PATH" "$@"
