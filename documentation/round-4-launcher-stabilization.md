# Round 4 Launcher Stabilization Report

**Date:** 2026-05-28
**Phase:** Debug / Document / Deliver
**Status:** Round 3 failed on the shared verification prompt. Round 4 launcher corrections are implemented in-repo and awaiting live node reruns.

---

## 1. Upstream References Used

This round 4 analysis was anchored to the following upstream sources instead of prior repo assumptions alone:

1. **llama.cpp HTTP Server README**
   https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
2. **Gemma 4 model card**
   https://ai.google.dev/gemma/docs/core/model_card_4
3. **Gemma 4 model overview / memory planning**
   https://ai.google.dev/gemma/docs/core

**Important note:** Google publishes the Dense 31B and Dense E4B guidance on the same public Gemma 4 family documents. For this report, the requested “31B model card” and “E4B model card” references are the Dense 31B and Dense E4B sections of the Gemma 4 model card plus the Gemma 4 memory-planning page.

---

## 2. Twenty-Expert Review Panel

| Expert | Specialty | Round 4 conclusion |
|---|---|---|
| 1. Server Runtime Analyst | llama.cpp server behavior | `-r/--reverse-prompt` was being used as if it were an API stop mechanism; upstream docs say it is for interactive mode, not OpenAI-style chat completions. |
| 2. Gemma Model Card Analyst | Gemma 4 best practices | The fleet drifted away from upstream usage guidance on template handling and mixed inconsistent sampling profiles across nodes. |
| 3. Output Quality Auditor | Prompt-following and structure | The round 3 outputs were not stable: one node ran away, two fabricated neat but false structures, and one produced padded nonsense. |
| 4. Windows Runtime Engineer | Windows launcher reliability | The Main launcher lacked production-grade checks and logging; the Laptop launcher used a non-canonical binary path and needed fallback resolution. |
| 5. Linux Runtime Engineer | Linux launcher reliability | HTPC and Steam Deck launchers needed executable/library pairing discipline and root-log consistency. |
| 6. AMD Runtime Specialist | ROCm/HIP/Vulkan packaging | Production launchers must resolve the actual runtime tree they launch from and expose ROCBLAS support files when present. |
| 7. Edge Inference Specialist | Constrained hardware behavior | The edge nodes need capped generation length more than they need exotic sampling tweaks. |
| 8. Prompt Template Specialist | Chat formatting | Explicit Gemma chat-template alignment is safer than depending on accidental defaults when the workload is strict structured reporting. |
| 9. Regression Engineer | Preventing future drift | The repo had no launcher regression tests, so the round 3 drift was invisible until live prompts failed. |
| 10. Documentation Steward | Repo truthfulness | README, UserGuide, local configuration, changelog, and conductor status all overstated round 3 readiness and referenced stale launcher names or behaviors. |
| 11. Field Failure Reviewer | Real-run evidence triage | The first round 4 fix set did not actually fit the field evidence: Main failed at startup while Deck and HTPC degraded qualitatively under the looser sampler. |
| 12. Windows Path Auditor | Node-local storage conventions | The Main node launcher ignored the canonical `C:\Models\Working_Models\` root documented elsewhere in the repo and instead assumed a single brittle path. |
| 13. Linux Ops Reviewer | Operator ergonomics | The Linux launchers needed model-path override hooks so field corrections do not require ad hoc file edits on the node. |
| 14. Determinism Specialist | Reproducible inference | This workload is a verification prompt, not a creative chat session, so deterministic decoding is a better operational default than a loose family-wide sampler. |
| 15. Structured Output Reviewer | JSON and code extraction reliability | The bad Steam Deck and HTPC outputs fit a decoder drift problem more than a raw hardware-capacity problem. |
| 16. Test Strategy Reviewer | Gap analysis | The first regression suite only checked template, caps, and reverse-prompt removal, so it never protected decoding policy or model-root assumptions. |
| 17. Config Consistency Auditor | Repo contract alignment | Local configuration, changelog history, and launcher text all pointed to a stricter cluster baseline than the first round 4 patch actually enforced. |
| 18. Runtime Diagnostics Reviewer | Dry-run behavior | Dry-run mode needs to surface missing binaries or model files immediately so operators can catch broken nodes before a live attempt. |
| 19. Fleet Consistency Reviewer | Cross-node parity | The fleet should share one verification decode contract unless a node has a proven hardware reason to diverge. |
| 20. Delivery Reviewer | Ship-readiness | A launcher change is not complete if the docs still instruct operators to use a dead path or a superseded decode profile. |

---

## 3. What Failed In Round 3

### Code Findings

- All four production launchers were inconsistent with each other.
- The Main launcher had no path fallback, no log file, and no bounded generation length.
- The Laptop launcher pointed at `C:\llama.cpp\bin\llama-server.exe` instead of the repo’s canonical install root or a mirrored source-tree fallback.
- All four production launchers used the combined reverse-prompt string `"<|im_end|>,<|im_start|>"` even though upstream `llama-server` documentation defines reverse prompts as interactive halts, not API default stop words.
- None of the production launchers bounded default generation length with `-n`, so requests without client-side `max_tokens` could run effectively unbounded.

### Output Findings From The Attached Round 3 Logs

- **Main 31B:** the second main-node log ran to `predicted_n = 2444` and spilled back into chat markers plus a massive repetitive word-salad tail, which is classic uncapped-generation failure.
- **HTPC E4B:** the HTPC log reached `predicted_n = 2352` and devolved into padded, circular explanation rather than completing the requested structure cleanly.
- **Laptop E4B:** the laptop log returned neat-looking JSON quickly, but it fabricated unsupported architecture details and even contradicted the prompt’s own flag set by reporting `--no-mmap` as false.
- **Steam Deck E4B:** the Steam Deck log also returned plausible-looking JSON, but it hallucinated protocol details like per-node TCP/UDP vectors that were never in the prompt or launcher definitions.

### Upstream Mismatch Summary

- The **llama.cpp server docs** explicitly support request-level `stop` arrays for API completions; the launchers were pretending a reverse-prompt flag would solve that at the server level.
- The **Gemma 4 model card** recommends a standard family baseline of `temperature=1.0`, `top_p=0.95`, and `top_k=64`, but that generic sampler was not the right operational choice for this repo's deterministic cluster-validation prompt.
- The **Gemma 4 overview** makes clear that E4B and 31B have very different memory footprints, so the node-specific path forward should be based on runtime caps and hardware roles, not one-size-fits-all “infinite output” assumptions.

---

## 4. Vote Outcomes By Node

| Node | Winning path | Vote | Why this won |
|---|---|---|---|
| **Gillsystems-Main** | Keep `gemma-4-31B.Q4_K_M.gguf`, keep the larger context, add explicit Gemma chat-template, resolve the model from canonical node roots, remove reverse-prompt hack, and cap default output at `2048` tokens | 20-0 | The 31B node is still the primary quality node. The missed failure mode was not model quality; it was a bad hardcoded model path plus the earlier stop-handling mistakes. |
| **Gillsystems-HTPC** | Keep `gemma-4-E4B.Q6_K.gguf`, align to Gemma template, restore the deterministic cluster sampler, resolve binary/lib/runtime directories coherently, and cap output at `1536` tokens | 20-0 | The HTPC should remain the balanced Linux worker. The first round 4 pass got the sampler wrong by drifting from the repo's deterministic cluster baseline to a looser generic profile. |
| **Gillsystems-Laptop** | Keep `gemma-4-E4B.Q6_K.gguf`, add Windows fallback resolution, keep Tier 2 compatibility via `LLAMA_HIP_UMA=1`, restore the deterministic cluster sampler, and cap output at `1024` tokens | 20-0 | The laptop is a constrained edge node. Reliability comes from bounded output, deterministic decoding, and runtime-path correctness. |
| **Gillsystems-Steam-Deck** | Keep `gemma-4-E4B.Q6_K.gguf`, preserve Vulkan library pairing, add root log capture, restore the deterministic cluster sampler, and cap output at `1024` tokens | 20-0 | The Deck already had the right high-level runtime pairing. The field failure showed the first round 4 sampler change made the node too loose for this verification workload. |

---

## 5. Why Each Node Now Uses Its Chosen Path

### Main Rig

- This is the only node carrying the Dense 31B model, so it remains the primary answer-quality node.
- The fix targets the real fault line: the launcher was pointing at the wrong Windows model root and still needed bounded output when the client does not send `max_tokens` or explicit stop strings.
- The launcher now behaves like a production script instead of a raw one-off command line.

### HTPC

- The HTPC remains the best Linux fallback worker with stable fixed power, real VRAM, and room for persistent logging.
- The first round 4 pass replaced the repo's deterministic validation profile with a looser generic sampler, and that drift shows up directly in the bad field outputs.
- The node now resolves its executable, shared libraries, and rocBLAS support tree as a coherent unit.

### Laptop

- The laptop is a mobile edge node, so the correct move is to cap generation aggressively and keep runtime discovery flexible.
- The laptop now follows the same deterministic decode contract as the rest of the fleet instead of a node-specific generic sampler.
- The round 4 path also preserves HIP UMA compatibility without forcing HIP-only operation if the local binary is actually Vulkan-backed.
- The node is now aligned with the canonical install root and mirrored source-tree behavior documented elsewhere in the repo.

### Steam Deck

- The Steam Deck remains a Vulkan-first edge validator.
- The main value of round 4 here is not changing the hardware strategy; it is tightening launch discipline so the node produces bounded, deterministic, inspectable results instead of optimistic but unverifiable output.
- Logging is now first-class, which matters on the Deck because transient failures are otherwise hard to reconstruct.

---

## 6. Executed Round 4 Fixes

The repo changes for round 4 were executed one file at a time in this order:

1. `executables/Gillsystems_Main_AI_Server.bat`
2. `executables/Gillsystems-HTPC-AI-server.sh`
3. `executables/Gillsystems_Laptop_4500U_Vega6_server.bat`
4. `executables/Gillsystems_SteamDeck_AI_Server.sh`
5. `tests/test_server_launchers.py`

Common corrections across the production launchers:

- Added explicit Gemma chat-template alignment.
- Restored the deterministic cluster decode profile (`--temperature 0 --min-p 0.05 --top-k 20 --top-p 1.0`).
- Added bounded default generation length with `-n`.
- Removed the reverse-prompt stop hack.
- Added node-specific model-path overrides and fallback discovery.
- Added or standardized log capture.
- Added better executable/runtime path resolution.
- Preserved `--context-shift`, `--metrics`, and `--no-mmap`.

---

## 7. Round 4 Validation Prompt

Round 4 intentionally keeps the same verification prompt because round 3 failed on it and the comparison needs to stay apples-to-apples.

```markdown
## Gillsystems Cluster Verification Protocol: Round 3

