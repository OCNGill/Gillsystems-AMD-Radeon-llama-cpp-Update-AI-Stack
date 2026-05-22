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
from src.runtime import get_node_id

logger = logging.getLogger(__name__)

_SERVICE_NAME_PREFIX = "gillsystems-ai-stack-updater-resume"

_SERVICE_TEMPLATE = """\
[Unit]
Description=Gillsystems AI Stack Updater — Post-reboot Resume
After=network.target multi-user.target
ConditionPathExists={launcher}

[Service]
Type=oneshot
WorkingDirectory={working_dir}
Environment="HOME={owner_home}"
Environment="GILLSYSTEMS_NODE_NAME={node_id}"
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
        self.node_id = get_node_id()
        self.service_name = f"{_SERVICE_NAME_PREFIX}-{self.node_id}.service"
        self.service_path = Path(f"/etc/systemd/system/{self.service_name}")
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
            print_dry_run(f"Would create systemd service: {self.service_path}")
            print_dry_run(f"Would enable: systemctl enable {self.service_name}")
            return

        service_content = _SERVICE_TEMPLATE.format(
            launcher=self.launcher_path,
            working_dir=self.launcher_path.parent,
            node_id=self.node_id,
            owner=self.repo_owner,
            owner_home=self.repo_owner_home,
            service_name=self.service_name,
        )

        print_step(f"Writing systemd service: {self.service_path}")
        try:
            self.service_path.write_text(service_content, encoding="utf-8")
        except PermissionError:
            # Try via sudo tee
            _write_via_sudo_tee(str(self.service_path), service_content)

        _run_privileged(["systemctl", "daemon-reload"])
        _run_privileged(["systemctl", "enable", self.service_name])
        print_success(f"Systemd resume service registered: {self.service_name}")

    def unregister_resume_task(self) -> None:
        """Disable and remove the systemd service after successful resume."""
        if self.cfg.behavior.dry_run:
            print_dry_run(f"Would disable and remove: {self.service_name}")
            return

        print_step(f"Removing resume service: {self.service_name}")
        try:
            _run_privileged(["systemctl", "disable", self.service_name], check=False)
            if self.service_path.exists():
                self.service_path.unlink()
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
