# Track Plan: T-001-agent-core

## Phase 1: Foundation (Design)
- [x] Analyze requirements and research ROCm/llama.cpp update paths
- [x] Define agent architecture and team roles
- [x] Create implementation plan
- [x] Finalize GPU target list and install paths (defaults set in config/default_config.yaml)

## Phase 2: Core Development (Develop)
- [x] Implement `state_manager.py` with SQLite persistence
- [x] Implement `version_intel.py` for GitHub/AMD version checks
- [x] Implement `gpu_detect.py` for architecture auto-detection
- [x] Implement `privilege.py` for UAC/sudo elevation
- [x] Implement `config.py` with Pydantic models and YAML loader
- [x] Implement `cli.py` with Rich terminal UI
- [x] Create `main.py` entry point and orchestrator logic

## Phase 3: Sub-Agent Implementation
- [x] Implement Linux `rocm_updater.py` and `llama_builder.py`
- [x] Implement Linux `reboot_handler.py` (systemd one-shot)
- [x] Implement Windows `hip_updater.py` and `llama_builder.py`
- [x] Implement Windows `reboot_handler.py` (Scheduled Task)

## Phase 4: Integration & UX
- [x] Implement `cli.py` with Rich output
- [x] Create `.bat` and `.sh` launchers
- [x] Create config/default_config.yaml
- [x] Create requirements.txt and pyproject.toml

## Phase 5: Testing (QA)
- [x] test_version_intel.py — Version detection unit tests
- [x] test_state_manager.py — SQLite checkpoint tests
- [x] test_linux_rocm.py — Linux sub-agent unit tests
- [x] test_windows_hip.py — Windows sub-agent unit tests
- [x] tests/mocks/mock_installers.py — Mock binary helpers

## Phase 6: Verification & Delivery (Document/Deliver)
- [x] Document usage in README.md
- [ ] Full live run on test Linux machine
- [ ] Full live run on test Windows machine
- [ ] Tag v1.0.0 release

## Phase 7: Post-MVP Hardening (Debug / Deliver)
_Completed 2026-05-06_
- [x] Rewrite `update-ai-stack.bat` as thin wrapper (no more immediate close)
- [x] Create `bootstrap.ps1` — self-contained first-run: auto-finds Python 3.11–3.14, installs pip deps, `Tee-Object` log, always keeps window open on error
- [x] Fix `version_intel.py`: `needs_update=True` when not installed; GitHub rate-limit fallback via HTML redirect; `GITHUB_TOKEN` env var support
- [x] Fix `cli.py`: `Text.from_markup()` for Rich markup rendering in version table
- [x] AMD docs compliance — Linux: use `ROCm/llama.cpp` fork; set `HIPCXX`/`HIP_PATH` from `hipconfig`; add `-DLLAMA_CURL=ON`; widen GPU target list per AMD docs
- [x] Windows: `ggml-org/llama.cpp` (no AMD native Windows ROCm build docs)
- [x] Split `llama_cpp_repo` (Linux) / `llama_cpp_repo_windows` in config and YAML
- [x] `version_intel.py` platform-aware repo check: `ROCm/llama.cpp` on Linux, `ggml-org/llama.cpp` on Windows
- [x] `--force` now triggers llama.cpp build even if version already current
- [x] `--force` nukes CMake cache dir before configure (fixes stale HIP SDK link pollution)
- [x] `_find_hip_path()`: added ROCm 7.0–7.3 search paths (was missing 7.x entirely)
- [x] Locked `.exe` handling: rename existing binaries to `.exe.old` before `cmake --install`
- [x] Add `gfx906` (Radeon VII / Vega 20) and `gfx1033` (Steam Deck Van Gogh APU) to default targets
- [x] Update all documentation and conductor files to reflect current state
