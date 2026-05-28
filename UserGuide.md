<p align="center">
  <img src="Gillsystems_logo_stuff/Gill%20Systems%20Logo.png" alt="Gill Systems Logo" width="800">
</p>

# User Guide: Gillsystems AI Stack Updater Agent v2.1

> **v2.1 — ROUND 3 TUNING.** The fleet has migrated standard node deployments to the Google-Optimized sample profile (Temperature 1.0, Top K 64, Top P 0.95) and fully locked APU compute chunks via -b 2048 and -ub 512. We are now prepared for Instruction-Tuned (IT) model orchestration.

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

v2.0 ships fully validated, production-ready launchers for every Gillsystems node. Each is hard-coded for its exact hardware — binary path, library path, context size, GPU layers, and temperature. They are not generic templates; they are the launchers that actually passed real-world validation.

**KUbuntu HTPC (RX 7600 / gfx1102 — ROCm/HIP, Tier 1):**
```bash
executables/Gillsystems-HTPC-AI-server.sh
```
- Binary: `/home/gillsystems-htpc/src/llama.cpp/bin/llama-server`
- Libs: `/opt/gillsystems/llama.cpp/lib` (canonical ROCm/HIP install)
- Context: 65 536 tokens — confirmed stable on 8 GB VRAM + 16 GB RAM
- GPU layers: 99 (full offload)
- Flash Attention: on
- Sampling: Temperature 1.0, Top_K 64, Top_P 0.95
- Batching: 2048 logical, 512 physical
- Supports `--dry-run`

**Steam Deck AI Server (RDNA 2 APU / gfx1033 — Vulkan, Tier 2):**
```bash
executables/Gillsystems_SteamDeck_AI_Server.sh
```
- Binary: `/home/deck/src/llama.cpp/bin/llama-server`
- Libs: `/home/deck/src/llama.cpp/build-vulkan/bin` — points directly to the Vulkan build output where `libllama-server-impl.so` and all Vulkan-backend `.so` files live
- Context: 32 768 tokens — right-sized for APU shared memory
- GPU layers: 99
- Flash Attention: on
- Sampling: Temperature 1.0, Top_K 64, Top_P 0.95
- Batching: 2048 logical, 512 physical
- Supports `--dry-run`

**Windows Laptop (Vega 6 iGPU / gfx90c — HIP UMA, Tier 2):**
```bat
executables/Gillsystems_Laptop_iGPU_server.bat
```
- Edit context and paths to suit; template ships with Gemma-safe defaults.

**Editable per-node templates in `executables/` (start here for a new node):**
```text
executables/Gillsystems_server_edit_per_node.bat
executables/Gillsystems_server_edit_per_node.sh
```

All launchers use `--temperature 0` for fully deterministic output, `--jinja`, `--context-shift`, `--metrics`, and `--no-mmap`.

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
