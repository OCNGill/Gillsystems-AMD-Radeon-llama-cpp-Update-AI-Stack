"""
privilege.py — Privilege handling for Gillsystems AI Stack Updater.

Linux:  validates a usable sudo session without re-executing the whole process
as root during normal interactive runs.
Windows: checks IsUserAnAdmin(), re-launches with ShellExecute runas if needed.
"""
from __future__ import annotations

import os
import sys
import subprocess
import logging
from typing import NoReturn

logger = logging.getLogger(__name__)


class PrivilegeError(RuntimeError):
    """Raised when privilege elevation is not possible."""


def is_admin() -> bool:
    """Return True if the current process is running with admin/root privileges."""
    if sys.platform == "win32":
        return _is_admin_windows()
    return os.geteuid() == 0  # type: ignore[attr-defined]


def ensure_admin() -> None:
    """
    Verify privilege prerequisites for the current platform.

    On Windows this opens a UAC prompt. On Linux it validates that sudo is
    available and, when needed, warms a sudo session instead of re-executing
    the entire Python process as root.
    """
    if sys.platform == "win32":
        if is_admin():
            logger.debug("Privilege check passed — running as admin/root.")
            return

        logger.info("Not running with elevated privileges. Requesting elevation...")
        _elevate_windows()
        return

    if is_admin():
        logger.debug("Privilege check passed — running as admin/root.")
        return

    logger.info("Linux live run detected without root. Validating sudo session...")
    _prepare_linux_sudo()


# ---------------------------------------------------------------------------
# Windows elevation
# ---------------------------------------------------------------------------


def _is_admin_windows() -> bool:
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _elevate_windows() -> NoReturn:
    """Re-launch with 'runas' via ShellExecuteW (triggers UAC prompt)."""
    import ctypes

    logger.info("Requesting UAC elevation via ShellExecuteW runas...")

    script = os.path.abspath(sys.argv[0])
    params = " ".join(f'"{a}"' for a in sys.argv[1:])

    # ShellExecuteW returns > 32 on success
    ret = ctypes.windll.shell32.ShellExecuteW(
        None,       # hwnd
        "runas",    # operation
        sys.executable,  # file
        f'"{script}" {params}',  # parameters
        None,       # directory
        1,          # SW_SHOWNORMAL
    )

    if ret <= 32:
        raise PrivilegeError(
            f"UAC elevation failed (ShellExecuteW returned {ret}). "
            "Please run as Administrator manually."
        )

    logger.info("Elevated process launched. Exiting current (unprivileged) process.")
    sys.exit(0)


# ---------------------------------------------------------------------------
# Linux privilege preparation
# ---------------------------------------------------------------------------


def _prepare_linux_sudo() -> None:
    """Ensure sudo is available and ready for Linux privileged sub-commands."""
    if not _sudo_available():
        raise PrivilegeError(
            "sudo is not available and process is not root. "
            "Run via ./update-ai-stack.sh from an interactive Linux shell."
        )

    if os.environ.get("GILLSYSTEMS_SUDO_NONINTERACTIVE") == "1" and _sudo_validate(non_interactive=True):
        logger.debug("Linux sudo session already primed by the launcher.")
        return

    try:
        subprocess.run(["sudo", "-v"], check=True, timeout=30)
    except subprocess.CalledProcessError as exc:
        raise PrivilegeError(
            "sudo authentication failed. Re-run ./update-ai-stack.sh from an interactive Linux terminal."
        ) from exc


def get_linux_sudo_prefix() -> list[str]:
    """Return the sudo prefix appropriate for Linux privileged helper commands."""
    if sys.platform == "win32" or is_admin():
        return []

    if os.environ.get("GILLSYSTEMS_SUDO_NONINTERACTIVE") == "1":
        return ["sudo", "-n"]

    return ["sudo"]


def _sudo_validate(non_interactive: bool = False) -> bool:
    cmd = ["sudo"]
    if non_interactive:
        cmd.append("-n")
    cmd.append("-v")

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=5)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _sudo_available() -> bool:
    return _sudo_validate() or _sudo_validate(non_interactive=True)
