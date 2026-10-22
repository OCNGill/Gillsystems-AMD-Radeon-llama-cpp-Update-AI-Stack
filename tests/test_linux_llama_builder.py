from __future__ import annotations

import subprocess
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


def test_configure_cmake_removes_stale_cache_before_reconfigure(tmp_path: Path) -> None:
    cfg = _make_cfg(tmp_path)
    builder = LlamaBuilderLinux(cfg, ["gfx1033"])
    builder._use_ninja = True
    builder.build_dir.mkdir(parents=True)
    cache_file = builder.build_dir / "CMakeCache.txt"
    cache_file.write_text("Vulkan_INCLUDE_DIR:PATH=Vulkan_INCLUDE_DIR-NOTFOUND\n", encoding="utf-8")

    with patch("src.linux.llama_builder._run") as mock_run:
        builder._configure_cmake()

    assert not cache_file.exists()
    mock_run.assert_called_once()


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
         patch("src.linux.llama_builder._has_c_runtime_headers", side_effect=lambda: state["installed"]), \
            patch("src.linux.llama_builder._has_linux_api_headers", side_effect=lambda: state["installed"]), \
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
            "linux-api-headers",
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
         patch("src.linux.llama_builder._has_c_runtime_headers", return_value=True), \
            patch("src.linux.llama_builder._has_linux_api_headers", return_value=True), \
         patch("src.linux.llama_builder._has_vulkan_loader", return_value=False), \
         patch("src.linux.llama_builder._has_vulkan_headers", return_value=True), \
         patch("src.linux.llama_builder._has_spirv_headers", return_value=True):
        missing = linux_llama_builder._detect_missing_linux_requirements(use_hip=False)

    assert missing == ["Vulkan loader"]


def test_detect_missing_linux_requirements_reports_vulkan_headers_when_missing() -> None:
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
         patch("src.linux.llama_builder._has_c_runtime_headers", return_value=True), \
            patch("src.linux.llama_builder._has_linux_api_headers", return_value=True), \
         patch("src.linux.llama_builder._has_vulkan_loader", return_value=True), \
         patch("src.linux.llama_builder._has_vulkan_headers", return_value=False), \
         patch("src.linux.llama_builder._has_spirv_headers", return_value=True):
        missing = linux_llama_builder._detect_missing_linux_requirements(use_hip=False)

    assert missing == ["Vulkan headers"]


def test_detect_missing_linux_requirements_reports_c_runtime_headers_when_missing() -> None:
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
         patch("src.linux.llama_builder._has_c_runtime_headers", return_value=False), \
         patch("src.linux.llama_builder._has_linux_api_headers", return_value=True), \
         patch("src.linux.llama_builder._has_vulkan_loader", return_value=True), \
         patch("src.linux.llama_builder._has_vulkan_headers", return_value=True), \
         patch("src.linux.llama_builder._has_spirv_headers", return_value=True):
        missing = linux_llama_builder._detect_missing_linux_requirements(use_hip=False)

    assert missing == ["C runtime headers"]


def test_detect_missing_linux_requirements_reports_linux_api_headers_when_missing() -> None:
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
         patch("src.linux.llama_builder._has_c_runtime_headers", return_value=True), \
         patch("src.linux.llama_builder._has_linux_api_headers", return_value=False), \
         patch("src.linux.llama_builder._has_vulkan_loader", return_value=True), \
         patch("src.linux.llama_builder._has_vulkan_headers", return_value=True), \
         patch("src.linux.llama_builder._has_spirv_headers", return_value=True):
        missing = linux_llama_builder._detect_missing_linux_requirements(use_hip=False)

    assert missing == ["Linux API headers"]


def test_arch_vulkan_install_plan_includes_icd_loader() -> None:
    with patch("src.linux.llama_builder.shutil.which", side_effect=lambda tool: "/usr/bin/pacman" if tool == "pacman" else None):
        package_manager, commands, installs_ninja = linux_llama_builder._build_linux_dependency_install_plan(
            "arch",
            use_hip=False,
        )

    assert package_manager == "pacman"
    assert installs_ninja is True
    assert "vulkan-icd-loader" in commands[0]
    assert "linux-api-headers" in commands[0]


