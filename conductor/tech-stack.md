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

## Example Server Launchers
- **`Gillsystems_example_server_edit_per_node.bat`** — Windows `llama-server.exe` example launcher with timestamped `logs/` output, portable rocBLAS Tensile path wiring, and Gemma-safe defaults (no MTP flags)
- **`Gillsystems_example_server_edit_per_node.sh`** — Linux `llama-server` example launcher with timestamped `logs/` output and Gemma-safe defaults (no MTP flags)
- **`executables/Gillsystems_Laptop_iGPU_server_example.bat`** — Dedicated Windows Tier 2 server-only launcher for the Laptop/Vega 6 node with path fallbacks for mirrored source-root, active build tree, and canonical install roots
- **`executables/Gillsystems_SteamDeck_iGPU_server_example.sh`** — Dedicated Linux Tier 2 server-only launcher for the Steam Deck node with path fallbacks for mirrored source-root, active build tree, and canonical install roots

## OS Targets
- **Linux:** Ubuntu 22.04 / 24.04 (primary), Fedora (secondary), SteamOS / Arch (Steam Deck)
- **Windows:** Windows 10 / 11 with HIP SDK 7.x support
