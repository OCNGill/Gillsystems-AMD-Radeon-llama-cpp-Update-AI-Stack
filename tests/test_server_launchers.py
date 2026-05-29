from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

PRODUCTION_LAUNCHERS = {
    "executables/server_primary_hip_windows.bat": "2048",
    "executables/server_desktop_rocm_linux.sh": "1536",
    "executables/server_mobile_uma_windows.bat": "1024",
    "executables/server_deck_vulkan_linux.sh": "1024",
}


def _read_workspace_file(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_production_launchers_use_gemma_chat_template() -> None:
    for relative_path in PRODUCTION_LAUNCHERS:
        launcher_text = _read_workspace_file(relative_path)

        assert "gemma" in launcher_text, relative_path
        assert "--jinja" in launcher_text, relative_path
        # --chat-template overrides the GGUF-embedded Gemma 4 Jinja template with
        # the old Gemma 2/3 built-in template, breaking prompt construction (prompt_n=3).
        assert "--chat-template" not in launcher_text, f"{relative_path} must not use --chat-template"


def test_production_launchers_cap_generation_length() -> None:
    for relative_path, expected_cap in PRODUCTION_LAUNCHERS.items():
        launcher_text = _read_workspace_file(relative_path)

        assert "-n" in launcher_text, relative_path
        assert expected_cap in launcher_text, relative_path


def test_production_launchers_do_not_use_reverse_prompt_stop_hack() -> None:
    for relative_path in PRODUCTION_LAUNCHERS:
        launcher_text = _read_workspace_file(relative_path)

        assert '-r "<|im_end|>"' not in launcher_text, relative_path
        assert '-r "<|im_start|>"' not in launcher_text, relative_path
        assert "--reverse-prompt" not in launcher_text, relative_path


def test_production_launchers_keep_core_runtime_safeguards() -> None:
    required_flags = ("--reasoning-format", "--metrics", "--no-mmap")

    for relative_path in PRODUCTION_LAUNCHERS:
        launcher_text = _read_workspace_file(relative_path)

        for required_flag in required_flags:
            assert required_flag in launcher_text, f"{relative_path} missing {required_flag}"


def test_main_launcher_uses_google_sampling_profile() -> None:
    launcher_text = _read_workspace_file("executables/server_primary_hip_windows.bat")

    assert '--temperature 1.0 ^' in launcher_text
    assert '--top-k 64 ^' in launcher_text
    assert '--top-p 0.95 ^' in launcher_text
    assert '--min-p 0.05 ^' in launcher_text
    assert '--reasoning-format none ^' in launcher_text
    assert '--chat-template gemma ^' not in launcher_text
    assert '--context-shift ^' not in launcher_text
    assert '--repeat-penalty 1.15 ^' in launcher_text
    assert '--repeat-last-n 128 ^' in launcher_text


def test_main_launcher_supports_fixed_main_path_and_override() -> None:
    launcher_text = _read_workspace_file("executables/server_primary_hip_windows.bat")

    assert 'set "MODEL_PATH=C:\\Models\\gemma-4-31B.Q4_K_M.gguf"' in launcher_text
    assert 'GILLSYSTEMS_PRIMARY_MODEL_PATH' in launcher_text


def test_main_launcher_resolves_python_without_repo_venv() -> None:
    launcher_text = _read_workspace_file("executables/server_primary_hip_windows.bat")

    assert 'GILLSYSTEMS_PRIMARY_PYTHON' in launcher_text
    assert 'if not defined PYTHON_EXE if exist "%REPO_ROOT%\\.venv\\Scripts\\python.exe" set "PYTHON_EXE=%REPO_ROOT%\\.venv\\Scripts\\python.exe"' in launcher_text
    assert "where python.exe" in launcher_text
    assert "where py.exe" in launcher_text
    assert '"%PYTHON_EXE%" %PYTHON_ARGS% --version >nul 2>&1' in launcher_text


def test_main_launcher_uses_json_export_proxy_with_main_prefix() -> None:
    launcher_text = _read_workspace_file("executables/server_primary_hip_windows.bat")
    proxy_text = _read_workspace_file("scripts/llama_json_proxy.py")

    assert 'set "NODE_PREFIX=gillsystems_cluster-primary"' in launcher_text
    assert 'scripts\\llama_json_proxy.py' in launcher_text
    assert '--port %UPSTREAM_PORT% ^' in launcher_text
    assert '--log-file "%SERVER_LOG%" ^' in launcher_text
    assert 'pause' in launcher_text

    assert 'class ConversationExporter' in proxy_text
    assert 'ThreadingHTTPServer' in proxy_text
    assert '_conv_' in proxy_text