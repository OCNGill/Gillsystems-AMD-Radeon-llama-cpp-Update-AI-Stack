from __future__ import annotations

import os
import subprocess
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


def _make_dir_link(link: Path, target: Path) -> bool:
    """Create a directory junction (Windows) or symlink (POSIX) at *link* -> *target*."""
    link.parent.mkdir(parents=True, exist_ok=True)
    target.mkdir(parents=True, exist_ok=True)

    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return True

    try:
        os.symlink(target, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        return False
    return True


def _install_builder(builder: LlamaBuilderWindows) -> list[list[str]]:
    """Run builder._install() with every side effect stubbed out."""
    captured: list[list[str]] = []

    with patch.dict("src.windows.llama_builder.os.environ", {}, clear=True), \
         patch("src.windows.llama_builder._find_hip_path", return_value=None), \
         patch("src.windows.llama_builder._append_to_user_path"), \
         patch("src.windows.llama_builder._run",
               side_effect=lambda cmd, timeout=3600, env=None: captured.append(cmd)):
        builder._install()

    return captured


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

    def fake_run(cmd, timeout=3600, env=None):
        captured.append(list(cmd))
        # A real cmake configure always writes a cache; the builder reads it
        # back to prove HIP is still enabled.
        builder.build_dir.mkdir(parents=True, exist_ok=True)
        (builder.build_dir / "CMakeCache.txt").write_text(
            "GGML_HIP:BOOL=ON\n", encoding="utf-8"
        )
        return 0

    with patch("src.windows.llama_builder.shutil.which", side_effect=_fake_which(hip_root)), \
         patch("src.windows.llama_builder._find_hip_path", return_value=str(hip_root)), \
         patch("src.windows.llama_builder._run", side_effect=fake_run):
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

    def fake_run(cmd, timeout=3600, env=None):
        captured.append(list(cmd))
        # A real cmake configure always writes a cache; the builder reads it
        # back to prove HIP is still enabled.
        builder.build_dir.mkdir(parents=True, exist_ok=True)
        (builder.build_dir / "CMakeCache.txt").write_text(
            "GGML_HIP:BOOL=ON\n", encoding="utf-8"
        )
        return 0

    with patch("src.windows.llama_builder.shutil.which", side_effect=_fake_which(hip_root)), \
         patch("src.windows.llama_builder._find_hip_path", return_value=str(hip_root)), \
         patch("src.windows.llama_builder._run", side_effect=fake_run):
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


def test_backend_selection_uses_separate_build_dirs_for_hip_and_vulkan(tmp_path: Path) -> None:
    cfg = _make_cfg(tmp_path)
    builder = LlamaBuilderWindows(cfg, ["gfx1033"])

    with patch("src.windows.llama_builder.shutil.which", return_value=None):
        builder._refresh_backend_selection()
        assert builder.build_dir == Path(cfg.paths.llama_cpp_source) / "build-vulkan-win"

    hip_root = tmp_path / "rocm"
    with patch("src.windows.llama_builder.shutil.which", side_effect=_fake_which(hip_root)):
        builder._refresh_backend_selection()
        assert builder.build_dir == Path(cfg.paths.llama_cpp_source) / "build-hip-win"


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


def test_install_keeps_build_tree_binaries_when_install_prefix_is_build_dir(tmp_path: Path) -> None:
    """The install step must never rename binaries that live in the build tree.

    Regression test for the confirmed 2026-10-21 incident: the install prefix
    pointed at the build output dir, so unlocking "*.exe" renamed the freshly
    built binaries and `cmake --install` then failed with
    "file INSTALL cannot find .../build-hip-win/bin/test-tokenizer-0.exe".
    """
    cfg = _make_cfg(tmp_path)
    builder = LlamaBuilderWindows(cfg, ["gfx1100"])

    build_dir = tmp_path / "build-hip-win"
    build_bin = build_dir / "bin"
    build_bin.mkdir(parents=True)
    (build_bin / "test-tokenizer-0.exe").write_text("stub\n", encoding="ascii")

    builder.build_dir = build_dir
    builder.install_dir = build_dir

    _install_builder(builder)

    assert (build_bin / "test-tokenizer-0.exe").exists()
    assert not (build_bin / "test-tokenizer-0.exe.old").exists()


def test_install_removes_junction_install_bin_and_keeps_build_outputs(tmp_path: Path) -> None:
    """A junction install bin must be replaced by a real directory.

    The junction is the exact shape of the 2026-10-21 failure: install\\bin was
    a directory junction pointing at build-hip-win\\bin.
    """
    cfg = _make_cfg(tmp_path)
    builder = LlamaBuilderWindows(cfg, ["gfx1100"])

    build_dir = tmp_path / "build-hip-win"
    build_bin = build_dir / "bin"
    build_bin.mkdir(parents=True)
    (build_bin / "test-tokenizer-0.exe").write_text("stub\n", encoding="ascii")

    install_dir = tmp_path / "install"
    install_bin = install_dir / "bin"
    if not _make_dir_link(install_bin, build_bin):
        pytest.skip("directory junctions/symlinks are not available on this platform")

    builder.build_dir = build_dir
    builder.install_dir = install_dir

    _install_builder(builder)

    assert (build_bin / "test-tokenizer-0.exe").exists()
    assert not (build_bin / "test-tokenizer-0.exe.old").exists()
    assert not windows_llama_builder._is_reparse_point(install_bin)
    assert install_bin.is_dir()


def test_install_restores_renamed_binaries_when_cmake_install_fails(tmp_path: Path) -> None:
    """A failed install must not leave renamed (.exe.old) binaries behind."""
    cfg = _make_cfg(tmp_path)
    builder = LlamaBuilderWindows(cfg, ["gfx1100"])

    install_dir = tmp_path / "install"
    install_bin = install_dir / "bin"
    install_bin.mkdir(parents=True)
    binary = install_bin / "llama-server.exe"
    binary.write_text("server\n", encoding="ascii")

    builder.build_dir = tmp_path / "build-hip-win"
    builder.install_dir = install_dir

    with patch.dict("src.windows.llama_builder.os.environ", {}, clear=True), \
         patch("src.windows.llama_builder._find_hip_path", return_value=None), \
         patch("src.windows.llama_builder._append_to_user_path"), \
         patch("src.windows.llama_builder._run", side_effect=RuntimeError("install failed")):
        with pytest.raises(RuntimeError, match="install failed"):
            builder._install()

    assert binary.exists()
    assert not (install_bin / "llama-server.exe.old").exists()


def test_install_leaves_no_exe_old_litter_after_successful_install(tmp_path: Path) -> None:
    """A successful install leaves no .exe.old files behind."""
    cfg = _make_cfg(tmp_path)
    builder = LlamaBuilderWindows(cfg, ["gfx1100"])

    install_dir = tmp_path / "install"
    install_bin = install_dir / "bin"
    install_bin.mkdir(parents=True)
    (install_bin / "llama-server.exe").write_text("old\n", encoding="ascii")

    builder.build_dir = tmp_path / "build-hip-win"
    builder.install_dir = install_dir

    def _fake_run(cmd: list[str], timeout: int = 3600, env: dict | None = None) -> None:
        (install_bin / "llama-server.exe").write_text("new\n", encoding="ascii")

    with patch.dict("src.windows.llama_builder.os.environ", {}, clear=True), \
         patch("src.windows.llama_builder._find_hip_path", return_value=None), \
         patch("src.windows.llama_builder._append_to_user_path"), \
         patch("src.windows.llama_builder._run", side_effect=_fake_run):
        builder._install()

    assert not list(install_bin.glob("*.exe.old"))
    assert (install_bin / "llama-server.exe").read_text(encoding="ascii") == "new\n"


def test_mirror_install_bin_tree_replaces_junction_source_bin(tmp_path: Path) -> None:
    """Mirroring must not follow a junction: the link is replaced by a real dir."""
    install_bin = tmp_path / "install" / "bin"
    install_bin.mkdir(parents=True)
    (install_bin / "llama-server.exe").write_text("server\n", encoding="ascii")

    link_target = tmp_path / "link-target"
    source_bin = tmp_path / "llama.cpp" / "bin"
    if not _make_dir_link(source_bin, link_target):
        pytest.skip("directory junctions/symlinks are not available on this platform")
    (link_target / "keep-me.txt").write_text("keep\n", encoding="ascii")

    mirrored = windows_llama_builder._mirror_install_bin_tree(install_bin, source_bin)

    assert mirrored == source_bin
    assert not windows_llama_builder._is_reparse_point(source_bin)
    assert (source_bin / "llama-server.exe").exists()
    assert (link_target / "keep-me.txt").exists()


def test_configure_cmake_reconfigures_when_cache_drops_hip_flag(tmp_path: Path) -> None:
    """A HIP SDK upgrade changes the compiler; CMake then wipes its cache and
    re-runs configure, which can silently lose -DGGML_HIP=ON. The builder must
    detect the CPU-only cache and re-configure from a clean cache."""
    cfg = _make_cfg(tmp_path)
    builder = LlamaBuilderWindows(cfg, ["gfx1100"])
    builder._use_ninja = True
    builder.build_dir = tmp_path / "build-hip-win"
    builder.build_dir.mkdir(parents=True, exist_ok=True)

    hip_root = tmp_path / "rocm"
    (hip_root / "bin").mkdir(parents=True)

    calls: list[list[str]] = []

    def fake_run(cmd, timeout=3600, env=None):
        calls.append(list(cmd))
        # First configure writes a CPU-only cache (the regression).
        # The re-configure (after the cache file is deleted) writes GGML_HIP=ON.
        cache = builder.build_dir / "CMakeCache.txt"
        hip_on = len(calls) > 1
        cache.write_text(
            "CMAKE_BUILD_TYPE:STRING=Release\n"
            + ("GGML_HIP:BOOL=ON\n" if hip_on else "GGML_HIP:BOOL=OFF\n"),
            encoding="utf-8",
        )
        return 0

    with patch("src.windows.llama_builder.shutil.which", side_effect=_fake_which(hip_root)), \
         patch("src.windows.llama_builder._find_hip_path", return_value=str(hip_root)), \
         patch("src.windows.llama_builder._hip_has_rocwmma", return_value=True), \
         patch("src.windows.llama_builder._build_env", return_value=None), \
         patch("src.windows.llama_builder._run", side_effect=fake_run):
        builder._configure_cmake()

    assert len(calls) == 2, f"expected a re-configure, got {len(calls)} cmake runs"
    assert "-DGGML_HIP=ON" in calls[1]


def test_configure_cmake_raises_when_hip_stays_off_after_reconfigure(tmp_path: Path) -> None:
    """If the cache still says GGML_HIP=OFF after a clean re-configure, the
    builder must refuse to build a CPU-only llama.cpp."""
    cfg = _make_cfg(tmp_path)
    builder = LlamaBuilderWindows(cfg, ["gfx1100"])
    builder._use_ninja = True
    builder.build_dir = tmp_path / "build-hip-win"
    builder.build_dir.mkdir(parents=True, exist_ok=True)

    hip_root = tmp_path / "rocm"
    (hip_root / "bin").mkdir(parents=True)

    def fake_run(cmd, timeout=3600, env=None):
        (builder.build_dir / "CMakeCache.txt").write_text(
            "GGML_HIP:BOOL=OFF\n", encoding="utf-8"
        )
        return 0

    with patch("src.windows.llama_builder.shutil.which", side_effect=_fake_which(hip_root)), \
         patch("src.windows.llama_builder._find_hip_path", return_value=str(hip_root)), \
         patch("src.windows.llama_builder._hip_has_rocwmma", return_value=True), \
         patch("src.windows.llama_builder._build_env", return_value=None), \
         patch("src.windows.llama_builder._run", side_effect=fake_run):
        with pytest.raises(RuntimeError, match="GGML_HIP=OFF"):
            builder._configure_cmake()


def test_validate_raises_when_gpu_backend_is_not_usable(tmp_path: Path) -> None:
    """A CPU-only install passes every --version check, so validation must
    prove the GPU backend actually runs a kernel before reporting success."""
    cfg = _make_cfg(tmp_path)
    builder = LlamaBuilderWindows(cfg, ["gfx1100"])
    builder.use_hip = True

    bin_dir = tmp_path / "install" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    (bin_dir / "llama-cli.exe").write_bytes(b"MZ")
    (bin_dir / "test-backend-ops.exe").write_bytes(b"MZ")

    def fake_run(cmd, **kwargs):
        if "--version" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "version: 0.7.0-dev", "")
        # GPU probe: no ROCm device found.
        return subprocess.CompletedProcess(
            cmd, 0, "Available devices:\n  CPU\n", ""
        )

    with patch.dict("src.windows.llama_builder.os.environ", {}, clear=True), \
         patch("src.windows.llama_builder._find_hip_path", return_value=None), \
         patch("src.windows.llama_builder.subprocess.run", side_effect=fake_run):
        with pytest.raises(RuntimeError, match="ROCm"):
            builder._validate()


