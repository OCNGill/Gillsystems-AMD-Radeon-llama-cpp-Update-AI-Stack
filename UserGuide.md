<p align="center">
  <img src="Gillsystems_logo_stuff/Gill%20Systems%20Logo.png" alt="Gill Systems Logo" width="800">
</p>

# User Guide: Gillsystems AI Stack Updater Agent

## 📌 Getting Started

### Windows
Launch the updater agent by double-clicking the root batch script or running it via command prompt:
```bat
update-ai-stack.bat
```
*(You will be asked to elevate privileges if not already running as Administrator.)*

### Linux
Launch the updater agent directly from your terminal:
```bash
./update-ai-stack.sh
```
*(The script will request `sudo` permissions as needed.)*

---

## 🏗️ Architecture & State Tracking

Gillsystems AI Stack Updater implements a fully reboot-resilient architecture that tracks state progressively into a local SQLite ledger `state/checkpoint.db`, meaning the application safely picks up right where it left off!

- The main `Orchestrator` validates system state against upstream versions (`version_intel`).
- Distinct `Linux` and `Windows` Sub-Agents handle platform-specific operations:
  - **Linux (`rocm_updater.py`):** Uses native package managers to install AMDGPU drivers under `amdgpu-install --usecase=rocm,hiplibsdk`.
  - **Windows (`hip_updater.py`):** Operates the AMD HIP SDK 7.x Installer silently.
- Platform-aware `LlamaBuilder` selects the correct upstream source and builds with HIP:
  - **Linux:** Clones AMD's official [`ROCm/llama.cpp`](https://github.com/ROCm/llama.cpp) fork (per AMD documentation). Sets `HIPCXX` and `HIP_PATH` from `hipconfig` before building. CMake flags include `-DGGML_HIP=ON`, `-DGGML_HIP_ROCWMMA_FATTN=ON`, and `-DLLAMA_CURL=ON`.
  - **Windows:** Clones [`ggml-org/llama.cpp`](https://github.com/ggml-org/llama.cpp) (AMD has no native Windows ROCm build documentation). Uses Ninja + MSVC with auto-detected HIP SDK path.
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
