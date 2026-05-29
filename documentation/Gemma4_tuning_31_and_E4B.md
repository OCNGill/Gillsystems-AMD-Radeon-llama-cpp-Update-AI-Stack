# Gemma 4 Tuning Reference: 31B (Dense) & E4B (Efficient)

**Created:** 2026-05-29  
**Last Updated:** 2026-05-29  
**Owner:** Gillsystems Decentralized Node Network  
**Scope:** CLI flag reference, per-node configuration, engineering history, known issues

---

## 1. Primary Authority References

### Prompt Formatting & Model Guidance
| Reference | URL | Applicability |
|-----------|-----|---------------|
| Gemma 4 Prompt Formatting (Google) | https://ai.google.dev/gemma/docs/core/prompt-formatting-gemma4 | Chat template, system role, stop tokens for both 31B and E4B |
| Gemma 4 Model Card | https://ai.google.dev/gemma/docs/core/model_card_4 | Architecture, context window (128K native), sampling baselines |
| Gemma 4 Memory Planning | https://ai.google.dev/gemma/docs/core | VRAM requirements per quantization, MTP guidance |

### Model Weights (HuggingFace)
| Model | Repository | GGUF Used In Fleet |
|-------|-----------|-------------------|
| Gemma 4 31B (Dense) | https://huggingface.co/google/gemma-4-31B | `gemma-4-31B.Q4_K_M.gguf` — Main Rig only |
| Gemma 4 E4B (Efficient 4B) | https://huggingface.co/google/gemma-4-2b-it | `gemma-4-E4B.Q6_K.gguf` — HTPC, Laptop, Steam Deck |

### Server Software
| Reference | URL |
|-----------|-----|
| llama.cpp HTTP Server Tools | https://github.com/ggml-org/llama.cpp/tree/master/tools/server |
| llama.cpp Server README | https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md |
| llama.cpp GitHub (ggml-org) | https://github.com/ggml-org/llama.cpp |

---

## 2. Cluster Node Inventory

### Hardware Configuration Matrix

| Node | IP | OS | GPU | VRAM | System RAM | CPU | Build Target | Backend | Model |
|------|----|----|-----|------|-----------|-----|-------------|---------|-------|
| **Gillsystems-Main** | `10.0.0.164` | Windows 11 Pro | Radeon RX 7900 XTX | 24 GB GDDR6 | 48 GB DDR5 | Ryzen 9 5900X (12C/24T) | `gfx1100` (Navi 31 / RDNA 3) | ROCm/HIP SDK | `gemma-4-31B.Q4_K_M.gguf` |
| **Gillsystems-HTPC** | `10.0.0.42` | Kubuntu | Radeon RX 7600 | 8 GB GDDR6 | 16 GB DDR4 | Ryzen 5 5600G (6C/12T) | `gfx1102` (Navi 33 / RDNA 3) | ROCm/HIP | `gemma-4-E4B.Q6_K.gguf` |
| **Gillsystems-Laptop** | `10.0.0.93` | Windows 10 | Radeon Vega 6 (integrated) | Shared (UMA) | 20 GB | Ryzen 5 4500U (6C/6T) | `gfx90c` (Renoir / Vega) | Vulkan (with HIP UMA) | `gemma-4-E4B.Q6_K.gguf` |
| **Gillsystems-Steam-Deck** | `10.0.0.139` | SteamOS (Arch) | AMD RDNA 2 APU (Van Gogh) | Shared 16 GB unified | 16 GB LPDDR5 | Zen 2 (4C/8T) | `gfx1033` (Van Gogh / RDNA 2) | Vulkan | `gemma-4-E4B.Q6_K.gguf` |

### Network Topology
```
Main Rig    10.0.0.164:8010  (Public) ← 127.0.0.1:18010  (Upstream llama-server)
HTPC        10.0.0.42:8011   (Direct llama-server)
Laptop      10.0.0.93:8012   (Direct llama-server)
Steam Deck  10.0.0.139:8013  (Direct llama-server)
```

### Inference Speeds (Approximate)
| Node | Tokens/sec | Notes |
|------|-----------|-------|
| Main Rig (31B Q4_K_M) | ~130 t/s | Full GPU offload, 24 GB VRAM |
| HTPC (E4B Q6_K) | ~60 t/s | ROCm direct, 8 GB VRAM |
| Laptop (E4B Q6_K) | ~9 t/s | UMA shared memory bottleneck |
| Steam Deck (E4B Q6_K) | ~30 t/s | RDNA 2 efficiency |

