from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from src.config import GillsystemsAIStackUpdaterConfig, load_config
from src.linux.llama_builder import LlamaBuilderLinux


def _make_cfg(tmp_path: Path) -> GillsystemsAIStackUpdaterConfig:
    cfg = load_config()
    cfg.behavior.dry_run = False
    cfg.paths.llama_cpp_source = str(tmp_path / "llama.cpp")
    cfg.paths.llama_cpp_install_linux = str(tmp_path / "install-root")
    return cfg


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