<p align="center">
  <img src="Gillsystems_logo_stuff/Gill%20Systems%20Logo.png" alt="Gill Systems Logo" width="800">
</p>

# User Guide: Gillsystems AI Stack Updater Agent v2.3.0

> **v2.3.0 — ROUND 4 STABILIZATION.** The attached round 3 logs showed launcher drift under the shared verification prompt. The production launchers now enforce explicit Gemma chat-template alignment, bounded default output, proper runtime path resolution, and root log capture before the same prompt is rerun.

## 📌 Getting Started

### Windows
Launch the updater agent by double-clicking the root batch script or running it via command prompt:
```bat
update-ai-stack.bat
```
*(You will be asked to elevate privileges if not already running as Administrator. A timestamped run log is written to `logs/`.)*

### Linux
Launch the updater agent directly from your terminal:
```bash
./update-ai-stack.sh
```
*(Live runs request `sudo` once, keep it warm for the run, and keep the Python venv/log handling in user space. Dry-runs do not prompt for `sudo`. A timestamped run log is written to `logs/`.)*

If Konsole or SteamOS warns that it could not find `update-ai-stack.sh` and falls back to `/bin/bash`, the terminal profile is pointing at a stale repo path or the execute bit was stripped. Use this as the safe launcher command in terminal profiles:

```bash
/bin/bash "/absolute/path/to/update-ai-stack.sh"
```

You can also run `bash ./update-ai-stack.sh --check-env` once to validate the Linux launcher and auto-repair the execute bit when the repo checkout is writable.

### Server Launchers — Production Node Configuration

Round 4 keeps dedicated launchers for every Gillsystems node, but corrects the operational contract that broke round 3: no more fake reverse-prompt stop handling, no more unbounded default output, and no more stale file references.

**Main Rig (RX 7900 XTX / gfx1100 — HIP/ROCm, Tier 1):**
```bat
executables/Gillsystems_Main_AI_Server.bat
```
- Model: `gemma-4-31B.Q4_K_M.gguf`
- Model path resolution: prefers `C:\Models\Working_Models\gemma-4-31B.Q4_K_M.gguf`; override with `GILLSYSTEMS_MAIN_MODEL_PATH`
- Context: 49 152 tokens
- Default output cap: 2 048 tokens
- Gemma alignment: `--jinja` + `--chat-template gemma`
- Logging: root `logs/` capture via PowerShell `Tee-Object`

**KUbuntu HTPC (RX 7600 / gfx1102 — ROCm/HIP, Tier 1):**
```bash
executables/Gillsystems-HTPC-AI-server.sh
```
- Context: 32 768 tokens
- Default output cap: 1 536 tokens
- Runtime pairing: executable, shared libraries, and optional rocBLAS Tensile path are resolved together
- Logging: root `logs/` capture via `tee`

**Windows Laptop (Vega 6 iGPU / gfx90c — Vulkan or HIP UMA, Tier 2):**
```bat
executables/Gillsystems_Laptop_4500U_Vega6_server.bat
```
- Context: 32 768 tokens
- Default output cap: 1 024 tokens
- Runtime pairing: canonical install root plus mirrored source/build fallbacks
- Compatibility: sets `LLAMA_HIP_UMA=1` when HIP runtime support is used

**Steam Deck AI Server (RDNA 2 APU / gfx1033 — Vulkan, Tier 2):**
```bash
executables/Gillsystems_SteamDeck_AI_Server.sh
```
- Context: 32 768 tokens
- Default output cap: 1 024 tokens
- Runtime pairing: prefers the Vulkan build-tree library directory used by the deck
- Logging: root `logs/` capture via `tee`

**Editable per-node templates in `executables/` (start here for a new node):**
```text
executables/Gillsystems_server_edit_per_node.bat
executables/Gillsystems_server_edit_per_node.sh
```

All production launchers use the deterministic cluster sampler (`temperature 0`, `min-p 0.05`, `top-k 20`, `top-p 1.0`), plus `--jinja`, `--chat-template gemma`, `--context-shift`, `--metrics`, and `--no-mmap`.

For OpenAI-compatible chat clients, send an explicit `stop` array such as `[
  "<|im_end|>",
  "<|im_start|>"
]` when you need hard stop-word behavior. `llama-server` documents stop arrays for API usage; reverse prompts are for interactive mode.

---

## 🏗️ Architecture & State Tracking

