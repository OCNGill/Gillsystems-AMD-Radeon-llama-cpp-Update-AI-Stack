from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from src.config import load_config


def test_state_dir_is_scoped_by_platform_and_node_when_root_only() -> None:
    cfg = load_config()
    cfg.paths.state_dir = "state"

    with patch(
        "src.config.get_runtime_identity",
        return_value={"platform": "linux", "distro": "steamos", "node": "steam-deck"},
    ):
        assert cfg.paths.resolve_state_dir() == Path("state") / "linux" / "steam-deck"


def test_state_dir_respects_runtime_templates() -> None:
    cfg = load_config()
    cfg.paths.state_dir = "state/{platform}/{node}"

    with patch(
        "src.config.resolve_runtime_path",
        return_value=Path("state") / "windows" / "gillsystems-main",
    ):
        assert cfg.paths.resolve_state_dir() == Path("state") / "windows" / "gillsystems-main"