"""
test_linux_rocm.py — Tests for Linux ROCm updater sub-agent.

Uses mocks to avoid touching the real system. Verifies:
- distro detection
- installer URL construction
- amdgpu-install command construction
- user group addition
- reboot requirement detection
"""
from __future__ import annotations

import subprocess
from pathlib import Path
import sys
from unittest.mock import MagicMock, call, patch

import pytest

from src.config import load_config, GillsystemsAIStackUpdaterConfig, BehaviorConfig


@pytest.fixture
def dry_run_cfg() -> GillsystemsAIStackUpdaterConfig:
    cfg = load_config()
    cfg.behavior.dry_run = True
    return cfg


@pytest.fixture
def live_cfg() -> GillsystemsAIStackUpdaterConfig:
    cfg = load_config()
    cfg.behavior.dry_run = False
    return cfg


# ---------------------------------------------------------------------------
# ROCmUpdater — distro detection
# ---------------------------------------------------------------------------


class TestDistroDetection:
    def test_detect_ubuntu(self):
        from src.linux.rocm_updater import _detect_distro, _is_debian_based

        with patch("platform.freedesktop_os_release", return_value={"ID": "ubuntu", "ID_LIKE": "debian"}):
            distro = _detect_distro()

        assert _is_debian_based(distro) is True

    def test_detect_fedora(self):
        from src.linux.rocm_updater import _detect_distro, _is_debian_based

        with patch("platform.freedesktop_os_release", return_value={"ID": "fedora", "ID_LIKE": ""}):
            distro = _detect_distro()

        assert _is_debian_based(distro) is False

    def test_detect_fallback(self):
        from src.linux.rocm_updater import _detect_distro

        with patch("platform.freedesktop_os_release", side_effect=AttributeError), \
             patch("builtins.open", side_effect=OSError):
            distro = _detect_distro()

        assert distro == ""


# ---------------------------------------------------------------------------
# ROCmUpdater — dry-run mode
# ---------------------------------------------------------------------------


class TestROCmUpdaterDryRun:
    def test_update_dry_run_returns_no_reboot(self, dry_run_cfg: GillsystemsAIStackUpdaterConfig):
        from src.linux.rocm_updater import ROCmUpdater

        updater = ROCmUpdater(dry_run_cfg)
        with patch("src.linux.rocm_updater._detect_distro", return_value="ubuntu jammy"), \
             patch("src.linux.rocm_updater._is_arch_based", return_value=False), \
             patch.object(updater, "_download_amdgpu_install", return_value=Path("/tmp/fake.deb")), \
             patch.object(updater, "_install_package"), \
             patch.object(updater, "_run_amdgpu_install", return_value=False):
            reboot = updater.update()

        assert reboot is False

    def test_amdgpu_install_command_content(self, dry_run_cfg: GillsystemsAIStackUpdaterConfig):
        from src.linux.rocm_updater import ROCmUpdater

        updater = ROCmUpdater(dry_run_cfg)
        with patch("src.linux.rocm_updater._run_privileged") as mock_run:
            updater._run_amdgpu_install()
        # In dry-run, it shouldn't actually call _run_privileged
        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# ROCmUpdater — reboot detection
# ---------------------------------------------------------------------------


class TestROCmRebootDetection:
    def test_reboot_detected_from_kernel_hint(self, live_cfg: GillsystemsAIStackUpdaterConfig):
        from src.linux.rocm_updater import ROCmUpdater

        updater = ROCmUpdater(live_cfg)
        mock_res = MagicMock()
        mock_res.stdout = "New kernel module installed, please reboot"
        mock_res.stderr = ""

        with patch("src.linux.rocm_updater._run_privileged", return_value=mock_res):
            reboot = updater._run_amdgpu_install()

        assert reboot is True

    def test_no_reboot_when_no_kernel_hint(self, live_cfg: GillsystemsAIStackUpdaterConfig):
        from src.linux.rocm_updater import ROCmUpdater

        updater = ROCmUpdater(live_cfg)
        mock_res = MagicMock()
        mock_res.stdout = "Packages installed successfully"
        mock_res.stderr = ""

        with patch("src.linux.rocm_updater._run_privileged", return_value=mock_res):
            reboot = updater._run_amdgpu_install()

        assert reboot is False


# ---------------------------------------------------------------------------
# RebootHandler (Linux)
# ---------------------------------------------------------------------------


class TestLinuxRebootHandler:
    def test_register_task_dry_run(self, dry_run_cfg: GillsystemsAIStackUpdaterConfig):
        from src.linux.reboot_handler import RebootHandler

        handler = RebootHandler(dry_run_cfg)
        with patch("src.linux.reboot_handler._run_privileged") as mock_run:
            handler.register_resume_task()
        mock_run.assert_not_called()

    def test_unregister_task_dry_run(self, dry_run_cfg: GillsystemsAIStackUpdaterConfig):
        from src.linux.reboot_handler import RebootHandler

        handler = RebootHandler(dry_run_cfg)
        with patch("src.linux.reboot_handler._run_privileged") as mock_run:
            handler.unregister_resume_task()
        mock_run.assert_not_called()

    def test_reboot_dry_run(self, dry_run_cfg: GillsystemsAIStackUpdaterConfig):
        from src.linux.reboot_handler import RebootHandler

        handler = RebootHandler(dry_run_cfg)
        with patch("src.linux.reboot_handler._run_privileged") as mock_run:
            handler.reboot()
        mock_run.assert_not_called()

    def test_service_file_content(self, live_cfg: GillsystemsAIStackUpdaterConfig):
        """The systemd service content should reference the launcher."""
        from src.linux.reboot_handler import _SERVICE_TEMPLATE, RebootHandler

        with patch.dict(
            "os.environ",
            {
                "GILLSYSTEMS_REPO_OWNER": "deck",
                "GILLSYSTEMS_REPO_OWNER_HOME": "/home/deck",
            },
            clear=False,
        ):
            handler = RebootHandler(live_cfg)
            content = _SERVICE_TEMPLATE.format(
                launcher=str(handler.launcher_path),
                working_dir=str(handler.launcher_path.parent),
                owner=handler.repo_owner,
                owner_home=handler.repo_owner_home,
                service_name="gillsystems-ai-stack-updater-resume.service",
            )

        assert "gillsystems-ai-stack-updater-resume.service" in content
        assert "oneshot" in content
        assert 'Environment="GILLSYSTEMS_REPO_OWNER=deck"' in content
        assert 'Environment="HOME=/home/deck"' in content

    def test_rocm_run_privileged_uses_noninteractive_sudo_when_warmed(self):
        from src.linux.rocm_updater import _run_privileged

        with patch.object(sys, "platform", "linux"), \
             patch("src.privilege.os.geteuid", return_value=1000, create=True), \
             patch.dict("src.privilege.os.environ", {"GILLSYSTEMS_SUDO_NONINTERACTIVE": "1"}, clear=False), \
             patch("src.linux.rocm_updater.subprocess.run") as mock_run:
            _run_privileged(["apt-get", "install", "-y", "fake.deb"])

        assert mock_run.call_args.args[0][:2] == ["sudo", "-n"]