---

## 3. Complete Engineering History

### Round 1: Bare-Metal Execution & The Unified Memory Wall
- **Date:** ~2026-05-17
- **Objective:** Establish raw model instantiation across all destination nodes
- **Problem:** Initial allocations targeted 128K-256K context size. Main 7900 XTX handled it, but edge nodes (Steam Deck, Laptop) crashed with Vulkan `ErrorDeviceLost`.
- **Root Cause:** Unified memory pools on edge nodes consumed by oversized context windows.
- **Fixes Applied:**
  - Killed background processes (VS Code, RustDesk) to free memory
  - Enforced 32K (`32768`) context on shared-memory nodes
  - Attempted KV cache quantization (`--cache-type-k q8_0`) — freed memory but caused attention matrix corruption
- **CLI Flags Established:** `-c 32768`, `-ngl 99`, `--no-mmap`

### Round 2: Token Repetition & Syntax Contamination
- **Date:** ~2026-05-18
- **Objective:** Maximize generation coherence, eliminate attention hijacking
- **Problem:** HTPC generated infinite recursive loops (`Maximum Page Table Entries`), Laptop looped on ZFS quota text.
- **Root Cause:** Low temperature + uncalibrated repetition penalties → attention hyper-focused on mathematical patterns.
- **Additional Issue:** Manual script editing corrupted caret continuation on Laptop `.bat`.
- **Fixes Applied:**
  - Refactored Laptop `.bat` variable separation (clean `%CTX_SIZE%` to `-c`)
  - Added reverse prompts (`-r "<|im_end|>,<|im_start|>"`) — **later removed in Round 4**
  - Abandoned KV cache quantization (reverted to full precision)
  - Enforced `--no-mmap`

### Round 3: Google Parameter Baseline & Architecture Calibration
- **Date:** ~2026-05-20
- **Objective:** Tailor sampling mechanics to match Gemma 4 architecture
- **Fixes Applied:**
  - Integrated `-b 2048` / `-ub 512` batch sizing
  - Locked `--min-p 0.05`, `--top-k 20` (later revised)
  - Injected `--metrics` for VRAM monitoring
- **Limitations:** Round 3 launchers still had inconsistent parameters across fleet.
- **Sampling Profile at This Time:** `temperature=0`, `min-p=0.05`, `top-k=20`, `top-p=1.0` (deterministic cluster profile)

