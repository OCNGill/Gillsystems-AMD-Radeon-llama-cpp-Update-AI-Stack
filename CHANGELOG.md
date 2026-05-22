# Changelog

All notable changes to the **Gillsystems AI Stack Updater** are documented here per semantic versioning.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

### Added
- **Dedicated HTPC server launcher**: Added `executables/Gillsystems-HTPC-server-latest.sh` for the HTPC optimized for 16GB RAM + 8GB VRAM (RX 7600), supporting Gemma 4 architecture.
- **Linux repository alignment**: Switched default `llama_cpp_repo` in `default_config.yaml` to the mainstream `ggml-org` fork to fix Gemma 4 compatibility errors caused by the outdated AMD tracking fork.
- **Linux library resolution**: Patched `update-ai-stack.sh` output wrappers and `executables/*.sh` scripts to explicitly link canonical `/opt` `.so` paths in `LD_LIBRARY_PATH`. Ensure `llama-server` does not fail due to missing shared libraries.

- **Example llama.cpp server launchers**: Added `Gillsystems_example_server_edit_per_node.bat` and `Gillsystems_example_server_edit_per_node.sh` in the repo root. Both create timestamped logs in `logs/` and ship Gemma-safe defaults with MTP flags omitted.
- **Dedicated Tier 2 server-only launchers**: Added `executables/Gillsystems_Laptop_iGPU_server_example.bat` and `executables/Gillsystems_SteamDeck_iGPU_server_example.sh` for the Laptop and Steam Deck nodes without changing the shared root templates.

### Changed

- **Linux launcher logging**: `update-ai-stack.sh` now mirrors Windows behavior by writing timestamped run logs into `logs/` while still streaming output to the console.
- **llama.cpp install layout**: successful installs still land in the canonical platform root, but the updater now mirrors the resulting `bin` tree into `<llama_cpp_source>/bin` and reports both locations during validation.

### Fixed

