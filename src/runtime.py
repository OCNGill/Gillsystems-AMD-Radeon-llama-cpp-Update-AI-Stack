from __future__ import annotations

import os
import platform as platform_lib
import re
import sys
from pathlib import Path

_RUNTIME_PLACEHOLDERS = ("platform", "distro", "node")


def _sanitize_runtime_token(value: str | None, fallback: str) -> str:
    candidate = (value or "").strip()
    if not candidate:
        return fallback

    normalized = re.sub(r"[^0-9A-Za-z._-]+", "-", candidate).strip("-._").lower()
    return normalized or fallback


def get_platform_id() -> str:
    if sys.platform == "win32":
        return "windows"
    if sys.platform.startswith("linux"):
        return "linux"
    return _sanitize_runtime_token(sys.platform, "unknown")


def get_linux_distro_id() -> str:
    if get_platform_id() != "linux":
        return get_platform_id()

    try:
        info = platform_lib.freedesktop_os_release()
        for key in ("ID", "ID_LIKE", "NAME"):
            raw_value = info.get(key, "")
            if raw_value:
                return _sanitize_runtime_token(raw_value.split()[0], "linux")
    except Exception:
        pass

    try:
        for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
            if line.startswith("ID="):
                raw_value = line.split("=", 1)[1].strip().strip('"')
                return _sanitize_runtime_token(raw_value.split()[0], "linux")
    except OSError:
        pass

    return "linux"


def get_node_id() -> str:
    for candidate in (
        os.environ.get("GILLSYSTEMS_NODE_NAME"),
        os.environ.get("COMPUTERNAME"),
        os.environ.get("HOSTNAME"),
        platform_lib.node(),
    ):
        if candidate:
            return _sanitize_runtime_token(candidate, "unknown-node")
    return "unknown-node"


def get_runtime_identity() -> dict[str, str]:
    platform_id = get_platform_id()
    distro_id = get_linux_distro_id() if platform_id == "linux" else platform_id
    return {
        "platform": platform_id,
        "distro": distro_id,
        "node": get_node_id(),
    }


def has_runtime_placeholders(path_value: str) -> bool:
    return any(f"{{{key}}}" in path_value for key in _RUNTIME_PLACEHOLDERS)


def resolve_runtime_path(path_value: str) -> Path:
    resolved = path_value
    for key, value in get_runtime_identity().items():
        resolved = resolved.replace(f"{{{key}}}", value)
    return Path(resolved).expanduser()