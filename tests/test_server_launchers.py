from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]

PRODUCTION_LAUNCHERS = {
    "executables/server_primary_hip_windows.bat": "2048",
    "executables/server_desktop_rocm_linux.sh": "1536",
    "executables/server_mobile_uma_windows.bat": "1024",
    "executables/server_deck_vulkan_linux.sh": "1024",
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
        "executables/server_primary_hip_windows.bat": ("GILLSYSTEMS_PRIMARY_MODEL_PATH", "Working_Models"),
        "executables/server_desktop_rocm_linux.sh": ("GILLSYSTEMS_DESKTOP_MODEL_PATH",),
        "executables/server_mobile_uma_windows.bat": ("GILLSYSTEMS_MOBILE_MODEL_PATH",),
        "executables/server_deck_vulkan_linux.sh": ("GILLSYSTEMS_DECK_MODEL_PATH",),
    }

    for relative_path, markers in expected_markers.items():
        launcher_text = _read_launcher(relative_path)

        for marker in markers:
            assert marker in launcher_text, f"{relative_path} missing {marker}"


def test_main_launcher_keeps_a_debug_window_open_and_stringifies_errors() -> None:
    launcher_text = _read_launcher("executables/server_primary_hip_windows.bat")

    assert "cmd.exe /k" in launcher_text
    assert "--gillsystems-primary-child-window" in launcher_text
    assert "ForEach-Object { $_.ToString() }" in launcher_text
    assert "UNHANDLED POWERSHELL ERROR" in launcher_text