def test_validate_accepts_a_working_gpu_backend(tmp_path: Path) -> None:
    """The positive path: a real ROCm device probe must let validation pass."""
    cfg = _make_cfg(tmp_path)
    builder = LlamaBuilderWindows(cfg, ["gfx1100"])
    builder.use_hip = True

    bin_dir = tmp_path / "install" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    (bin_dir / "llama-cli.exe").write_bytes(b"MZ")
    (bin_dir / "test-backend-ops.exe").write_bytes(b"MZ")

    def fake_run(cmd, **kwargs):
        if "--version" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "version: 0.7.0-dev", "")
        if "test-backend-ops.exe" in cmd[0]:
            return subprocess.CompletedProcess(
                cmd, 0, "Backend 0: ROCm0\n  ADD: OK\n1/1 backends passed\n", ""
            )
        return subprocess.CompletedProcess(cmd, 0, "help text", "")

    with patch.dict("src.windows.llama_builder.os.environ", {}, clear=True), \
         patch("src.windows.llama_builder._find_hip_path", return_value=None), \
         patch("src.windows.llama_builder.subprocess.run", side_effect=fake_run):
        builder._validate()


def test_configure_cmake_reconfigures_when_cache_is_unreadable(tmp_path: Path) -> None:
    """A missing/unreadable CMake cache is "unknown", never "off" and never
    "fine to ignore". The builder must re-configure and prove HIP is on."""
    cfg = _make_cfg(tmp_path)
    builder = LlamaBuilderWindows(cfg, ["gfx1100"])
    builder._use_ninja = True
    builder.build_dir = tmp_path / "build-hip-win"
    builder.build_dir.mkdir(parents=True, exist_ok=True)

    hip_root = tmp_path / "rocm"
    (hip_root / "bin").mkdir(parents=True)

    calls: list[list[str]] = []

    def fake_run(cmd, timeout=3600, env=None):
        calls.append(list(cmd))
        # First configure leaves NO cache at all (unreadable -> "unknown").
        # The re-configure writes a cache that reports GGML_HIP=ON.
        cache = builder.build_dir / "CMakeCache.txt"
        if len(calls) > 1:
            cache.write_text("GGML_HIP:BOOL=ON\n", encoding="utf-8")
        else:
            if cache.exists():
                cache.unlink()
        return 0

    with patch("src.windows.llama_builder.shutil.which", side_effect=_fake_which(hip_root)), \
         patch("src.windows.llama_builder._find_hip_path", return_value=str(hip_root)), \
         patch("src.windows.llama_builder._hip_has_rocwmma", return_value=True), \
         patch("src.windows.llama_builder._build_env", return_value=None), \
         patch("src.windows.llama_builder._run", side_effect=fake_run):
        builder._configure_cmake()

    assert len(calls) == 2, f"expected a re-configure, got {len(calls)} cmake runs"
    assert "-DGGML_HIP=ON" in calls[1]


