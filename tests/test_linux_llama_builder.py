from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

import src.linux.llama_builder as linux_llama_builder
from src.config import GillsystemsAIStackUpdaterConfig, load_config
from src.linux.llama_builder import LlamaBuilderLinux


def _make_cfg(tmp_path: Path) -> GillsystemsAIStackUpdaterConfig:
    cfg = load_config()
    cfg.behavior.dry_run = False
    cfg.paths.llama_cpp_source = str(tmp_path / "llama.cpp")
    cfg.paths.llama_cpp_install_linux = str(tmp_path / "install-root")
    return cfg


def _assert_commands_appear_in_order(commands: list[list[str]], expected_sequence: list[list[str]]) -> None:
    position = 0
    for expected in expected_sequence:
        while position < len(commands) and commands[position] != expected:
            position += 1
        if position == len(commands):
            raise AssertionError(f"Expected command not found in order: {expected}\nCommands: {commands}")
        position += 1


def _has_command_with_path(commands: list[list[str]], prefix: list[str], expected_path: str) -> bool:
    normalized_expected = expected_path.replace("\\", "/")
    prefix_len = len(prefix)
    return any(
        len(cmd) > prefix_len
        and cmd[:prefix_len] == prefix
        and cmd[prefix_len].replace("\\", "/") == normalized_expected
        for cmd in commands
    )


def test_install_uses_privileged_commands_for_protected_paths(tmp_path: Path) -> None:
    cfg = _make_cfg(tmp_path)
    builder = LlamaBuilderLinux(cfg, ["gfx1102"])
    builder.build_dir.mkdir(parents=True)
    (builder.install_dir / "bin").mkdir(parents=True)
    protected_symlink_dir = Path("/usr/local/bin")

    with patch("src.linux.llama_builder._path_requires_privilege", side_effect=lambda path: path in {builder.install_dir, protected_symlink_dir}), \
         patch("src.linux.llama_builder._run") as mock_run, \
         patch("src.linux.llama_builder._run_privileged") as mock_run_privileged, \
         patch("src.linux.llama_builder._mirror_install_bin_tree", return_value=None), \
         patch("src.linux.llama_builder._symlink_binaries") as mock_symlink:
        builder._install()

    mock_run.assert_not_called()
    assert mock_run_privileged.call_args_list[0].args[0] == ["mkdir", "-p", str(builder.install_dir)]
    assert mock_run_privileged.call_args_list[1].args[0] == [
        "cmake",
        "--install",
        str(builder.build_dir),
        "--prefix",
        str(builder.install_dir),
    ]
    mock_symlink.assert_called_once_with(builder.install_dir / "bin", protected_symlink_dir, privileged=True)


def test_install_uses_local_commands_for_user_writable_paths(tmp_path: Path) -> None:
    cfg = _make_cfg(tmp_path)
    builder = LlamaBuilderLinux(cfg, ["gfx1102"])
    builder.build_dir.mkdir(parents=True)
    (builder.install_dir / "bin").mkdir(parents=True)

    with patch("src.linux.llama_builder._path_requires_privilege", return_value=False), \
         patch("src.linux.llama_builder._run") as mock_run, \
         patch("src.linux.llama_builder._run_privileged") as mock_run_privileged, \
         patch("src.linux.llama_builder._mirror_install_bin_tree", return_value=None), \
         patch("src.linux.llama_builder._symlink_binaries") as mock_symlink:
        builder._install()

    mock_run.assert_called_once_with([
        "cmake",
        "--install",
        str(builder.build_dir),
        "--prefix",
        str(builder.install_dir),
    ], timeout=3600, env=None)
    mock_run_privileged.assert_not_called()
    mock_symlink.assert_called_once_with(builder.install_dir / "bin", Path("/usr/local/bin"), privileged=False)


