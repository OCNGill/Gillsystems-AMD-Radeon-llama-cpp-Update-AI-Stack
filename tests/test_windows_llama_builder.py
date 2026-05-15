from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from src.config import GillsystemsAIStackUpdaterConfig, load_config
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