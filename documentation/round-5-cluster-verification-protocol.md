# Gillsystems Cluster Verification Protocol: Round 5

## Hardware Footprint: Distributed Computing Stack Alignment

### 1. Ingestion Profiling Matrix

Initialize an exhaustive processing chain to verify node stability under the current launcher-aligned Gemma 4 sampling and runtime baselines. The following configuration array must be parsed without generating recursive token replication patterns, format drift, control-token leakage, prompt-template corruption, or memory heap allocation failures.

### 2. Parameter Tuning Verification Bounds

The verification pass must match the current production launcher parameters in this repository.

#### Shared Runtime Baseline

- Logical Execution Batch Size: `-b 2048` (prefill parallelization boundary)
- Physical Multi-Batch Chunking Size: `-ub 512` (APU compute alignment layer)
- Sampling Profile: `--temperature 1.0 | --top-k 64 | --top-p 0.95 | --min-p 0.05`
- Prompt Formatting Stack: `--jinja | --chat-template gemma | --reasoning-format none`
- Core Tracking Flags: `--metrics | --no-mmap | --context-shift`

#### Node-Specific Runtime Bounds

- Main Rig: `-c 49152 | -n 2048 | --cache-type-k q8_0 | --cache-type-v q8_0 | --cache-ram 0`
- HTPC Node: `-c 32768 | -n 1536`
- Laptop Node: `-c 32768 | -n 1024`
- Steam Deck: `-c 32768 | -n 1024`

### 3. Distributed Compute System Architecture Mapping

**Task:** Generate a structural blueprint and definitive analysis mapping the operational topology, structural communication vectors, node role distribution, load balancing parameters, memory-allocation posture, and single-point-of-failure vulnerabilities for the following host network map:

- **Main Rig:** `10.0.0.164:8010` (Primary Orchestrator)
- **HTPC Node:** `10.0.0.42:8011` (High-Precision Processing Edge)
- **Laptop Node:** `10.0.0.93:8012` (Telemetry / Sync Worker)
- **Steam Deck:** `10.0.0.139:8013` (Local Validation Node)

### 4. Verification Requirements

The report must explicitly verify all of the following:

- Prompt formatting remains Gemma-aligned across all nodes and does not regress into malformed control-token output.
- The current sampling profile is respected exactly as deployed: `temperature 1.0`, `top-k 64`, `top-p 0.95`, `min-p 0.05`.
- Batch execution remains aligned at `-b 2048` and `-ub 512` across the cluster.
- Main node memory posture reflects the current 24 GB VRAM containment strategy: q8_0 KV cache plus `--cache-ram 0`.
- No node analysis should assume legacy `top-k 20`, deterministic `temperature 0`, or removed repeat-penalty flags.

### 5. Output Requirement

Deliver a detailed processing report containing:

- An ingestion matrix
- A parameter verification section
- A structural text diagram
- A step-by-step role distribution layout
- A memory-footprint assessment per node
- A bottleneck and failure-domain summary

Output must be structured, complete, and non-truncated.