def test_arch_repair_package_list_maps_missing_requirements_to_packages() -> None:
    packages = linux_llama_builder._build_arch_repair_package_list([
        "Vulkan headers",
        "Vulkan loader",
        "SPIRV-Headers",
        "glslc",
    ])

    assert packages == ["vulkan-headers", "vulkan-icd-loader", "spirv-headers", "shaderc"]


def test_arch_repair_package_list_maps_c_runtime_headers_to_glibc() -> None:
    packages = linux_llama_builder._build_arch_repair_package_list(["C runtime headers"])

    assert packages == ["glibc"]


def test_arch_repair_package_list_maps_linux_api_headers_to_package() -> None:
    packages = linux_llama_builder._build_arch_repair_package_list(["Linux API headers"])

    assert packages == ["linux-api-headers"]


def test_has_vulkan_headers_ignores_pkg_config_loader_signal() -> None:
    def fake_which(tool: str) -> str | None:
        return "/usr/bin/pkg-config" if tool in {"pkg-config", "pkgconf"} else None

    def fake_exists(self: Path) -> bool:
        return False

    with patch("src.linux.llama_builder.shutil.which", side_effect=fake_which), \
         patch("src.linux.llama_builder.subprocess.run") as mock_run, \
         patch("pathlib.Path.exists", new=fake_exists):
        assert linux_llama_builder._has_vulkan_headers() is False

    mock_run.assert_not_called()


def test_preflight_forces_targeted_reinstall_when_pacman_needed_skips_missing_headers(tmp_path: Path) -> None:
    cfg = _make_cfg(tmp_path)
    builder = LlamaBuilderLinux(cfg, ["gfx1033"])

    privileged_calls: list[list[str]] = []
    state = {"header_fixed": False}

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
        if tool == "hipcc":
            return None
        return installed_tools.get(tool)

    def fake_run_privileged(cmd: list[str], timeout: int = 3600, env: dict | None = None) -> None:
        privileged_calls.append(cmd)
        if cmd[:4] == ["pacman", "-S", "--noconfirm", "vulkan-headers"]:
            state["header_fixed"] = True

    with patch("src.linux.llama_builder.shutil.which", side_effect=fake_which), \
         patch("src.linux.llama_builder._detect_distro", return_value="steamos arch"), \
         patch("src.linux.llama_builder._has_c_runtime_headers", return_value=True), \
            patch("src.linux.llama_builder._has_linux_api_headers", return_value=True), \
         patch("src.linux.llama_builder._has_vulkan_loader", return_value=True), \
         patch("src.linux.llama_builder._has_vulkan_headers", side_effect=lambda: state["header_fixed"]), \
         patch("src.linux.llama_builder._has_spirv_headers", return_value=True), \
         patch("src.linux.llama_builder._PACMAN_KEYRING_DIR", new=Path("/nonexistent/__gpg__")), \
         patch("src.linux.llama_builder._detect_available_pacman_keyrings", return_value=["archlinux", "holo"]), \
         patch("src.linux.llama_builder._run_privileged", side_effect=fake_run_privileged):
        builder._preflight_check()

    assert ["pacman", "-S", "--needed", "--noconfirm", "base-devel", "linux-api-headers", "cmake", "git", "ninja", "shaderc", "spirv-headers", "vulkan-headers", "vulkan-icd-loader"] in privileged_calls
    assert ["pacman", "-S", "--noconfirm", "vulkan-headers"] in privileged_calls
    assert builder._use_ninja is True


