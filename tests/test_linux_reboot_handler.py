from __future__ import annotations

from src.config import load_config
from src.linux.reboot_handler import RebootHandler


def test_reboot_handler_uses_node_scoped_service_name() -> None:
    cfg = load_config()

    handler = RebootHandler(cfg)

    assert handler.service_name.startswith("gillsystems-ai-stack-updater-resume-")
    assert handler.service_name.endswith(".service")
    assert handler.node_id in handler.service_name
    assert handler.service_path.name == handler.service_name