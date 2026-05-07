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
  - Windows: [ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp) — CMake with `GGML_HIP=ON`, `GGML_HIP_ROCWMMA_FATTN=ON`; HIP SDK path auto-detected

## Windows First-Run Bootstrap
- **`bootstrap.ps1`** — Self-contained PowerShell script called by `update-ai-stack.bat`; auto-locates Python (3.11–3.14), installs pip deps, logs full output to `logs/`, always keeps the window open with errors visible

## OS Targets
- **Linux:** Ubuntu 22.04 / 24.04 (primary), Fedora (secondary), SteamOS / Arch (Steam Deck)
- **Windows:** Windows 10 / 11 with HIP SDK 7.x support