- **Steam Deck `stdint.h` build-stage failure after successful Vulkan configure** (`llama_builder.py`): SteamOS could now reach the `ninja` phase, but some systems still had a broken `/usr/include` tree where GCC existed and CMake configured successfully while the first compile failed with `fatal error: stdint.h: No such file or directory`. Linux preflight now probes the active C compiler with `#include <stdint.h>` before building, reports missing `C runtime headers` as a prerequisite failure, and the Arch/SteamOS targeted repair path now forces a `glibc` reinstall when that probe still fails after the normal `pacman --needed` pass.
- **Steam Deck pacman repair loop on Vulkan headers** (`llama_builder.py`): SteamOS could correctly detect `Vulkan headers` as missing, but the Arch repair plan used `pacman -S --needed`, so pacman skipped reinstall when its database said `vulkan-headers` was already installed, even though the required file was still missing on disk. The updater now keeps the fast `--needed` first pass, then detects unresolved Arch requirements and forces a second targeted pacman reinstall without `--needed` only for the still-missing packages.
- **Steam Deck Vulkan header false-positive and stale configure cache** (`llama_builder.py`): `_has_vulkan_headers()` incorrectly treated `pkg-config --exists vulkan` as proof that headers were present, but on Arch/SteamOS that only proves the loader package exists. This let preflight skip repair while CMake still failed with `Could NOT find Vulkan (missing: Vulkan_INCLUDE_DIR)`. Header detection now relies on the concrete `vulkan/vulkan.h` path that `FindVulkan` actually searches, and `_configure_cmake()` now deletes stale `CMakeCache.txt` before reconfigure so previous failed `build-vulkan` state cannot poison later runs.
- **Steam Deck Vulkan preflight false-positive / missing loader repair** (`llama_builder.py`): preflight could pass on SteamOS while CMake still failed with `Could NOT find Vulkan (missing: Vulkan_INCLUDE_DIR)` because the updater did not treat the Vulkan loader as a required dependency. Linux preflight now checks for a Vulkan loader explicitly, and the Arch/SteamOS package plan now installs `vulkan-icd-loader` alongside `vulkan-headers`, `shaderc`, and `spirv-headers` so the next run can repair the current system instead of failing at CMake configure.
- **Steam Deck `PermissionError` on pacman keyring stat** (`llama_builder.py`): `_has_initialized_pacman_keyring()` called `Path.exists()` on files inside `/etc/pacman.d/gnupg/` (root:root 700). Running as non-root `deck` user this raises `PermissionError` even after `steamos-readonly disable`, aborting the entire run. Wrapped in `try/except PermissionError` returning `False` so `pacman-key --init` is invoked via the privileged sudo runner as intended.
- **Steam Deck Vulkan header detection false-negative** (`llama_builder.py`): `_has_vulkan_headers()` and `_has_spirv_headers()` relied exclusively on `Path.exists()` filesystem checks. On SteamOS's overlay mount, installed package headers can be invisible to Python even after a successful `pacman -S`. Replaced with a three-tier strategy: `pkgconf`/`pkg-config --exists`, pacman database query (`pacman -Qq`), then filesystem path fallback.
- **`install_dir` missing `.expanduser()`** (`llama_builder.py`): `Path(cfg.paths.llama_cpp_install_linux)` did not call `.expanduser()`, so any `~`-prefixed install path would create a literal `~/` directory instead of expanding to the user's home. Now matches `source_dir` which already called it.
- **`-DGGML_HIP=OFF` missing from Vulkan-only CMake configure** (`llama_builder.py`): Vulkan builds only appended `-DGGML_VULKAN=ON` without explicitly disabling HIP. CMake auto-detection could silently enable HIP on machines where ROCm toolchain is partially installed, causing link conflicts. Added `-DGGML_HIP=OFF` to the Vulkan branch.
- **hipconfig queried during Vulkan-only builds** (`llama_builder.py`): `_build()` queried `hipconfig` and set `HIPCXX`/`HIP_PATH` env vars regardless of build backend. Guarded the block with `if self.use_hip`.
- **`_validate()` early return skipped second binary** (`llama_builder.py`): The loop returned after the first successful binary, so `llama-server` was never checked if `llama-cli` passed. Replaced with accumulator pattern that checks all binaries and warns on each missing/failed one.
- **`build_dir` always named `build-hip` regardless of backend** (`llama_builder.py`): The cmake build directory was hardcoded as `build-hip` even for Vulkan builds. Renamed dynamically to `build-hip` or `build-vulkan` based on `self.use_hip` to prevent CMakeCache conflicts between backend switches.
- **Bootstrap `cleanup()` killed keepalive before sudo commands** (`bootstrap-linux.sh`): `SUDO_KEEPALIVE_PID` was killed at the top of `cleanup()`, before the `sudo -n chown` and `sudo -n steamos-readonly enable` calls. If the ticket was near expiry, cleanup sudo commands could silently fail. Moved the keepalive kill to the very end of `cleanup()`, after all privileged operations.
- **Steam Deck `PermissionError` on pacman keyring stat** (`llama_builder.py`): `_has_initialized_pacman_keyring()` called `Path.exists()` on files inside `/etc/pacman.d/gnupg/` (root:root 700). Running as non-root `deck` user this raises `PermissionError` even after `steamos-readonly disable`, aborting the entire run. Wrapped in `try/except PermissionError` returning `False` so `pacman-key --init` is invoked via the privileged sudo runner as intended.
- **Steam Deck critical relock-mid-run bug** (commit `agent-round3`): `_install_linux_build_prerequisites()` was calling `steamos-readonly enable` in its `finally` block even when `bootstrap-linux.sh` had already unlocked the filesystem globally. This re-locked the FS before `_build()` ran, causing a read-only filesystem error during cmake. Fix: guard the lock/unlock cycle with `os.environ.get("STEAMOS_UNLOCKED") == "1"`.
- **Steam Deck `use_hip` redundant computation**: `bool(shutil.which("hipcc"))` was computed independently in `_preflight_check()`, `_configure_cmake()`, and `_build()`. Now computed once in `LlamaBuilderLinux.__init__` as `self.use_hip`, used universally.
- **Version check queried wrong fork on Linux** (`version_intel.py`): Linux version check was querying `ROCm/llama.cpp` (AMD tracking fork) instead of `ggml-org/llama.cpp`, causing spurious "Could not determine latest version" warnings. Both platforms now use the ggml-org fork to match actual build target.
- **Opaque `SyntaxError` / `ImportError` on llama engine load** (`main.py`): Dynamic imports of `LlamaBuilderLinux` and `LlamaBuilderWindows` are now wrapped in `try/except (ImportError, SyntaxError)` with a descriptive `RuntimeError` pointing to the build engine file.
- **Steam Deck cleanup() chown-after-relock ordering** (`bootstrap-linux.sh`): `restore_user_owned_paths()` only ran as root (never triggered in normal non-root flow). Restructured `cleanup()` to: kill keepalive → chown repo dir back to original owner → re-lock filesystem. Root-owned artifacts from privileged subprocess steps are now cleaned up before read-only mode is restored.
- **Steam Deck `llama_builder.py` corrupted by raw diff text** (commit `a23d109`): File was overwritten with git diff markers in a prior commit (`e93fe78`). Restored from `63a2012` and applied intended `DGGML_HIP_ROCWMMA_FATTN=OFF` change.
- **Steam Deck 5-issue hardening** (commit `0172ed8`): `LLAMA_HIP_UMA` flag now HIP-only; symlink `RuntimeError` surfaced correctly; `_detect_distro()` fallback parses `/etc/os-release` key=value pairs; SteamOS `readonly` `finally` block wrapped in `try/except`; `config.py` Pydantic default aligned to `ggml-org/llama.cpp.git`.
- **Steam Deck global SteamOS unlock** (commit `79508bf`): `bootstrap-linux.sh` now calls `steamos-readonly disable` at session establishment (inside `ensure_sudo_session()`), exports `STEAMOS_UNLOCKED=1`, and re-locks in the `cleanup()` trap on exit.
- **Windows Tier 2 Vulkan fallback**: CMake now points `CMAKE_PREFIX_PATH` at the LunarG Vulkan SDK package root so `SPIRV-Headers` is discovered reliably during `llama.cpp` configure.
- **Windows PATH validation messaging**: the updater now refreshes the current process PATH and tells users where the install and source-root launcher bins actually live.