def test_preflight_forces_targeted_reinstall_when_c_runtime_headers_are_missing(tmp_path: Path) -> None:
    cfg = _make_cfg(tmp_path)
    builder = LlamaBuilderLinux(cfg, ["gfx1033"])

    privileged_calls: list[list[str]] = []
    state = {"libc_fixed": False}

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
        if tool == "hipcc":
            return None
        return installed_tools.get(tool)

    def fake_run_privileged(cmd: list[str], timeout: int = 3600, env: dict | None = None) -> None:
        privileged_calls.append(cmd)
        if cmd[:4] == ["pacman", "-S", "--noconfirm", "glibc"]:
            state["libc_fixed"] = True

    with patch("src.linux.llama_builder.shutil.which", side_effect=fake_which), \
         patch("src.linux.llama_builder._detect_distro", return_value="steamos arch"), \
         patch("src.linux.llama_builder._has_c_runtime_headers", side_effect=lambda: state["libc_fixed"]), \
         patch("src.linux.llama_builder._has_linux_api_headers", return_value=True), \
         patch("src.linux.llama_builder._has_vulkan_loader", return_value=True), \
         patch("src.linux.llama_builder._has_vulkan_headers", return_value=True), \
         patch("src.linux.llama_builder._has_spirv_headers", return_value=True), \
         patch("src.linux.llama_builder._PACMAN_KEYRING_DIR", new=Path("/nonexistent/__gpg__")), \
         patch("src.linux.llama_builder._detect_available_pacman_keyrings", return_value=["archlinux", "holo"]), \
         patch("src.linux.llama_builder._run_privileged", side_effect=fake_run_privileged):
        builder._preflight_check()

    assert ["pacman", "-S", "--needed", "--noconfirm", "base-devel", "linux-api-headers", "cmake", "git", "ninja", "shaderc", "spirv-headers", "vulkan-headers", "vulkan-icd-loader"] in privileged_calls
    assert ["pacman", "-S", "--noconfirm", "glibc"] in privileged_calls
    assert builder._use_ninja is True