def test_configure_cmake_raises_when_cache_stays_unknown_after_reconfigure(tmp_path: Path) -> None:
    """If the cache is still unreadable after the repair attempt, the builder
    must refuse to build rather than assume HIP is enabled."""
    cfg = _make_cfg(tmp_path)
    builder = LlamaBuilderWindows(cfg, ["gfx1100"])
    builder._use_ninja = True
    builder.build_dir = tmp_path / "build-hip-win"
    builder.build_dir.mkdir(parents=True, exist_ok=True)

    hip_root = tmp_path / "rocm"
    (hip_root / "bin").mkdir(parents=True)

    def fake_run(cmd, timeout=3600, env=None):
        cache = builder.build_dir / "CMakeCache.txt"
        if cache.exists():
            cache.unlink()
        return 0

    with patch("src.windows.llama_builder.shutil.which", side_effect=_fake_which(hip_root)), \
         patch("src.windows.llama_builder._find_hip_path", return_value=str(hip_root)), \
         patch("src.windows.llama_builder._hip_has_rocwmma", return_value=True), \
         patch("src.windows.llama_builder._build_env", return_value=None), \
         patch("src.windows.llama_builder._run", side_effect=fake_run):
        with pytest.raises(RuntimeError, match="GGML_HIP=ON"):
            builder._configure_cmake()


