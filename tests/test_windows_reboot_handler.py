from __future__ import annotations

from src.config import load_config
from src.windows.reboot_handler import RebootHandler


def test_reboot_handler_uses_node_scoped_task_name() -> None:
    cfg = load_config()

    handler = RebootHandler(cfg)

    assert handler.task_name.startswith("GillsystemsAIStackUpdaterResumeTask-")
    assert handler.node_id in handler.task_name