def test_preflight_forces_targeted_reinstall_when_linux_api_headers_are_missing(tmp_path: Path) -> None:
    cfg = _make_cfg(tmp_path)
    builder = LlamaBuilderLinux(cfg, ["gfx1033"])

    privileged_calls: list[list[str]] = []
    state = {"linux_headers_fixed": False}

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
        if tool == "hipcc":
            return None
        return installed_tools.get(tool)

    def fake_run_privileged(cmd: list[str], timeout: int = 3600, env: dict | None = None) -> None:
        privileged_calls.append(cmd)
        if cmd[:4] == ["pacman", "-S", "--noconfirm", "linux-api-headers"]:
            state["linux_headers_fixed"] = True

    with patch("src.linux.llama_builder.shutil.which", side_effect=fake_which), \
         patch("src.linux.llama_builder._detect_distro", return_value="steamos arch"), \
         patch("src.linux.llama_builder._has_c_runtime_headers", return_value=True), \
         patch("src.linux.llama_builder._has_linux_api_headers", side_effect=lambda: state["linux_headers_fixed"]), \
         patch("src.linux.llama_builder._has_vulkan_loader", return_value=True), \
         patch("src.linux.llama_builder._has_vulkan_headers", return_value=True), \
         patch("src.linux.llama_builder._has_spirv_headers", return_value=True), \
         patch("src.linux.llama_builder._PACMAN_KEYRING_DIR", new=Path("/nonexistent/__gpg__")), \
         patch("src.linux.llama_builder._detect_available_pacman_keyrings", return_value=["archlinux", "holo"]), \
         patch("src.linux.llama_builder._run_privileged", side_effect=fake_run_privileged):
        builder._preflight_check()

    assert ["pacman", "-S", "--needed", "--noconfirm", "base-devel", "linux-api-headers", "cmake", "git", "ninja", "shaderc", "spirv-headers", "vulkan-headers", "vulkan-icd-loader"] in privileged_calls
    assert ["pacman", "-S", "--noconfirm", "linux-api-headers"] in privileged_calls
    assert builder._use_ninja is True


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
         patch("src.linux.llama_builder._has_c_runtime_headers", return_value=False), \
            patch("src.linux.llama_builder._has_linux_api_headers", return_value=False), \
         patch("src.linux.llama_builder._has_vulkan_loader", return_value=False), \
         patch("src.linux.llama_builder._PACMAN_KEYRING_DIR", new=Path("/nonexistent/__gpg__")), \
         patch("src.linux.llama_builder._detect_available_pacman_keyrings", return_value=["archlinux", "holo"]), \
         patch("src.linux.llama_builder._has_vulkan_headers", return_value=False), \
         patch("src.linux.llama_builder._has_spirv_headers", return_value=False), \
         patch("src.linux.llama_builder.print_dry_run", side_effect=dry_run_messages.append):
        builder._preflight_check()

    assert builder._use_ninja is True
    assert any(
        "pacman -S --needed --noconfirm base-devel linux-api-headers cmake git ninja shaderc spirv-headers vulkan-headers vulkan-icd-loader" in message
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
         patch("src.linux.llama_builder._has_c_runtime_headers", return_value=False), \
            patch("src.linux.llama_builder._has_linux_api_headers", return_value=False), \
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
         patch("src.linux.llama_builder._has_c_runtime_headers", side_effect=lambda: state["installed"]), \
            patch("src.linux.llama_builder._has_linux_api_headers", side_effect=lambda: state["installed"]), \
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


# ---------------------------------------------------------------------------
# HIP configure repair — a CPU-only build must never be reported as success
# ---------------------------------------------------------------------------


def _hip_toolchain(root: Path) -> linux_llama_builder.RocmToolchain:
    """A synthetic SDK-coherent ROCm toolchain rooted at *root*."""
    sdk_compiler = root / "lib" / "llvm" / "bin" / "clang++"
    return linux_llama_builder.RocmToolchain(
        root=root,
        hip_path=str(root),
        hipcxx=str(sdk_compiler),
        hip_compiler=str(sdk_compiler),
        sdk_coherent=True,
        source=str(root),
    )


def _hip_builder(tmp_path: Path, targets: list[str] | None = None) -> LlamaBuilderLinux:
    cfg = _make_cfg(tmp_path)
    builder = LlamaBuilderLinux(cfg, targets or ["gfx1100"])
    builder.use_hip = True
    builder._use_ninja = True
    builder.build_dir = tmp_path / "build-hip"
    builder.build_dir.mkdir(parents=True, exist_ok=True)
    return builder


def test_hip_cache_state_is_tri_state(tmp_path: Path) -> None:
    """The cache reader reports on/off/unknown and never guesses."""
    cache = tmp_path / "CMakeCache.txt"

    cache.write_text("GGML_HIP:BOOL=ON\n", encoding="utf-8")
    assert linux_llama_builder._hip_cache_state(tmp_path) == "on"

    cache.write_text("GGML_HIP:BOOL=OFF\n", encoding="utf-8")
    assert linux_llama_builder._hip_cache_state(tmp_path) == "off"

    cache.write_text("CMAKE_BUILD_TYPE:STRING=Release\n", encoding="utf-8")
    assert linux_llama_builder._hip_cache_state(tmp_path) == "unknown"

    cache.unlink()
    assert linux_llama_builder._hip_cache_state(tmp_path) == "unknown"


def test_configure_cmake_reconfigures_when_cache_drops_hip_flag(tmp_path: Path) -> None:
    """A ROCm SDK upgrade makes CMake re-run configure and silently lose
    -DGGML_HIP=ON. The builder must notice the CPU-only cache and re-configure
    with HIP explicitly enabled instead of building a CPU-only llama.cpp."""
    builder = _hip_builder(tmp_path)
    toolchain = _hip_toolchain(tmp_path / "rocm-7.2.4")

    calls: list[list[str]] = []

    def fake_run(cmd, timeout=3600, env=None):
        calls.append(list(cmd))
        # First configure writes a CPU-only cache (the regression). The
        # re-configure (after the cache file is deleted) writes GGML_HIP=ON.
        cache = builder.build_dir / "CMakeCache.txt"
        hip_on = len(calls) > 1
        cache.write_text(
            "CMAKE_BUILD_TYPE:STRING=Release\n"
            + ("GGML_HIP:BOOL=ON\n" if hip_on else "GGML_HIP:BOOL=OFF\n"),
            encoding="utf-8",
        )
        return 0

    with patch("src.linux.llama_builder._resolve_rocm_toolchain", return_value=toolchain), \
         patch("src.linux.llama_builder._run", side_effect=fake_run):
        builder._configure_cmake()

    assert len(calls) == 2, f"expected a re-configure, got {len(calls)} cmake runs"
    assert "-DGGML_HIP=ON" in calls[1]
    assert "-DAMDGPU_TARGETS=gfx1100" in calls[1]
    assert f"-DCMAKE_INSTALL_PREFIX={builder.install_dir}" in calls[1]


def test_configure_cmake_raises_when_hip_stays_off_after_reconfigure(tmp_path: Path) -> None:
    """If the cache still says GGML_HIP=OFF after a clean re-configure, the
    builder must refuse to build a CPU-only llama.cpp."""
    builder = _hip_builder(tmp_path)
    toolchain = _hip_toolchain(tmp_path / "rocm-7.2.4")

    def fake_run(cmd, timeout=3600, env=None):
        (builder.build_dir / "CMakeCache.txt").write_text(
            "GGML_HIP:BOOL=OFF\n", encoding="utf-8"
        )
        return 0

    with patch("src.linux.llama_builder._resolve_rocm_toolchain", return_value=toolchain), \
         patch("src.linux.llama_builder._run", side_effect=fake_run):
        with pytest.raises(RuntimeError, match="GGML_HIP"):
            builder._configure_cmake()


def test_configure_cmake_passes_sdk_rocm_path_and_hip_compiler(tmp_path: Path) -> None:
    """An SDK-coherent toolchain must pin the compile-time ROCm to the same
    generation as the deployed runtime."""
    builder = _hip_builder(tmp_path)
    sdk_root = tmp_path / "rocm-7.2.4"
    toolchain = _hip_toolchain(sdk_root)

    calls: list[list[str]] = []

    def fake_run(cmd, timeout=3600, env=None):
        calls.append(list(cmd))
        (builder.build_dir / "CMakeCache.txt").write_text(
            "GGML_HIP:BOOL=ON\n", encoding="utf-8"
        )
        return 0

    with patch("src.linux.llama_builder._resolve_rocm_toolchain", return_value=toolchain), \
         patch("src.linux.llama_builder._run", side_effect=fake_run):
        builder._configure_cmake()

    assert len(calls) == 1
    assert f"-DROCM_PATH={sdk_root}" in calls[0]
    assert f"-DCMAKE_HIP_COMPILER={sdk_root / 'lib' / 'llvm' / 'bin' / 'clang++'}" in calls[0]


# ---------------------------------------------------------------------------
# HIP validation — a CPU-only install must not be reported as a success
# ---------------------------------------------------------------------------


def _hip_install_tree(tmp_path: Path) -> LlamaBuilderLinux:
    builder = _hip_builder(tmp_path)
    bin_dir = builder.install_dir / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    (bin_dir / "llama-cli").write_bytes(b"ELF")
    (bin_dir / "llama-server").write_bytes(b"ELF")
    lib_dir = builder.install_dir / "lib"
    lib_dir.mkdir(parents=True, exist_ok=True)
    (lib_dir / "libggml-hip.so").write_bytes(b"ELF")
    return builder


def test_validate_raises_when_only_cpu_device_is_enumerated(tmp_path: Path) -> None:
    """A CPU-only install passes every --version check, so validation must
    prove a real GPU device registers before reporting success."""
    builder = _hip_install_tree(tmp_path)
    toolchain = _hip_toolchain(tmp_path / "rocm-7.2.4")

    def fake_run(cmd, **kwargs):
        if "--version" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "version: 0.7.0-dev", "")
        return subprocess.CompletedProcess(cmd, 0, "Available devices:\n  CPU\n", "")

    with patch("src.linux.llama_builder._resolve_rocm_toolchain", return_value=toolchain), \
         patch("src.linux.llama_builder.subprocess.run", side_effect=fake_run):
        with pytest.raises(RuntimeError, match="no GPU device"):
            builder._validate()