def test_install_raises_when_hip_backend_artifact_is_missing(tmp_path: Path) -> None:
    """A CPU-only build installs cleanly and ships no ggml-hip.dll. The
    install step must refuse to report success in that case."""
    cfg = _make_cfg(tmp_path)
    builder = LlamaBuilderWindows(cfg, ["gfx1100"])
    builder.use_hip = True
    builder.build_dir = tmp_path / "build-hip-win"
    builder.build_dir.mkdir(parents=True, exist_ok=True)
    builder.install_dir = tmp_path / "install"
    (builder.install_dir / "bin").mkdir(parents=True, exist_ok=True)

    with patch("src.windows.llama_builder._run", return_value=0), \
         patch("src.windows.llama_builder._find_hip_path", return_value=None), \
         patch("src.windows.llama_builder._mirror_install_bin_tree", return_value=None):
        with pytest.raises(RuntimeError, match="HIP backend artifact is missing"):
            builder._install()


def test_install_accepts_a_real_hip_backend_artifact(tmp_path: Path) -> None:
    """The positive path: a real ggml-hip.dll in the install tree passes."""
    cfg = _make_cfg(tmp_path)
    builder = LlamaBuilderWindows(cfg, ["gfx1100"])
    builder.use_hip = True
    builder.build_dir = tmp_path / "build-hip-win"
    builder.build_dir.mkdir(parents=True, exist_ok=True)
    builder.install_dir = tmp_path / "install"
    install_bin = builder.install_dir / "bin"
    install_bin.mkdir(parents=True, exist_ok=True)
    (install_bin / "ggml-hip.dll").write_bytes(b"MZ")

    with patch("src.windows.llama_builder._run", return_value=0), \
         patch("src.windows.llama_builder._find_hip_path", return_value=None), \
         patch("src.windows.llama_builder._mirror_install_bin_tree", return_value=None):
        builder._install()
