# Product Definition — Gillsystems AI Stack Updater Agent

## Mission
Provide a single-invocation, fully autonomous agent that detects, downloads, builds, and installs the latest stable releases of **ROCm/HIP** (and all dependencies) and **llama.cpp** (compiled against the installed ROCm) — across both **Windows** and **Linux** — on AMD consumer GPU hardware.

## Core Value
Eliminates the painful, error-prone manual process of keeping the AMD AI software stack current on consumer hardware where official tooling is sparse and the dependency graph is deep.

## Target Users / Nodes
| Node | OS | GPU | gfx | Backend |
|---|---|---|---|---|
| Gillsystems-Main | Windows 11 Pro | RX 7900 XTX | gfx1100 | HIP/ROCm (Tier 1) |
| Gillsystems-HTPC | Kubuntu | RX 7600 | gfx1102 | ROCm (Tier 1) |
| Gillsystems-Laptop | Windows 10 | Vega 6 iGPU | gfx90c | Vulkan + HIP UMA (Tier 2) |
| Gillsystems-Steam-Deck | SteamOS | RDNA 2 APU | gfx1033 | Vulkan + HIP UMA (Tier 2) |

## Key Capabilities
1. **Version Detection** — Checks currently installed versions vs. latest upstream releases; GitHub Releases API with HTML redirect rate-limit fallback.
2. **Automated Update** — Downloads, compiles (if needed), and installs new versions.
3. **Reboot Resilience** — Survives reboots mid-update, resumes exactly where it left off.
4. **Dual-OS** — Separate sub-agents for Windows and Linux with shared core logic.
5. **Dual-Target** — ROCm/HIP stack + llama.cpp, each as independent update routines.
6. **Invocation-Only** — Does nothing unless explicitly launched via `.bat` / `.sh`.
7. **Admin/Sudo** — Runs with elevated privileges for driver/kernel-level installs.
8. **Windows First-Run Bootstrap** — `bootstrap.ps1` finds Python, installs deps, keeps window open on error.
9. **Force Clean Build** — `--force` nukes stale CMake cache before rebuild, preventing HIP SDK version pollution and locked-exe install failures.
10. **Zero-Day Model Support** — `--bleeding-edge` compiles from master for immediate support of new GGML tensor formats (e.g. Gemma 4 CoT tensors, sliding window attention).
11. **AMD Docs Compliance** — Linux uses AMD’s official `ROCm/llama.cpp` fork; `HIPCXX`/`HIP_PATH` set from `hipconfig`; `-DLLAMA_CURL=ON`; `GGML_HIP_ROCWMMA_FATTN=ON` for Gemma 4 attention pattern support.