## [1.0.1] — 2026-05-06 — Windows 11 Hardening (Current)

### Added
- **Dedicated HTPC server launcher**: Added `executables/Gillsystems-HTPC-server-latest.sh` for the HTPC optimized for 16GB RAM + 8GB VRAM (RX 7600), supporting Gemma 4 architecture.
- **Linux repository alignment**: Switched default `llama_cpp_repo` in `default_config.yaml` to the mainstream `ggml-org` fork to fix Gemma 4 compatibility errors caused by the outdated AMD tracking fork.
- **Linux library resolution**: Patched `update-ai-stack.sh` output wrappers and `executables/*.sh` scripts to explicitly link canonical `/opt` `.so` paths in `LD_LIBRARY_PATH`. Ensure `llama-server` does not fail due to missing shared libraries.

- **`bootstrap.ps1` — Windows Unicode support**: Sets `$env:PYTHONUTF8 = '1'` and forces `[Console]::OutputEncoding = UTF8` before launching the agent. Prevents Rich box-drawing characters from being mangled by PowerShell 5.1's `Tee-Object` pipe transcoding to OEM cp437.
- **`bootstrap.ps1` — Stderr isolation**: Changed `2>&1 | Tee-Object` to `2>>$logFile | Tee-Object -Append`. This sends httpx INFO/DEBUG logs (which PowerShell 5.1 wraps in red `NativeCommandError` decorations) directly to the log file, keeping the console clean.
- **`src/cli.py` — `PYTHONUTF8` env var**: Sets `os.environ['PYTHONUTF8'] = '1'` at module import time, before any stdio interaction, ensuring Python 3.12+ uses UTF-8 for all I/O on Windows.
- **`src/main.py` — httpx log suppression**: Adds `logging.getLogger('httpx').setLevel(logging.WARNING)` and same for `httpcore` to stop INFO-level HTTP request logs from polluting stderr.
- **`src/windows/hip_updater.py` — HIP SDK 7.x support**: Updated version search list to include `7.2.2` through `7.0.0` (was only `6.x`), updated fallback URL to `7.2.2`, and updated environment scanner to search `ROCm/7.0` through `ROCm/7.3` paths first.
- **`tests/test_version_intel.py` — API failure mock**: Added `HEAD` side-effect mock to cover the HTML redirect fallback path in `_get_latest_llama()`.

### Fixed

