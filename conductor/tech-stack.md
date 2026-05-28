# Tech Stack

## Runtime
- **Python 3.11+** — Agent core (3.12 recommended; 3.14 supported)
- **SQLite** — State persistence / progress ledger
- **JSON/YAML** — Config and checkpoint files

## Dependencies (Python)
- `httpx` — HTTP for GitHub API / AMD repo checks (rate-limit fallback via HTML redirect)
- `rich` — Terminal UI / progress bars
- `pydantic` / `pydantic-settings` — Config and state validation
- `packaging` — Version comparison
- `PyYAML` — Config file loading

## Build Tools (Targets)
- **ROCm 7.x** — `amdgpu-install` (Linux), HIP SDK 7.2.x installer (Windows)
- **llama.cpp**:
  - Linux: AMD’s [ROCm/llama.cpp](https://github.com/ROCm/llama.cpp) fork — CMake with `GGML_HIP=ON`, `GGML_HIP_ROCWMMA_FATTN=ON`, `LLAMA_CURL=ON`; `HIPCXX`/`HIP_PATH` set from `hipconfig`
  - Windows: [ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp) — CMake with `GGML_HIP=ON`, `GGML_HIP_ROCWMMA_FATTN=ON`; HIP SDK path auto-detected for Tier 1, LunarG Vulkan SDK package discovery for Tier 2 fallback
  - Install layout: binaries install into the canonical platform root and are mirrored into `<llama_cpp_source>/bin` after a successful build for source-tree launchers

## Windows First-Run Bootstrap
- **`bootstrap.ps1`** — Self-contained PowerShell script called by `update-ai-stack.bat`; auto-locates Python (3.11–3.14), installs pip deps, logs full output to `logs/`, always keeps the window open with errors visible

## Linux First-Run Bootstrap
- **`bootstrap-linux.sh`** — Repo-local Bash bootstrap called by `update-ai-stack.sh`; auto-locates Python 3.11+, creates the project venv, warms `sudo` once per live run, keeps the credential alive for the session, logs full output to `logs/`, and prints explicit Konsole/SteamOS launcher warnings when the execute bit or profile path is wrong

## Server Launchers
- **`executables/Gillsystems_server_edit_per_node.bat`** — Windows `llama-server.exe` editable launcher with timestamped `logs/` output, portable rocBLAS Tensile path wiring, and Gemma-safe defaults (no MTP flags)
- **`executables/Gillsystems_server_edit_per_node.sh`** — Linux `llama-server` editable launcher with timestamped `logs/` output and Gemma-safe defaults (no MTP flags)
- **`executables/Gillsystems_Main_AI_Server.bat`** — Dedicated Windows Tier 1 launcher for the Dense 31B main node with root-log capture, rocBLAS path wiring, explicit Gemma template alignment, and a 2048-token default output cap
- **`executables/Gillsystems-HTPC-AI-server.sh`** — Dedicated Linux Tier 1 launcher for the HTPC node with paired executable/library resolution, optional rocBLAS Tensile wiring, explicit Gemma template alignment, and a 1536-token default output cap
- **`executables/Gillsystems_Laptop_4500U_Vega6_server.bat`** — Dedicated Windows Tier 2 launcher for the Laptop/Vega 6 node with canonical install and mirrored source-tree fallbacks, HIP UMA compatibility, explicit Gemma template alignment, and a 1024-token default output cap
- **`executables/Gillsystems_SteamDeck_AI_Server.sh`** — Dedicated Linux Tier 2 launcher for the Steam Deck node with Vulkan build-tree library pairing, root-log capture, explicit Gemma template alignment, and a 1024-token default output cap

## OS Targets
- **Linux:** Ubuntu 22.04 / 24.04 (primary), Fedora (secondary), SteamOS / Arch (Steam Deck)
- **Windows:** Windows 10 / 11 with HIP SDK 7.x support