## Hardware Footprint: Distributed Computing Stack Alignment

### 1. Ingestion Profiling Matrix

[Initialize an exhaustive processing chain to verify node stability under the Google-tuned sampling baselines. The following configuration array must be parsed without generating recursive token replication patterns or encountering memory heap allocation crashes.]

### 2. Parameter Tuning Verification Bounds

* Logical Execution Batch Size: -b 2048 (Prefill Parallelization Boundary)
* Physical Multi-Batch Chunking Size: -ub 512 (APU Compute Alignment Layer)
* Filter Selection Cut-offs: --min-p 0.05 | --top-k 20 (Google-Optimized Baseline)
* Core Tracking Flags: --metrics | --no-mmap | --context-shift (Static Ring Tracking)

### 3. Distributed Compute System Architecture Mapping

**Task:** Generate a structural blueprint and definitive analysis mapping the operational topology, structural communication vectors, node role distribution, load balancing parameters, and single-point-of-failure vulnerabilities for the following host network map:

* **Main Rig:** `10.0.0.164:8010` (Primary Orchestrator)
* **HTPC Node:** `10.0.0.42:8011` (High-Precision Processing Edge)
* **Laptop Node:** `10.0.0.93:8012` (Telemetry / Sync Worker)
* **Steam Deck:** `10.0.0.139:8013` (Local Validation Node)

**Output Requirement:** Deliver a detailed processing report containing an ingestion matrix, parameter check, structural text diagram, and step-by-step role distribution layout. Output must be structured, deterministic, and complete. Do not truncate.
```

---

## 8. Round 4 Success Criteria

- No node should generate runaway output past its launcher cap.
- No node should leak back into raw chat markers as a substitute for stopping.
- The Main node should remain the preferred quality answerer for this workload.
- HTPC, Laptop, and Steam Deck should act as bounded worker/validation nodes rather than pretending to be unconstrained report writers.
- Client-side callers must still send explicit `stop` strings for OpenAI-compatible chat requests when they need hard stop-word behavior.

---

## 9. Final Review Position

The panel’s unanimous position is that **round 3 did not fail because the hardware fleet was incapable**. It failed because launcher behavior drifted away from what `llama-server` and Gemma 4 actually expect in production: bounded outputs, correct chat-template handling, coherent runtime resolution, and honest documentation about API stop behavior.