def test_validate_raises_when_hip_backend_artifact_is_missing(tmp_path: Path) -> None:
    """A HIP build that installed no ggml-hip library is a CPU-only build."""
    builder = _hip_install_tree(tmp_path)
    (builder.install_dir / "lib" / "libggml-hip.so").unlink()
    toolchain = _hip_toolchain(tmp_path / "rocm-7.2.4")

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, "version: 0.7.0-dev", "")

    with patch("src.linux.llama_builder._resolve_rocm_toolchain", return_value=toolchain), \
         patch("src.linux.llama_builder.subprocess.run", side_effect=fake_run):
        with pytest.raises(RuntimeError, match="HIP backend library"):
            builder._validate()


def test_validate_accepts_a_working_gpu_backend(tmp_path: Path) -> None:
    """The positive path: a real ROCm device must let validation pass."""
    builder = _hip_install_tree(tmp_path)
    toolchain = _hip_toolchain(tmp_path / "rocm-7.2.4")

    def fake_run(cmd, **kwargs):
        if "--version" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "version: 0.7.0-dev", "")
        return subprocess.CompletedProcess(
            cmd, 0, "Available devices:\n  ROCm0 (AMD Radeon RX 7900 XTX)\n", ""
        )

    with patch("src.linux.llama_builder._resolve_rocm_toolchain", return_value=toolchain), \
         patch("src.linux.llama_builder.subprocess.run", side_effect=fake_run):
        builder._validate()


