from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

PRODUCTION_LAUNCHERS = {
    "executables/Gillsystems_Main_AI_Server.bat": "2048",
    "executables/Gillsystems-HTPC-AI-server.sh": "1536",
    "executables/Gillsystems_Laptop_4500U_Vega6_server.bat": "1024",
    "executables/Gillsystems_SteamDeck_AI_Server.sh": "1024",
}


def _read_workspace_file(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_production_launchers_use_gemma_chat_template() -> None:
    for relative_path in PRODUCTION_LAUNCHERS:
        launcher_text = _read_workspace_file(relative_path)

        assert "gemma" in launcher_text, relative_path
        assert "--jinja" in launcher_text, relative_path
        assert "--chat-template" in launcher_text, relative_path


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
    required_flags = ("--context-shift", "--metrics", "--no-mmap")

    for relative_path in PRODUCTION_LAUNCHERS:
        launcher_text = _read_workspace_file(relative_path)

        for required_flag in required_flags:
            assert required_flag in launcher_text, f"{relative_path} missing {required_flag}"


def test_main_launcher_uses_google_sampling_profile() -> None:
    launcher_text = _read_workspace_file("executables/Gillsystems_Main_AI_Server.bat")

    assert '--temperature 1.0 ^' in launcher_text
    assert '--top-k 64 ^' in launcher_text
    assert '--top-p 0.95 ^' in launcher_text
    assert '--min-p 0.05 ^' in launcher_text
    assert '--repeat-penalty 1.15 ^' in launcher_text
    assert '--repeat-last-n 128 ^' in launcher_text
    assert '--reasoning-format none ^' in launcher_text
    assert '--chat-template gemma ^' in launcher_text
    assert '--context-shift ^' in launcher_text


def test_main_launcher_supports_fixed_main_path_and_override() -> None:
    launcher_text = _read_workspace_file("executables/Gillsystems_Main_AI_Server.bat")

    assert 'set "MODEL_PATH=C:\\Models\\gemma-4-31B.Q4_K_M.gguf"' in launcher_text
    assert 'GILLSYSTEMS_MAIN_MODEL_PATH' in launcher_text


def test_main_launcher_resolves_python_without_repo_venv() -> None:
    launcher_text = _read_workspace_file("executables/Gillsystems_Main_AI_Server.bat")

    assert 'GILLSYSTEMS_MAIN_PYTHON' in launcher_text
    assert 'if not defined PYTHON_EXE if exist "%REPO_ROOT%\\.venv\\Scripts\\python.exe" set "PYTHON_EXE=%REPO_ROOT%\\.venv\\Scripts\\python.exe"' in launcher_text
    assert "where python.exe" in launcher_text
    assert "where py.exe" in launcher_text
    assert '"%PYTHON_EXE%" %PYTHON_ARGS% --version >nul 2>&1' in launcher_text


def test_main_launcher_uses_json_export_proxy_with_main_prefix() -> None:
    launcher_text = _read_workspace_file("executables/Gillsystems_Main_AI_Server.bat")
    proxy_text = _read_workspace_file("scripts/llama_json_proxy.py")

    assert 'set "NODE_PREFIX=gillsystems_cluster-main"' in launcher_text
    assert 'scripts\\llama_json_proxy.py' in launcher_text
    assert '--port %UPSTREAM_PORT% ^' in launcher_text
    assert '--log-file "%SERVER_LOG%" ^' in launcher_text
    assert 'pause' in launcher_text

    assert 'class ConversationExporter' in proxy_text
    assert 'ThreadingHTTPServer' in proxy_text
    assert '_conv_' in proxy_text


def test_main_launcher_does_not_reference_jinja_file() -> None:
    """Round 6 fix: Main no longer uses --chat-template-file with a non-existent Jinja file."""
    launcher_text = _read_workspace_file("executables/Gillsystems_Main_AI_Server.bat")

    assert "--chat-template-file" not in launcher_text
    assert "gillsystems_gemma4.jinja" not in launcher_text
    assert "JINJA_FILE" not in launcher_text


def test_production_launchers_pass_repeat_penalty() -> None:
    """Round 6 fix: --repeat-penalty and --repeat-last-n must be passed to the server."""
    for relative_path in PRODUCTION_LAUNCHERS:
        launcher_text = _read_workspace_file(relative_path)

        assert "repeat-penalty" in launcher_text, relative_path
        assert "repeat-last-n" in launcher_text, relative_path
        assert "1.15" in launcher_text, relative_path
        assert "128" in launcher_text, relative_path


def test_production_launchers_pass_batch_and_ubatch() -> None:
    """All 4 launchers must pass -b 2048 and -ub 512 to the server."""
    for relative_path in PRODUCTION_LAUNCHERS:
        launcher_text = _read_workspace_file(relative_path)

        assert "2048" in launcher_text, relative_path
        assert "512" in launcher_text, relative_path


def test_htpc_launcher_no_broken_line_continuation() -> None:
    """Round 6 fix: HTPC bash script must not have blank lines inside continuation chain."""
    launcher_text = _read_workspace_file("executables/Gillsystems-HTPC-AI-server.sh")

    # Verify the launch command is a single coherent block
    assert '--no-mmap 2>&1 | tee -a "$LOG_FILE"' in launcher_text

    # Check no blank lines exist between --top-p and --metrics
    lines = launcher_text.splitlines()
    in_launch_block = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == 'set +e':
            in_launch_block = True
            continue
        if in_launch_block and stripped.startswith('exit'):
            break
        if in_launch_block and stripped == '':
            # Check if previous line had backslash continuation
            if i > 0 and lines[i - 1].rstrip().endswith('\\'):
                raise AssertionError(
                    f"HTPC launcher has blank line at line {i + 1} inside backslash "
                    f"continuation chain (between line {i}: '{lines[i - 1].strip()}' "
                    f"and line {i + 2}: '{lines[i + 1].strip() if i + 1 < len(lines) else ''}')"
                )