Gillsystems AI Stack Updater implements a fully reboot-resilient architecture that tracks state progressively into a local SQLite ledger `state/checkpoint.db`, meaning the application safely picks up right where it left off!

- The main `Orchestrator` validates system state against upstream versions (`version_intel`).
- Distinct `Linux` and `Windows` Sub-Agents handle platform-specific operations:
  - **Linux (`rocm_updater.py`):** Uses native package managers to install AMDGPU drivers under `amdgpu-install --usecase=rocm,hiplibsdk`.
  - **Windows (`hip_updater.py`):** Operates the AMD HIP SDK 7.x Installer silently.
- Platform-aware `LlamaBuilder` selects the correct upstream source and builds with HIP:
  - **Linux:** Clones AMD's official [`ROCm/llama.cpp`](https://github.com/ROCm/llama.cpp) fork (per AMD documentation). Sets `HIPCXX` and `HIP_PATH` from `hipconfig` before building. CMake flags include `-DGGML_HIP=ON`, `-DGGML_HIP_ROCWMMA_FATTN=ON`, and `-DLLAMA_CURL=ON`. When a live Linux run reaches the `llama.cpp` step, missing build prerequisites are installed automatically with the host package manager; Tier 1 machines still hard-require HIP, while Tier 2 machines install the Vulkan development packages needed for fallback builds.
  - **Windows:** Clones [`ggml-org/llama.cpp`](https://github.com/ggml-org/llama.cpp) (AMD has no native Windows ROCm build documentation). Uses Ninja + MSVC with auto-detected HIP SDK path for Tier 1 nodes, and configures Tier 2 Vulkan fallback through the LunarG Vulkan SDK when HIP is not available.
  - **Install layout:** Successful installs land in the canonical platform root (`C:\Gillsystems\llama.cpp\bin` on Windows, `/opt/gillsystems/llama.cpp/bin` on Linux) and are mirrored into `<llama_cpp_source>/bin` for direct testing from the active source tree.
  - GPU architecture targets (`AMDGPU_TARGETS`) are auto-detected from WMI / rocminfo and cover all Gillsystems nodes: `gfx1100` (7900 XTX), `gfx1102` (RX 7600), `gfx1033` (Steam Deck), `gfx1030` (RDNA 2), `gfx906` (Vega 20), and more.

### 🔧 Force a Clean Rebuild

If binaries fail to load new model tensor formats (e.g. Gemma 4) or cmake links against a stale HIP SDK version:

```bat
update-ai-stack.bat --force
```

`--force` deletes the entire CMake cache directory before reconfiguring, ensuring a fully clean build against the currently installed HIP SDK. It also handles locked `.exe` files — existing binaries are renamed before install so they can be overwritten even if another terminal has them open.

For absolute bleeding-edge model support (master branch, post-Gemma 4):

```bat
update-ai-stack.bat --bleeding-edge
```

*(See internal `conductor/` documentation and `documentation/implementation_plan.md` for specific architectural guidelines.)*

---

## 💖 Support / Donate

If you find this project helpful, you can support ongoing work — thank you!

<p align="center">
	<img src="Gillsystems_logo_stuff/Readme%20Donation%20files/qr-paypal.png" alt="PayPal QR code" width="180" style="margin:8px;">
	<img src="Gillsystems_logo_stuff/Readme%20Donation%20files/qr-venmo.png" alt="Venmo QR code" width="180" style="margin:8px;">
</p>


**Donate:**

- [![PayPal](https://img.shields.io/badge/PayPal-Donate-009cde?logo=paypal&logoColor=white)](https://paypal.me/gillsystems) https://paypal.me/gillsystems
- [![Venmo](https://img.shields.io/badge/Venmo-Donate-3d95ce?logo=venmo&logoColor=white)](https://venmo.com/Stephen-Gill-007) https://venmo.com/Stephen-Gill-007

---


<p align="center">
	<img src="Gillsystems_logo_stuff/Readme%20Donation%20files/Gillsystems_logo_with_donation_qrcodes.png" alt="Gillsystems logo with QR codes and icons" width="800">
</p>

<p align="center">
	<a href="https://paypal.me/gillsystems"><img src="Gillsystems_logo_stuff/Readme%20Donation%20files/paypal_icon.png" alt="PayPal" width="32" style="vertical-align:middle;"></a>
	<a href="https://venmo.com/Stephen-Gill-007"><img src="Gillsystems_logo_stuff/Readme%20Donation%20files/venmo_icon.png" alt="Venmo" width="32" style="vertical-align:middle;"></a>
</p>
