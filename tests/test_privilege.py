"""Tests for platform privilege handling."""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from src.privilege import PrivilegeError, ensure_admin, get_linux_sudo_prefix


class TestLinuxPrivilegeHandling:
    def test_ensure_admin_accepts_warmed_sudo_session(self) -> None:
        with patch.object(sys, "platform", "linux"), \
             patch("src.privilege.os.geteuid", return_value=1000, create=True), \
             patch.dict("src.privilege.os.environ", {"GILLSYSTEMS_SUDO_NONINTERACTIVE": "1"}, clear=False), \
             patch("src.privilege._sudo_available", return_value=True), \
             patch("src.privilege._sudo_validate", return_value=True), \
             patch("src.privilege.subprocess.run") as mock_run:
            ensure_admin()

        mock_run.assert_not_called()

    def test_ensure_admin_runs_sudo_validate_when_needed(self) -> None:
        with patch.object(sys, "platform", "linux"), \
             patch("src.privilege.os.geteuid", return_value=1000, create=True), \
             patch.dict("src.privilege.os.environ", {}, clear=False), \
             patch("src.privilege._sudo_available", return_value=True), \
             patch("src.privilege._sudo_validate", return_value=False), \
             patch("src.privilege.subprocess.run", return_value=MagicMock(returncode=0)) as mock_run:
            ensure_admin()

        mock_run.assert_called_once_with(["sudo", "-v"], check=True, timeout=30)

    def test_ensure_admin_raises_without_sudo(self) -> None:
        with patch.object(sys, "platform", "linux"), \
             patch("src.privilege.os.geteuid", return_value=1000, create=True), \
             patch("src.privilege._sudo_available", return_value=False):
            with pytest.raises(PrivilegeError, match="sudo is not available"):
                ensure_admin()

    def test_get_linux_sudo_prefix_uses_noninteractive_mode_when_warmed(self) -> None:
        with patch.object(sys, "platform", "linux"), \
             patch("src.privilege.os.geteuid", return_value=1000, create=True), \
             patch.dict("src.privilege.os.environ", {"GILLSYSTEMS_SUDO_NONINTERACTIVE": "1"}, clear=False):
            assert get_linux_sudo_prefix() == ["sudo", "-n"]