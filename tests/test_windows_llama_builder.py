from __future__ import annotations

import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.config import GillsystemsAIStackUpdaterConfig, load_config
from src.windows import llama_builder as windows_llama_builder
from src.windows.llama_builder import LlamaBuilderWindows


def _make_cfg(tmp_path: Path) -> GillsystemsAIStackUpdaterConfig:
    cfg = load_config()
    cfg.behavior.dry_run = False
    cfg.behavior.force = False
    cfg.paths.llama_cpp_source = str(tmp_path / "llama.cpp")
    cfg.paths.llama_cpp_install_windows = str(tmp_path / "install")
    return cfg


def _fake_which(hip_root: Path):
    def _inner(tool: str) -> str | None:
        if tool == "hipcc":
            return str(hip_root / "bin" / "hipcc.exe")
        return None

    return _inner


def test_configure_cmake_disables_rocwmma_when_header_missing(tmp_path: Path) -> None:
    cfg = _make_cfg(tmp_path)
    builder = LlamaBuilderWindows(cfg, ["gfx1100"])
    builder._use_ninja = True

    hip_root = tmp_path / "rocm"
    (hip_root / "bin").mkdir(parents=True)

    captured: list[list[str]] = []

    with patch("src.windows.llama_builder.shutil.which", side_effect=_fake_which(hip_root)), \
         patch("src.windows.llama_builder._find_hip_path", return_value=str(hip_root)), \
         patch("src.windows.llama_builder._run", side_effect=lambda cmd, timeout=3600, env=None: captured.append(cmd)):
        builder._configure_cmake()

    assert captured
    assert "-DGGML_HIP_ROCWMMA_FATTN=OFF" in captured[0]
    assert "-DGGML_HIP_ROCWMMA_FATTN=ON" not in captured[0]
    assert "-DGGML_VULKAN=ON" not in captured[0]


def test_configure_cmake_enables_rocwmma_when_header_exists(tmp_path: Path) -> None:
    cfg = _make_cfg(tmp_path)
    builder = LlamaBuilderWindows(cfg, ["gfx1100"])
    builder._use_ninja = True

    hip_root = tmp_path / "rocm"
    header = hip_root / "include" / "rocwmma" / "rocwmma-version.hpp"
    header.parent.mkdir(parents=True)
    header.write_text("// stub header\n", encoding="ascii")
    (hip_root / "bin").mkdir(parents=True, exist_ok=True)

    captured: list[list[str]] = []

    with patch("src.windows.llama_builder.shutil.which", side_effect=_fake_which(hip_root)), \
         patch("src.windows.llama_builder._find_hip_path", return_value=str(hip_root)), \
         patch("src.windows.llama_builder._run", side_effect=lambda cmd, timeout=3600, env=None: captured.append(cmd)):
        builder._configure_cmake()

    assert captured
    assert "-DGGML_HIP_ROCWMMA_FATTN=ON" in captured[0]
    assert "-DGGML_VULKAN=ON" not in captured[0]


def test_configure_cmake_enables_vulkan_with_sdk_cmake_prefix(tmp_path: Path) -> None:
    cfg = _make_cfg(tmp_path)
    builder = LlamaBuilderWindows(cfg, ["gfx1033"])
    builder._use_ninja = True

    vulkan_sdk = tmp_path / "VulkanSDK" / "1.4.335.0"
    spirv_cfg = vulkan_sdk / "Lib" / "cmake" / "SPIRV-Headers" / "SPIRV-HeadersConfig.cmake"
    spirv_cfg.parent.mkdir(parents=True)
    spirv_cfg.write_text("# stub config\n", encoding="ascii")

    captured: list[list[str]] = []

    with patch("src.windows.llama_builder.shutil.which", return_value=None), \
         patch("src.windows.llama_builder._find_vulkan_sdk_path", return_value=str(vulkan_sdk)), \
         patch.dict("src.windows.llama_builder.os.environ", {}, clear=True), \
         patch("src.windows.llama_builder._run", side_effect=lambda cmd, timeout=3600, env=None: captured.append(cmd)):
        builder._configure_cmake()

    assert captured
    assert "-DGGML_VULKAN=ON" in captured[0]
    assert f"-DCMAKE_PREFIX_PATH={vulkan_sdk / 'Lib' / 'cmake'}" in captured[0]
    assert "-DGGML_HIP=ON" not in captured[0]


def test_configure_cmake_raises_when_vulkan_sdk_cmake_prefix_missing(tmp_path: Path) -> None:
    cfg = _make_cfg(tmp_path)
    builder = LlamaBuilderWindows(cfg, ["gfx1033"])
    builder._use_ninja = True

    vulkan_sdk = tmp_path / "VulkanSDK" / "1.4.335.0"
    vulkan_sdk.mkdir(parents=True)

    with patch("src.windows.llama_builder.shutil.which", return_value=None), \
         patch("src.windows.llama_builder._find_vulkan_sdk_path", return_value=str(vulkan_sdk)), \
         patch.dict("src.windows.llama_builder.os.environ", {}, clear=True):
        with pytest.raises(RuntimeError, match="SPIRV-HeadersConfig.cmake"):
            builder._configure_cmake()


def test_bundle_hip_runtime_libraries_copies_matching_dlls(tmp_path: Path) -> None:
    hip_root = tmp_path / "rocm"
    hip_bin = hip_root / "bin"
    hip_bin.mkdir(parents=True)

    for dll_name in ("libhipblas.dll", "rocblas.dll", "amdhip64_7.dll"):
        (hip_bin / dll_name).write_text("stub\n", encoding="ascii")
    (hip_bin / "clang.dll").write_text("stub\n", encoding="ascii")

    install_bin = tmp_path / "install" / "bin"

    copied = windows_llama_builder._bundle_hip_runtime_libraries(str(hip_root), install_bin)

    assert copied == 3
    assert (install_bin / "libhipblas.dll").exists()
    assert (install_bin / "rocblas.dll").exists()
    assert (install_bin / "amdhip64_7.dll").exists()
    assert not (install_bin / "clang.dll").exists()