# ---------------------------------------------------------------------------
# ROCm SDK resolution — the distro ROCm must never win over an SDK
# ---------------------------------------------------------------------------


def _fake_sdk_root(base: Path, version: str = "7.2.4") -> Path:
    """Create a directory tree shaped like a ROCm SDK install."""
    root = base / f"rocm-{version}"
    (root / "lib" / "llvm" / "bin").mkdir(parents=True, exist_ok=True)
    (root / "lib" / "llvm" / "bin" / "clang++").write_text("#!/bin/sh\n", encoding="utf-8")
    (root / "bin").mkdir(parents=True, exist_ok=True)
    (root / "bin" / "hipconfig").write_text("#!/bin/sh\n", encoding="utf-8")
    return root


def _fake_distro_rocm_root(base: Path) -> Path:
    """Create a directory tree shaped like a distro ROCm (not an SDK).

    It has a hipconfig and a versioned LLVM, but no ``lib/llvm/bin/clang++``,
    so it must never be selected over a real SDK root.
    """
    root = base / "distro-rocm"
    (root / "lib" / "llvm-21" / "bin").mkdir(parents=True, exist_ok=True)
    (root / "lib" / "llvm-21" / "bin" / "clang++").write_text("#!/bin/sh\n", encoding="utf-8")
    (root / "bin").mkdir(parents=True, exist_ok=True)
    (root / "bin" / "hipconfig").write_text("#!/bin/sh\n", encoding="utf-8")
    return root


def test_rocm_toolchain_prefers_sdk_root_over_path_hipconfig(tmp_path: Path) -> None:
    """A ROCm SDK root must win over the distro ROCm that is first on PATH."""
    sdk_root = _fake_sdk_root(tmp_path)
    distro_root = _fake_distro_rocm_root(tmp_path)
    queries: list[list[str]] = []

    def fake_check_output(cmd, *args, **kwargs):
        queries.append(list(cmd))
        if cmd[1] == "-R":
            return f"{sdk_root}\n"
        if cmd[1] == "-l":
            return f"{sdk_root / 'lib' / 'llvm' / 'bin'}\n"
        return ""

    with patch.dict("src.linux.llama_builder.os.environ", {"HIP_PATH": str(distro_root)}), \
         patch("src.linux.llama_builder._ROCM_SDK_SEARCH_DIR", new=tmp_path), \
         patch("src.linux.llama_builder._ROCM_DEFAULT_SDK_ROOT", new=tmp_path / "no-rocm"), \
         patch("src.linux.llama_builder.shutil.which", return_value=str(distro_root / "bin" / "hipconfig")), \
         patch("src.linux.llama_builder.subprocess.check_output", side_effect=fake_check_output):
        toolchain = linux_llama_builder._resolve_rocm_toolchain()

    assert toolchain.sdk_coherent is True
    assert toolchain.root == sdk_root
    assert toolchain.hip_path == str(sdk_root)
    assert toolchain.hip_compiler == str(sdk_root / "lib" / "llvm" / "bin" / "clang++")
    assert toolchain.hipcxx == str(sdk_root / "lib" / "llvm" / "bin" / "clang++")
    # The SDK's own hipconfig must be used, never the PATH one.
    assert queries
    assert all(query[0] == str(sdk_root / "bin" / "hipconfig") for query in queries)