def test_preflight_installs_steamos_vulkan_prereqs_when_missing(tmp_path: Path) -> None:
    cfg = _make_cfg(tmp_path)
    builder = LlamaBuilderLinux(cfg, ["gfx1033"])

    install_commands: list[list[str]] = []
    state = {"installed": False}

    def fake_which(tool: str) -> str | None:
        installed_tools = {
            "cmake": "/usr/bin/cmake",
            "git": "/usr/bin/git",
            "cc": "/usr/bin/cc",
            "c++": "/usr/bin/c++",
            "make": "/usr/bin/make",
            "ninja": "/usr/bin/ninja",
            "glslc": "/usr/bin/glslc",
            "pacman": "/usr/bin/pacman",
        }

        if tool == "pacman":
            return "/usr/bin/pacman"

        if tool == "hipcc":
            return None

        if state["installed"]:
            return installed_tools.get(tool)

        return None

    def fake_run_privileged(cmd: list[str], timeout: int = 3600, env: dict | None = None) -> None:
        install_commands.append(cmd)
        state["installed"] = True

    with patch("src.linux.llama_builder.shutil.which", side_effect=fake_which), \
         patch("src.linux.llama_builder._detect_distro", return_value="steamos arch"), \
            patch("src.linux.llama_builder._has_vulkan_loader", side_effect=lambda: state["installed"]), \
         patch("src.linux.llama_builder._has_vulkan_headers", side_effect=lambda: state["installed"]), \
         patch("src.linux.llama_builder._has_spirv_headers", side_effect=lambda: state["installed"]), \
         patch("src.linux.llama_builder._PACMAN_KEYRING_DIR", new=Path("/nonexistent/__gpg__")), \
         patch("src.linux.llama_builder._detect_available_pacman_keyrings", return_value=["archlinux", "holo"]), \
         patch("src.linux.llama_builder._run_privileged", side_effect=fake_run_privileged):
        builder._preflight_check()

    assert install_commands[0] == ["steamos-readonly", "disable"]
    assert install_commands[-1] == ["steamos-readonly", "enable"]
    assert _has_command_with_path(install_commands, ["mkdir", "-p"], "/var/lib/pacman")
    assert _has_command_with_path(install_commands, ["mkdir", "-p"], "/var/cache/pacman/pkg")
    assert _has_command_with_path(install_commands, ["mkdir", "-p"], "/nonexistent/__gpg__")
    _assert_commands_appear_in_order(install_commands, [
        ["pacman-key", "--init"],
        ["pacman-key", "--populate", "archlinux"],
        ["pacman-key", "--populate", "holo"],
        [
            "pacman",
            "-S",
            "--needed",
            "--noconfirm",
            "base-devel",
            "cmake",
            "git",
            "ninja",
            "shaderc",
            "spirv-headers",
            "vulkan-headers",
            "vulkan-icd-loader",
        ],
    ])
    assert builder._use_ninja is True


def test_detect_missing_linux_requirements_reports_vulkan_loader_when_missing() -> None:
    def fake_which(tool: str) -> str | None:
        return {
            "cmake": "/usr/bin/cmake",
            "git": "/usr/bin/git",
            "cc": "/usr/bin/cc",
            "c++": "/usr/bin/c++",
            "ninja": "/usr/bin/ninja",
            "glslc": "/usr/bin/glslc",
        }.get(tool)

    with patch("src.linux.llama_builder.shutil.which", side_effect=fake_which), \
         patch("src.linux.llama_builder._has_vulkan_loader", return_value=False), \
         patch("src.linux.llama_builder._has_vulkan_headers", return_value=True), \
         patch("src.linux.llama_builder._has_spirv_headers", return_value=True):
        missing = linux_llama_builder._detect_missing_linux_requirements(use_hip=False)

    assert missing == ["Vulkan loader"]


def test_arch_vulkan_install_plan_includes_icd_loader() -> None:
    with patch("src.linux.llama_builder.shutil.which", side_effect=lambda tool: "/usr/bin/pacman" if tool == "pacman" else None):
        package_manager, commands, installs_ninja = linux_llama_builder._build_linux_dependency_install_plan(
            "arch",
            use_hip=False,
        )

    assert package_manager == "pacman"
    assert installs_ninja is True
    assert "vulkan-icd-loader" in commands[0]


def test_preflight_dry_run_reports_steamos_install_plan(tmp_path: Path) -> None:
    cfg = _make_cfg(tmp_path)
    cfg.behavior.dry_run = True
    builder = LlamaBuilderLinux(cfg, ["gfx1033"])
    dry_run_messages: list[str] = []

    def fake_which(tool: str) -> str | None:
        if tool == "pacman":
            return "/usr/bin/pacman"
        if tool == "hipcc":
            return None
        return None

    with patch("src.linux.llama_builder.shutil.which", side_effect=fake_which), \
         patch("src.linux.llama_builder._detect_distro", return_value="steamos arch"), \
                patch("src.linux.llama_builder._has_vulkan_loader", return_value=False), \
            patch("src.linux.llama_builder._PACMAN_KEYRING_DIR", new=Path("/nonexistent/__gpg__")), \
            patch("src.linux.llama_builder._detect_available_pacman_keyrings", return_value=["archlinux", "holo"]), \
         patch("src.linux.llama_builder._has_vulkan_headers", return_value=False), \
         patch("src.linux.llama_builder._has_spirv_headers", return_value=False), \
         patch("src.linux.llama_builder.print_dry_run", side_effect=dry_run_messages.append):
        builder._preflight_check()

    assert builder._use_ninja is True
    assert any(
        "pacman -S --needed --noconfirm base-devel cmake git ninja shaderc spirv-headers vulkan-headers vulkan-icd-loader" in message
        for message in dry_run_messages
    )
    assert any("steamos-readonly disable" in message for message in dry_run_messages)
    assert any("steamos-readonly enable" in message for message in dry_run_messages)
    assert any("verify SteamOS pacman paths are writable" in message for message in dry_run_messages)
    assert any("pacman-key --init" in message for message in dry_run_messages)
    assert any("pacman-key --populate archlinux" in message for message in dry_run_messages)
    assert any("pacman-key --populate holo" in message for message in dry_run_messages)


