from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

PRODUCTION_LAUNCHERS = {
    "executables/Gillsystems_Main_AI_Server.bat": "2048",
    "executables/Gillsystems-HTPC-AI-server.sh": "1536",
    "executables/Gillsystems_Laptop_4500U_Vega6_server.bat": "1024",
    "executables/Gillsystems_SteamDeck_AI_Server.sh": "1024",
}


def _read_launcher(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_production_launchers_use_gemma_chat_template() -> None:
    for relative_path in PRODUCTION_LAUNCHERS:
        launcher_text = _read_launcher(relative_path)

        assert "--chat-template" in launcher_text, relative_path
        assert "gemma" in launcher_text, relative_path
        assert "--jinja" in launcher_text, relative_path


def test_production_launchers_cap_generation_length() -> None:
    for relative_path, expected_cap in PRODUCTION_LAUNCHERS.items():
        launcher_text = _read_launcher(relative_path)

        assert "-n" in launcher_text, relative_path
        assert expected_cap in launcher_text, relative_path


def test_production_launchers_do_not_use_reverse_prompt_stop_hack() -> None:
    for relative_path in PRODUCTION_LAUNCHERS:
        launcher_text = _read_launcher(relative_path)

        assert "--reverse-prompt" not in launcher_text, relative_path
        assert "<|im_end|>,<|im_start|>" not in launcher_text, relative_path


def test_production_launchers_keep_core_runtime_safeguards() -> None:
    required_flags = ("--context-shift", "--metrics", "--no-mmap")

    for relative_path in PRODUCTION_LAUNCHERS:
        launcher_text = _read_launcher(relative_path)

        for required_flag in required_flags:
            assert required_flag in launcher_text, f"{relative_path} missing {required_flag}"