def test_rocm_toolchain_prefers_highest_versioned_sdk_root(tmp_path: Path) -> None:
    """Among /opt/rocm-<version> installs the highest version wins."""
    older = _fake_sdk_root(tmp_path, version="7.1.0")
    newer = _fake_sdk_root(tmp_path, version="7.2.4")
    queries: list[list[str]] = []

    def fake_check_output(cmd, *args, **kwargs):
        queries.append(list(cmd))
        if cmd[1] == "-R":
            return f"{newer}\n"
        if cmd[1] == "-l":
            return f"{newer / 'lib' / 'llvm' / 'bin'}\n"
        return ""

    with patch.dict("src.linux.llama_builder.os.environ", {"HIP_PATH": ""}), \
         patch("src.linux.llama_builder._ROCM_SDK_SEARCH_DIR", new=tmp_path), \
         patch("src.linux.llama_builder._ROCM_DEFAULT_SDK_ROOT", new=tmp_path / "no-rocm"), \
         patch("src.linux.llama_builder.subprocess.check_output", side_effect=fake_check_output):
        toolchain = linux_llama_builder._resolve_rocm_toolchain()

    assert toolchain.root == newer
    assert toolchain.root != older
    assert queries[0][0] == str(newer / "bin" / "hipconfig")


def test_rocm_toolchain_falls_back_to_path_hipconfig_without_sdk(tmp_path: Path) -> None:
    """With no SDK root available the builder keeps the PATH hipconfig
    behaviour, but flags the result as not SDK-coherent."""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    distro_root = _fake_distro_rocm_root(tmp_path)
    path_hipconfig = distro_root / "bin" / "hipconfig"
    queries: list[list[str]] = []

    def fake_check_output(cmd, *args, **kwargs):
        queries.append(list(cmd))
        if cmd[1] == "-R":
            return f"{distro_root}\n"
        if cmd[1] == "-l":
            return f"{distro_root / 'lib' / 'llvm-21' / 'bin'}\n"
        return ""

    with patch.dict("src.linux.llama_builder.os.environ", {"HIP_PATH": ""}), \
         patch("src.linux.llama_builder._ROCM_SDK_SEARCH_DIR", new=empty_dir), \
         patch("src.linux.llama_builder._ROCM_DEFAULT_SDK_ROOT", new=tmp_path / "no-rocm"), \
         patch("src.linux.llama_builder.shutil.which", return_value=str(path_hipconfig)), \
         patch("src.linux.llama_builder.subprocess.check_output", side_effect=fake_check_output):
        toolchain = linux_llama_builder._resolve_rocm_toolchain()

    assert toolchain.sdk_coherent is False
    assert toolchain.hip_path == str(distro_root)
    assert toolchain.hipcxx == f"{distro_root / 'lib' / 'llvm-21' / 'bin'}/clang"
    assert "PATH hipconfig" in toolchain.source
    assert queries
    assert all(query[0] == str(path_hipconfig) for query in queries)


def test_rocm_toolchain_summary_reports_root_hipcxx_and_coherence(tmp_path: Path) -> None:
    """The operator must see the resolved root, the HIPCXX in use and whether
    the toolchain is SDK-coherent."""
    sdk_root = _fake_sdk_root(tmp_path)

    def fake_check_output(cmd, *args, **kwargs):
        if cmd[1] == "-R":
            return f"{sdk_root}\n"
        if cmd[1] == "-l":
            return f"{sdk_root / 'lib' / 'llvm' / 'bin'}\n"
        return ""

    messages: list[str] = []

    with patch.dict("src.linux.llama_builder.os.environ", {"HIP_PATH": ""}), \
         patch("src.linux.llama_builder._ROCM_SDK_SEARCH_DIR", new=tmp_path), \
         patch("src.linux.llama_builder._ROCM_DEFAULT_SDK_ROOT", new=tmp_path / "no-rocm"), \
         patch("src.linux.llama_builder.subprocess.check_output", side_effect=fake_check_output), \
         patch("src.linux.llama_builder.print_info", side_effect=messages.append):
        builder = _hip_builder(tmp_path)
        toolchain = builder._rocm_toolchain()

    assert toolchain.sdk_coherent is True
    assert any(str(sdk_root) in message for message in messages)
    assert any("HIPCXX=" in message for message in messages)
    assert any("SDK-coherent=yes" in message for message in messages)
