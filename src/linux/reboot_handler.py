"""
reboot_handler.py (Linux) — Registers a systemd one-shot resume service.

After the system boots, the service runs `update-ai-stack.sh --resume`.
Once the resume completes, the service is removed.
"""
from __future__ import annotations

import getpass
import logging
import os
import subprocess
from pathlib import Path

try:
    import pwd
except ModuleNotFoundError:  # pragma: no cover - Windows test host only
    pwd = None

from src.cli import print_dry_run, print_info, print_step, print_success, print_warning
from src.config import GillsystemsAIStackUpdaterConfig
from src.privilege import get_linux_sudo_prefix

logger = logging.getLogger(__name__)

_SERVICE_NAME = "gillsystems-ai-stack-updater-resume.service"
_SERVICE_PATH = Path(f"/etc/systemd/system/{_SERVICE_NAME}")

_SERVICE_TEMPLATE = """\
[Unit]
Description=Gillsystems AI Stack Updater — Post-reboot Resume
After=network.target multi-user.target
ConditionPathExists={launcher}

[Service]
Type=oneshot
WorkingDirectory={working_dir}
Environment="HOME={owner_home}"
Environment="GILLSYSTEMS_REPO_OWNER={owner}"
Environment="GILLSYSTEMS_REPO_OWNER_HOME={owner_home}"
ExecStart=/bin/bash {launcher} --resume
ExecStartPost=/bin/systemctl disable {service_name}
RemainAfterExit=yes
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""


class RebootHandler:
    """Manages the systemd one-shot resume service and initiates reboot."""

    def __init__(self, cfg: GillsystemsAIStackUpdaterConfig) -> None:
        self.cfg = cfg
        self.launcher_path = self._find_launcher()
        self.repo_owner, self.repo_owner_home = self._resolve_owner_context()

    def _find_launcher(self) -> Path:
        """Locate update-ai-stack.sh relative to this module."""
        # Walk up from src/linux/ to project root
        here = Path(__file__).resolve().parent
        for candidate in [here.parent.parent, here.parent.parent.parent]:
            sh = candidate / "update-ai-stack.sh"
            if sh.exists():
                return sh
        # Fallback — return expected path
        return here.parent.parent / "update-ai-stack.sh"

    def _resolve_owner_context(self) -> tuple[str, str]:
        owner = (
            os.environ.get("GILLSYSTEMS_REPO_OWNER")
            or os.environ.get("SUDO_USER")
            or os.environ.get("USER")
            or getpass.getuser()
        )
        owner_home = os.environ.get("GILLSYSTEMS_REPO_OWNER_HOME", "")
        if not owner_home and pwd is not None:
            try:
                owner_home = pwd.getpwnam(owner).pw_dir
            except KeyError:
                pass
        if not owner_home:
            owner_home = str(Path.home())
        return owner, owner_home

    def register_resume_task(self) -> None:
        """Create the systemd one-shot service and enable it."""
        if self.cfg.behavior.dry_run:
            print_dry_run(f"Would create systemd service: {_SERVICE_PATH}")
            print_dry_run(f"Would enable: systemctl enable {_SERVICE_NAME}")
            return

        service_content = _SERVICE_TEMPLATE.format(
            launcher=self.launcher_path,
            working_dir=self.launcher_path.parent,
            owner=self.repo_owner,
            owner_home=self.repo_owner_home,
            service_name=_SERVICE_NAME,
        )

        print_step(f"Writing systemd service: {_SERVICE_PATH}")
        try:
            _SERVICE_PATH.write_text(service_content, encoding="utf-8")
        except PermissionError:
            # Try via sudo tee
            _write_via_sudo_tee(str(_SERVICE_PATH), service_content)

        _run_privileged(["systemctl", "daemon-reload"])
        _run_privileged(["systemctl", "enable", _SERVICE_NAME])
        print_success(f"Systemd resume service registered: {_SERVICE_NAME}")

    def unregister_resume_task(self) -> None:
        """Disable and remove the systemd service after successful resume."""
        if self.cfg.behavior.dry_run:
            print_dry_run(f"Would disable and remove: {_SERVICE_NAME}")
            return

        print_step(f"Removing resume service: {_SERVICE_NAME}")
        try:
            _run_privileged(["systemctl", "disable", _SERVICE_NAME], check=False)
            if _SERVICE_PATH.exists():
                _SERVICE_PATH.unlink()
            _run_privileged(["systemctl", "daemon-reload"])
            print_success("Resume service removed.")
        except Exception as exc:
            print_warning(f"Could not remove resume service: {exc}")

    def reboot(self) -> None:
        """Initiate a system reboot."""
        if self.cfg.behavior.dry_run:
            print_dry_run("Would run: sudo reboot")
            return

        print_info("Initiating system reboot...")
        _run_privileged(["reboot"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_privileged(
    cmd: list[str],
    check: bool = True,
) -> subprocess.CompletedProcess:
    cmd = get_linux_sudo_prefix() + cmd
    logger.debug("Running: %s", " ".join(cmd))
    return subprocess.run(cmd, check=check, timeout=30)


def _write_via_sudo_tee(path: str, content: str) -> None:
    """Write content to a privileged path using sudo tee."""
    result = subprocess.run(
        get_linux_sudo_prefix() + ["tee", path],
        input=content,
        text=True,
        capture_output=True,
        check=True,
    )
    logger.debug("tee wrote %d bytes to %s", len(content), path)