### Round 4: Launcher Stabilization (20-Expert Panel)
- **Date:** 2026-05-28
- **Trigger:** Shared verification prompt failed across all 4 nodes.
- **Methodology:** 20-expert panel review covering server runtime, Gemma model card, Windows/Linux runtime engineering, AMD GPU specialization, edge inference, prompt templating, regression testing, documentation stewardship.
- **Key Findings:**
  - `--reverse-prompt` (`-r`) was being misused as API stop mechanism (it's for interactive mode only)
  - None of the launchers bounded default generation length with `-n`
  - Main node had no path fallback or log file
  - Laptop node pointed at `C:\llama.cpp\bin\` instead of canonical install root
  - Output analysis: Main ran to 2444 tokens (uncapped), HTPC hit 2352 (circular), Laptop fabricated JSON, Steam Deck hallucinated protocols
- **Fixes Applied (Vote: 20-0 all nodes):**
  - Removed reverse-prompt hack
  - Added explicit Gemma chat-template alignment (`--chat-template gemma` / `--jinja`)
  - Restored deterministic decode profile
  - Added bounded default generation (`-n 2048` Main, `-n 1536` HTPC, `-n 1024` Laptop/Deck)
  - Added node-specific model-path overrides and fallback discovery
  - Standardized log capture across all nodes
  - Added executable/runtime path resolution
  - Preserved `--context-shift`, `--metrics`, `--no-mmap`

### Round 5: Cluster Verification Protocol
- **Date:** 2026-05-28
- **Phase:** Document / Deliver
- **Output:** Formalized verification prompt in `documentation/round-5-cluster-verification-protocol.md`
- **Key Change from Round 4:** Sampling profile shifted from deterministic (`temperature=0`, `top-k=20`, `top-p=1.0`) to Google family baseline (`temperature=1.0`, `top-k=64`, `top-p=0.95`, `min-p=0.05`)
- **Verification Targets:**
  - No runaway output past launcher cap
  - No chat marker leakage
  - Main remains quality answerer
  - Edge nodes produce bounded, deterministic results

### Round 6: Jinja Template Fix & Missing Flags Resolution (Current)
- **Date:** 2026-05-29
- **Objective:** Fix 4 critical bugs discovered during multi-script audit
- **Bugs Found & Fixed:**
  | # | Node | Bug | Severity |
  |---|------|-----|----------|
  | 1 | Main Rig | `--chat-template-file` references non-existent Jinja file on disk | 🔴 CRITICAL — server crashes on start |
  | 2 | HTPC | Blank line inside bash backslash continuation chain drops `--metrics` and `--no-mmap` | 🔴 CRITICAL — flags silently dropped |
  | 3 | HTPC, Laptop, Deck | `-b`/`-ub` batch flags defined but never passed to server | 🟡 MEDIUM — uses defaults |
  | 4 | All 4 nodes | `--repeat-penalty`/`--repeat-last-n` defined but never passed to server | 🟡 MEDIUM — anti-loop mechanism non-functional |
- **Fixes Applied:**
  - Main Rig: Replaced `--chat-template-file` with `--chat-template gemma`
  - HTPC: Removed blank line in continuation chain
  - HTPC, Laptop, Deck: Added `-b`/`-ub` to launch commands
  - All 4 nodes: Added `--repeat-penalty 1.15` and `--repeat-last-n 128`
  - Tests updated to validate all new flags

---

## 4. Production Launcher Configuration Matrix

### Unified Sampling Baseline (All Nodes)
| Parameter | Value | Source |
|-----------|-------|--------|
| `--temperature` | `1.0` | Google Gemma 4 family baseline |
| `--top-k` | `64` | Google Gemma 4 family baseline |
| `--top-p` | `0.95` | Google Gemma 4 family baseline |
| `--min-p` | `0.05` | Google Gemma 4 family baseline |
| `--repeat-penalty` | `1.15` | Google Gemma 4 family baseline |
| `--repeat-last-n` | `128` | Google Gemma 4 family baseline |
| `--jinja` | (flag) | Jinja template engine |
| `--reasoning-format` | `none` | Disable reasoning markup |
| `--context-shift` | (flag) | Static ring tracking |
| `--metrics` | (flag) | Prometheus endpoint |
| `--no-mmap` | (flag) | Disable memory mapping |

### Node-Specific Configuration

#### Gillsystems-Main (`10.0.0.164:8010`)
```
Backend:         ROCm/HIP SDK (gfx1100)
Model:           gemma-4-31B.Q4_K_M.gguf
Context:         -c 49152
Max Tokens:      -n 2048
GPU Layers:      -ngl 99
Flash Attn:      -fa on
Batch:           -b 2048 / -ub 512
KV Cache:        --cache-type-k q8_0 --cache-type-v q8_0
Cache RAM:       --cache-ram 0
Priority:        --prio 2
Chat Template:   --chat-template gemma
Public Port:     8010 (JSON proxy)
Upstream Port:   18010 (llama-server)
Proxy:           scripts/llama_json_proxy.py
```

#### Gillsystems-HTPC (`10.0.0.42:8011`)
```
Backend:         ROCm/HIP (gfx1102)
Model:           gemma-4-E4B.Q6_K.gguf
Context:         -c 32768
Max Tokens:      -n 1536
GPU Layers:      -ngl 99
Flash Attn:      -fa on
Batch:           -b 2048 / -ub 512
Chat Template:   --chat-template gemma
RocBLAS:         ROCBLAS_TENSILE_LIBPATH auto-detected
```

#### Gillsystems-Laptop (`10.0.0.93:8012`)
```
Backend:         Vulkan (HIP UMA if HIP binary)
Model:           gemma-4-E4B.Q6_K.gguf
Context:         -c 32768
Max Tokens:      -n 1024
GPU Layers:      -ngl 99
Flash Attn:      -fa on
Batch:           -b 2048 / -ub 512
Chat Template:   --chat-template gemma
HIP UMA:         LLAMA_HIP_UMA=1 (for HIP builds)
```

#### Gillsystems-Steam-Deck (`10.0.0.139:8013`)
```
Backend:         Vulkan (RADV VANGOGH)
Model:           gemma-4-E4B.Q6_K.gguf
Context:         -c 32768
Max Tokens:      -n 1024
GPU Layers:      -ngl 99
Flash Attn:      -fa on
Batch:           -b 2048 / -ub 512
Chat Template:   --chat-template gemma
Library Path:    LD_LIBRARY_PATH auto-detected
```

---

## 5. Known Issues Registry

### Open Issues

| # | Issue | Affected Nodes | Upstream Status | Workaround |
|---|-------|---------------|-----------------|------------|
| K1 | **rocWMMA not available on Windows HIP SDK** | Main, Laptop | AMD does not ship rocWMMA headers for Windows. Linux-only feature. | FlashAttention works without rocWMMA via tile kernels; ~5-10% throughput reduction on attention-heavy workloads |
| K2 | **FlashAttention tile occupancy warnings** (`-Wpass-failed`) | Main (gfx1100) | Upstream llvm/hipcc scheduling limitation | Kernels compile and function correctly; 1 wave/EU below target. No user-visible impact |
| K3 | **MTP not available for Gemma 4 GGUF** | All | `convert_hf_to_gguf.py` only generates MTP tensors for Qwen 3.5/3.6 | Launchers must NOT use `--spec-type draft-mtp` or related draft flags |
| K4 | **`test-jinja.exe` results on Windows HIP builds** | Main, Laptop | `test-jinja` may fail on Windows due to file path handling in embedded templates | Production server uses `--jinja` + `--chat-template gemma` with GGUF-embedded template, not external file |
| K5 | **Server-side `stop` behavior** | All | `llama-server` does not support server-configured stop words | Client must send explicit `stop: ["<|im_end|>", "<|im_start|>"]` in API requests |

### Resolved Issues

| # | Issue | Resolved In | Fix |
|---|-------|-------------|-----|
| R1 | 128K context crashes edge nodes with Vulkan ErrorDeviceLost | Round 1 | Enforce 32K context on shared-memory nodes |
| R2 | Infinite token repetition loops | Round 2 | Add repeat penalty + bounded generation length; remove reverse-prompt misuse |
| R3 | Caret continuation corruption in Windows batch | Round 2 | Clean variable separation in `.bat` scripts |
| R4 | Reverse-prompt misused as API stop mechanism | Round 4 | Remove `-r` flags; document client-side stop behavior |
| R5 | Missing `-n` generation caps on all nodes | Round 4 | Add `-n` with node-appropriate values |
| R6 | Missing model-path fallback resolution | Round 4 | Add multi-path discovery + env var override hooks |
| R7 | Broken `--chat-template-file` reference to non-existent Jinja file | Round 6 | Replace with `--chat-template gemma` (uses GGUF-embedded template) |
| R8 | Blank line in HTPC bash continuation chain | Round 6 | Remove blank line to restore `--metrics` and `--no-mmap` |
| R9 | `-b`/`-ub` not passed to HTPC, Laptop, Deck | Round 6 | Add batch flags to launch commands |
| R10 | `--repeat-penalty`/`--repeat-last-n` not passed to any node | Round 6 | Add repeat penalty flags to all 4 launch commands |

---

## 6. CLI Flag Reference (llama-server)

### Essential Flags for Gemma 4 Deployment

| Flag | Short | Type | Purpose |
|------|-------|------|---------|
| `--model` | `-m` | Path | Model GGUF file |
| `--ctx-size` | `-c` | Int | Context window (tokens) |
| `--predict` | `-n` | Int | Max tokens to generate |
| `--n-gpu-layers` | `-ngl` | Int | Layers to offload to GPU |
| `--flash-attn` | `-fa` | Flag/on | Enable FlashAttention |
| `--batch-size` | `-b` | Int | Logical batch size (prefill) |
| `--ubatch-size` | `-ub` | Int | Physical mini-batch size |
| `--temp` | | Float | Sampling temperature |
| `--top-k` | | Int | Top-K sampling |
| `--top-p` | | Float | Top-P (nucleus) sampling |
| `--min-p` | | Float | Minimum probability threshold |
| `--repeat-penalty` | | Float | Token repetition penalty |
| `--repeat-last-n` | | Int | Window for repeat penalty |
| `--jinja` | | Flag | Enable Jinja template engine |
| `--chat-template` | | String | Chat template (e.g., `gemma`) |
| `--chat-template-file` | | Path | External Jinja template file (NOT recommended — use `--chat-template`) |
| `--reasoning-format` | | String | Reasoning markup format |
| `--context-shift` | | Flag | Context shift for long sessions |
| `--metrics` | | Flag | Enable Prometheus metrics endpoint |
| `--no-mmap` | | Flag | Disable memory mapping |
| `--cache-type-k` | | String | KV cache quantization (K) |
| `--cache-type-v` | | String | KV cache quantization (V) |
| `--cache-ram` | | Int | RAM cache size |
| `--prio` | | Int | KV cache eviction priority |
| `--port` | | Int | Server port |
| `--host` | | String | Server bind address |
| `--log-file` | | Path | Log file destination |
| `--log-timestamps` | | Flag | Timestamp log entries |

### Flags to AVOID with Gemma 4

| Flag | Reason |
|------|--------|
| `--spec-type draft-mtp` | Gemma 4 GGUF does not contain MTP draft tensors (upstream limitation) |
| `-r` / `--reverse-prompt` | Intended for interactive mode only; does not affect API `/v1/chat/completions` |
| `--chat-template-file` with external file | GGUF metadata already contains the template; use `--chat-template gemma` instead |

---

## 7. Launcher File Reference

| File | Target Node | Language | Path Discovery |
|------|------------|----------|----------------|
| `executables/Gillsystems_Main_AI_Server.bat` | Gillsystems-Main | Windows Batch | Model: `C:\Models\` (hardcoded + `GILLSYSTEMS_MAIN_MODEL_PATH` override). Server: `C:\Gillsystems\llama.cpp\bin\` |
| `executables/Gillsystems-HTPC-AI-server.sh` | Gillsystems-HTPC | Linux Bash | Model: `~/Desktop/Models/` + ZFS pool + `GILLSYSTEMS_HTPC_MODEL_PATH` override. Server: `/opt/gillsystems/llama.cpp/bin/` + source-tree fallback |
| `executables/Gillsystems_Laptop_4500U_Vega6_server.bat` | Gillsystems-Laptop | Windows Batch + PowerShell | Model: `~/Desktop/Models/` + 5 fallback paths + `GILLSYSTEMS_LAPTOP_MODEL_PATH`. Server: multi-path discovery + canonical `C:\Gillsystems\llama.cpp\bin\` |
| `executables/Gillsystems_SteamDeck_AI_Server.sh` | Gillsystems-Steam-Deck | Linux Bash | Model: `~/Desktop/Models/` + ZFS pool + `GILLSYSTEMS_STEAMDECK_MODEL_PATH`. Server: `~/src/llama.cpp/` + `/opt/gillsystems/` |

---

## 8. Test Coverage

| Test File | Coverage |
|-----------|----------|
| `tests/test_server_launchers.py` | Validates all 4 launchers have correct chat template, generation caps, no reverse-prompt, core runtime safeguards, Google sampling profile, main model path, Python resolution, JSON proxy, batch sizes, repeat penalty flags |
| `tests/test_windows_llama_builder.py` | Windows build orchestration correctness |

See [`tests/test_server_launchers.py`](../tests/test_server_launchers.py) for the authoritative regression test suite.

---

## 9. Verification Protocol

To validate cluster readiness after configuration changes, use the Round 5 verification prompt in [`documentation/round-5-cluster-verification-protocol.md`](round-5-cluster-verification-protocol.md).

**Success criteria:**
1. No node generates output past its launcher `-n` cap
2. No node leaks chat markers (`<|im_start|>`, `<|im_end|>`) into output
3. Main node produces highest-quality structured responses
4. Edge nodes produce bounded, deterministic, non-hallucinated output
5. All nodes respond to `/metrics` endpoint with valid Prometheus data

---

*This document is the authoritative engineering reference for Gemma 4 tuning across the Gillsystems cluster. Keep in sync with launcher changes and new round findings.*