- **`bootstrap.ps1` — Duplicate exit block**: Removed duplicated exit-code block at end of file.
- **`tests/test_version_intel.py` — Indentation**: Corrected whitespace corruption in `test_get_latest_llama_success` and `test_get_latest_llama_api_failure` that prevented test collection.

---

## [1.0.0] — 2026-05-06 — Full-Stack Rebrand & Post-MVP Hardening

### Changed

- **Project rename**: GASU → **Gillsystems AI Stack Updater** across all source, config, env vars, systemd services, scheduled tasks, and documentation (commit `b432fe6`).
- **Linux AMD docs compliance** (commit `fba910a`): Switched to AMD's official `ROCm/llama.cpp` fork, set `HIPCXX`/`HIP_PATH` from `hipconfig`, added `-DLLAMA_CURL=ON`, widened GPU target list. Default targets: `gfx1100;gfx1101;gfx1102;gfx1030;gfx1031;gfx1032;gfx1033;gfx906`.
- **Windows repo split** (commit `fba910a`): Windows uses `ggml-org/llama.cpp` (no AMD native Windows build docs), config now has `llama_cpp_repo` (Linux) / `llama_cpp_repo_windows`.

### Added
- **Dedicated HTPC server launcher**: Added `executables/Gillsystems-HTPC-server-latest.sh` for the HTPC optimized for 16GB RAM + 8GB VRAM (RX 7600), supporting Gemma 4 architecture.
- **Linux repository alignment**: Switched default `llama_cpp_repo` in `default_config.yaml` to the mainstream `ggml-org` fork to fix Gemma 4 compatibility errors caused by the outdated AMD tracking fork.
- **Linux library resolution**: Patched `update-ai-stack.sh` output wrappers and `executables/*.sh` scripts to explicitly link canonical `/opt` `.so` paths in `LD_LIBRARY_PATH`. Ensure `llama-server` does not fail due to missing shared libraries.

- **`bootstrap.ps1`**: Self-contained PowerShell first-run bootstrap script. Auto-finds Python 3.11–3.14 via `py` launcher, PATH, or common install paths; downloads and silently installs Python 3.12.9 if none found; upgrades pip; installs requirements; launches agent with `Tee-Object` logging. Always keeps console window open on error (commit `6f6457c`).
- **`--force` clean-build** (commit `fc85951`): Nukes CMake cache directory before configure — fixes stale HIP SDK link pollution. Also renames locked `.exe` files to `.exe.old` before `cmake --install`.
- **GPU targets**: `gfx906` (Vega 20 / Radeon VII) and `gfx1033` (Steam Deck Van Gogh APU) added to default target list.
- **`version_intel.py`**: GitHub rate-limit fallback via HTML redirect; `GITHUB_TOKEN` env var support; `needs_update=True` when component is not installed (commit `b3e18ee`).

### Fixed

- **Version table rendering** (commit `b3e18ee`): Replaced plain-text version cell with `Text.from_markup()` so Rich markup styling renders correctly.
- **Windows bootstrap UX** (commit `6f6457c`): `update-ai-stack.bat` rewritten as thin wrapper — no longer closes cmd window immediately.
- **Version check logic** (commit `b3e18ee`): Null-installed components now correctly report `installed=None` without false comparisons.
- **ROCm 7.x path detection** (commit `fc85951`): Added ROCm 7.0–7.3 to `_find_hip_path()` candidate list.

---

## [0.9.0] — 2026-04-29 — Tier 1/2 Architecture & Hardware Profiling

### Added
- **Dedicated HTPC server launcher**: Added `executables/Gillsystems-HTPC-server-latest.sh` for the HTPC optimized for 16GB RAM + 8GB VRAM (RX 7600), supporting Gemma 4 architecture.
- **Linux repository alignment**: Switched default `llama_cpp_repo` in `default_config.yaml` to the mainstream `ggml-org` fork to fix Gemma 4 compatibility errors caused by the outdated AMD tracking fork.
- **Linux library resolution**: Patched `update-ai-stack.sh` output wrappers and `executables/*.sh` scripts to explicitly link canonical `/opt` `.so` paths in `LD_LIBRARY_PATH`. Ensure `llama-server` does not fail due to missing shared libraries.

