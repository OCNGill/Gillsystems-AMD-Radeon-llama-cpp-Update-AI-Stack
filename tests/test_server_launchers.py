from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]

PRODUCTION_LAUNCHERS = {
    "executables/Gillsystems_Main_AI_Server.bat": "2048",
    "executables/Gillsystems-HTPC-AI-server.sh": "1536",
    "executables/Gillsystems_Laptop_4500U_Vega6_server.bat": "1024",
    "executables/Gillsystems_SteamDeck_AI_Server.sh": "1024",
}


def _read_launcher(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _assert_setting(launcher_text: str, name: str, value: str, *, windows: bool) -> None:
    if windows:
        pattern = rf'^set "{re.escape(name)}={re.escape(value)}"$'
    else:
        pattern = rf'^{re.escape(name)}="{re.escape(value)}"$'

    assert re.search(pattern, launcher_text, re.MULTILINE), f"missing {name}={value}"


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


def test_production_launchers_use_deterministic_google_tuned_profile() -> None:
    for relative_path in PRODUCTION_LAUNCHERS:
        launcher_text = _read_launcher(relative_path)
        windows = relative_path.endswith(".bat")

        _assert_setting(launcher_text, "TEMPERATURE", "0", windows=windows)
        _assert_setting(launcher_text, "MIN_P", "0.05", windows=windows)
        _assert_setting(launcher_text, "TOP_K", "20", windows=windows)
        _assert_setting(launcher_text, "TOP_P", "1.0", windows=windows)

        assert "--min-p" in launcher_text, relative_path


def test_production_launchers_support_model_path_overrides() -> None:
    expected_markers = {
        "executables/Gillsystems_Main_AI_Server.bat": ("GILLSYSTEMS_MAIN_MODEL_PATH", "Working_Models"),
        "executables/Gillsystems-HTPC-AI-server.sh": ("GILLSYSTEMS_HTPC_MODEL_PATH",),
        "executables/Gillsystems_Laptop_4500U_Vega6_server.bat": ("GILLSYSTEMS_LAPTOP_MODEL_PATH",),
        "executables/Gillsystems_SteamDeck_AI_Server.sh": ("GILLSYSTEMS_STEAMDECK_MODEL_PATH",),
    }

    for relative_path, markers in expected_markers.items():
        launcher_text = _read_launcher(relative_path)

        for marker in markers:
            assert marker in launcher_text, f"{relative_path} missing {marker}"