def test_steamos_readonly_lock_restored_after_pacman_failure(tmp_path: Path) -> None:
    """steamos-readonly enable must be called even when pacman exits non-zero."""
    cfg = _make_cfg(tmp_path)
    builder = LlamaBuilderLinux(cfg, ["gfx1033"])

    privileged_calls: list[list[str]] = []

    def fake_which(tool: str) -> str | None:
        if tool == "pacman":
            return "/usr/bin/pacman"
        if tool == "hipcc":
            return None
        return None

    def fake_run_privileged(cmd: list[str], timeout: int = 3600, env: dict | None = None) -> None:
        privileged_calls.append(cmd)
        if cmd[0] == "pacman":
            raise RuntimeError("pacman failed (simulated)")

    with patch("src.linux.llama_builder.shutil.which", side_effect=fake_which), \
         patch("src.linux.llama_builder._detect_distro", return_value="steamos arch"), \
            patch("src.linux.llama_builder._has_vulkan_loader", return_value=False), \
         patch("src.linux.llama_builder._has_vulkan_headers", return_value=False), \
         patch("src.linux.llama_builder._has_spirv_headers", return_value=False), \
         patch("src.linux.llama_builder._PACMAN_KEYRING_DIR", new=Path("/nonexistent/__gpg__")), \
            patch("src.linux.llama_builder._detect_available_pacman_keyrings", return_value=["archlinux"]), \
         patch("src.linux.llama_builder._run_privileged", side_effect=fake_run_privileged):
        with pytest.raises(RuntimeError, match="pacman failed"):
            builder._preflight_check()

    # readonly must be re-enabled even after pacman failure
    assert ["steamos-readonly", "disable"] in privileged_calls
    assert ["steamos-readonly", "enable"] in privileged_calls


def test_steamos_populates_available_keyrings_when_already_present(tmp_path: Path) -> None:
    """SteamOS should repopulate available vendor keyrings even when initialized."""
    cfg = _make_cfg(tmp_path)
    builder = LlamaBuilderLinux(cfg, ["gfx1033"])

    # Simulate an already-initialised keyring
    fake_gnupg = tmp_path / "gnupg"
    fake_gnupg.mkdir()
    (fake_gnupg / "pubring.gpg").touch()
    (fake_gnupg / "trustdb.gpg").touch()

    privileged_calls: list[list[str]] = []
    state = {"installed": False}

    def fake_which(tool: str) -> str | None:
        installed = {"cmake", "git", "cc", "c++", "ninja", "glslc", "pacman"}
        if tool == "hipcc":
            return None
        if tool == "pacman":
            return "/usr/bin/pacman"
        return f"/usr/bin/{tool}" if (tool in installed and state["installed"]) else None

    def fake_run_privileged(cmd: list[str], timeout: int = 3600, env: dict | None = None) -> None:
        privileged_calls.append(cmd)
        state["installed"] = True

    with patch("src.linux.llama_builder.shutil.which", side_effect=fake_which), \
         patch("src.linux.llama_builder._detect_distro", return_value="steamos arch"), \
            patch("src.linux.llama_builder._has_vulkan_loader", side_effect=lambda: state["installed"]), \
         patch("src.linux.llama_builder._has_vulkan_headers", side_effect=lambda: state["installed"]), \
         patch("src.linux.llama_builder._has_spirv_headers", side_effect=lambda: state["installed"]), \
         patch("src.linux.llama_builder._PACMAN_KEYRING_DIR", new=fake_gnupg), \
         patch("src.linux.llama_builder._detect_available_pacman_keyrings", return_value=["archlinux", "holo"]), \
         patch("src.linux.llama_builder._run_privileged", side_effect=fake_run_privileged):
        builder._preflight_check()

    assert ["pacman-key", "--init"] not in privileged_calls
    assert ["pacman-key", "--populate", "archlinux"] in privileged_calls
    assert ["pacman-key", "--populate", "holo"] in privileged_calls
    assert ["steamos-readonly", "disable"] in privileged_calls
    assert ["steamos-readonly", "enable"] in privileged_calls


def test_preflight_requires_hipcc_for_tier1(tmp_path: Path) -> None:
    cfg = _make_cfg(tmp_path)
    builder = LlamaBuilderLinux(cfg, ["gfx1102"])

    def fake_which(tool: str) -> str | None:
        return {
            "cmake": "/usr/bin/cmake",
            "git": "/usr/bin/git",
            "cc": "/usr/bin/cc",
            "c++": "/usr/bin/c++",
            "make": "/usr/bin/make",
        }.get(tool)

    with patch("src.linux.llama_builder.shutil.which", side_effect=fake_which):
        with pytest.raises(RuntimeError, match="Tier 1 hardware REQUIRES the ROCm HIP SDK"):
            builder._preflight_check()