- **Tier-based hardware profiling** (commit `209fe27`): Tier 1 (full HIP/ROCm) vs Tier 2 (Vulkan + HIP UMA) detection. Flash Attention support (`GGML_HIP_ROCWMMA_FATTN=ON`). UMA memory controls for integrated GPUs.
- **Bleeding-edge mode** (commit `baf4f54`): `--bleeding-edge` flag compiles from `master` branch for zero-day GGML tensor format support (e.g. Gemma 4 CoT, sliding window attention).
- **Vulkan fallback** (commit `baf4f54`): Tier 2 machines (iGPUs, Steam Deck) get `GGML_VULKAN=ON` as compile backend when native HIP is unavailable.
- **Tier enforcement**: Launcher enforces minimum ROCm/llama.cpp versions per hardware tier.

---

## [0.8.0] — 2026-04-29 — Full-Stack Implementation (MVP)

### Added
- **Dedicated HTPC server launcher**: Added `executables/Gillsystems-HTPC-server-latest.sh` for the HTPC optimized for 16GB RAM + 8GB VRAM (RX 7600), supporting Gemma 4 architecture.
- **Linux repository alignment**: Switched default `llama_cpp_repo` in `default_config.yaml` to the mainstream `ggml-org` fork to fix Gemma 4 compatibility errors caused by the outdated AMD tracking fork.
- **Linux library resolution**: Patched `update-ai-stack.sh` output wrappers and `executables/*.sh` scripts to explicitly link canonical `/opt` `.so` paths in `LD_LIBRARY_PATH`. Ensure `llama-server` does not fail due to missing shared libraries.

- **Core orchestrator** (`main.py`): State machine with SQLite checkpoint ledger, reboot-resilient resume.
- **Version intelligence** (`version_intel.py`): Checks GitHub API for llama.cpp releases, AMD repo for ROCm versions.
- **GPU architecture detection** (`gpu_detect.py`): `rocminfo`/sysfs on Linux, WMI/`hipInfo` on Windows.
- **Privilege management** (`privilege.py`): UAC elevation (Windows) and `sudo` detection (Linux).
- **Rich terminal UI** (`cli.py`): Colored output, progress bars, dry-run warnings, summary tables.
- **Linux sub-agent** (`linux/rocm_updater.py`, `linux/llama_builder.py`, `linux/reboot_handler.py`): `amdgpu-install` automation, CMake+HIP llama.cpp build, systemd one-shot resume service.
- **Windows sub-agent** (`windows/hip_updater.py`, `windows/llama_builder.py`, `windows/reboot_handler.py`): HIP SDK silent installer, Visual Studio Build Tools + Ninja build, Scheduled Task resume.
- **Configuration** (`config.py`, `config/default_config.yaml`): Pydantic models, YAML loader, env var support.
- **Cross-platform launchers**: `update-ai-stack.bat` (Windows) and `update-ai-stack.sh` (Linux).
- **Test suite**: 59 unit tests across 4 test modules with isolation mocks.
- **Project scaffolding**: `pyproject.toml`, `requirements.txt`, `.gitignore`, `__init__.py`.

---

## [0.0.1] — 2026-04-16 — Initial Concept

### Added
- **Dedicated HTPC server launcher**: Added `executables/Gillsystems-HTPC-server-latest.sh` for the HTPC optimized for 16GB RAM + 8GB VRAM (RX 7600), supporting Gemma 4 architecture.
- **Linux repository alignment**: Switched default `llama_cpp_repo` in `default_config.yaml` to the mainstream `ggml-org` fork to fix Gemma 4 compatibility errors caused by the outdated AMD tracking fork.
- **Linux library resolution**: Patched `update-ai-stack.sh` output wrappers and `executables/*.sh` scripts to explicitly link canonical `/opt` `.so` paths in `LD_LIBRARY_PATH`. Ensure `llama-server` does not fail due to missing shared libraries.

- Agent architecture defined.
- Conductor files established: `conductor/index.md`, `product.md`, `tech-stack.md`, `tracks.md`, `workflow.md`, `setup_state.json`.
- Track T-001-agent-core created with spec and plan.
- `conductor/product-guidelines.md` — quality gates and standards.

---

## Legend

- `[1.0.1]` — Current release on `main`.
- Releases follow semantic versioning — breaking changes bump major, features bump minor, fixes bump patch.