def test_bundle_rocblas_runtime_support_copies_tensile_library_tree(tmp_path: Path) -> None:
    hip_root = tmp_path / "rocm"
    rocblas_library = hip_root / "bin" / "rocblas" / "library"
    rocblas_library.mkdir(parents=True)
    (rocblas_library / "TensileLibrary_lazy_gfx1100.dat").write_text("stub\n", encoding="ascii")

    arch_dir = rocblas_library / "gfx1100"
    arch_dir.mkdir(parents=True)
    (arch_dir / "kernel.co").write_text("stub\n", encoding="ascii")

    install_bin = tmp_path / "install" / "bin"

    bundled = windows_llama_builder._bundle_rocblas_runtime_support(str(hip_root), install_bin)

    assert bundled == install_bin / "rocblas" / "library"
    assert (install_bin / "rocblas" / "library" / "TensileLibrary_lazy_gfx1100.dat").exists()
    assert (install_bin / "rocblas" / "library" / "gfx1100" / "kernel.co").exists()


def test_validate_uses_runtime_dirs_and_skips_failed_exit_codes(tmp_path: Path) -> None:
    cfg = _make_cfg(tmp_path)
    builder = LlamaBuilderWindows(cfg, ["gfx1100"])

    install_bin = Path(cfg.paths.llama_cpp_install_windows) / "bin"
    install_bin.mkdir(parents=True)
    (install_bin / "llama-cli.exe").write_text("stub\n", encoding="ascii")
    (install_bin / "llama-server.exe").write_text("stub\n", encoding="ascii")
    (install_bin / "rocblas" / "library").mkdir(parents=True)

    hip_root = tmp_path / "rocm"
    (hip_root / "bin").mkdir(parents=True)

    calls: list[tuple[list[str], dict]] = []
    results = [
        MagicMock(returncode=126, stdout="", stderr="libhipblas.dll missing"),
        MagicMock(returncode=0, stdout="llama-server build 1\n", stderr=""),
        MagicMock(returncode=0, stdout="--spec-type\n draft-mtp\n", stderr=""),
    ]

    def _fake_run(cmd: list[str], **kwargs):
        calls.append((cmd, kwargs))
        return results[len(calls) - 1]

    with patch("src.windows.llama_builder._find_hip_path", return_value=str(hip_root)), \
         patch("src.windows.llama_builder.subprocess.run", side_effect=_fake_run):
        builder._validate()

    assert len(calls) == 3
    assert calls[0][0][0].endswith("llama-cli.exe")
    assert calls[1][0][0].endswith("llama-server.exe")
    assert calls[2][0][0].endswith("llama-server.exe")
    assert calls[2][0][1] == "--help"

    runtime_path = calls[0][1]["env"]["PATH"].split(";")
    assert runtime_path[0] == str(install_bin)
    assert str(hip_root / "bin") in runtime_path
    assert calls[0][1]["env"]["ROCBLAS_TENSILE_LIBPATH"] == str(install_bin / "rocblas" / "library")


def test_append_to_user_path_updates_current_process_and_registry_once(tmp_path: Path) -> None:
    new_dir = str(tmp_path / "install" / "bin")
    registry_state = {"Path": r"C:\Existing\Bin"}

    fake_winreg = types.SimpleNamespace(
        HKEY_CURRENT_USER=object(),
        KEY_QUERY_VALUE=1,
        KEY_SET_VALUE=2,
        REG_EXPAND_SZ=3,
    )

    def _open_key(*args, **kwargs):
        return object()

    def _query_value_ex(key, name):
        return registry_state[name], fake_winreg.REG_EXPAND_SZ

    def _set_value_ex(key, name, reserved, reg_type, value):
        registry_state[name] = value

    fake_winreg.OpenKey = _open_key
    fake_winreg.QueryValueEx = _query_value_ex
    fake_winreg.SetValueEx = _set_value_ex
    fake_winreg.CloseKey = lambda key: None

    with patch.dict("src.windows.llama_builder.os.environ", {"PATH": r"C:\Existing\Bin"}, clear=True), \
         patch.dict("sys.modules", {"winreg": fake_winreg}):
        windows_llama_builder._append_to_user_path(new_dir)
        windows_llama_builder._append_to_user_path(new_dir)

        process_paths = windows_llama_builder.os.environ["PATH"].split(";")
        registry_paths = registry_state["Path"].split(";")

    assert process_paths[0] == new_dir
    assert process_paths.count(new_dir) == 1
    assert registry_paths[-1] == new_dir
    assert registry_paths.count(new_dir) == 1


def test_mirror_install_bin_tree_replaces_source_bin_contents(tmp_path: Path) -> None:
    install_bin = tmp_path / "install" / "bin"
    install_bin.mkdir(parents=True)
    (install_bin / "llama-server.exe").write_text("server\n", encoding="ascii")
    (install_bin / "ggml-vulkan.dll").write_text("dll\n", encoding="ascii")

    source_bin = tmp_path / "llama.cpp" / "bin"
    source_bin.mkdir(parents=True)
    (source_bin / "stale.exe").write_text("stale\n", encoding="ascii")

    mirrored = windows_llama_builder._mirror_install_bin_tree(install_bin, source_bin)

    assert mirrored == source_bin
    assert (source_bin / "llama-server.exe").exists()
    assert (source_bin / "ggml-vulkan.dll").exists()
    assert not (source_bin / "stale.exe").exists()