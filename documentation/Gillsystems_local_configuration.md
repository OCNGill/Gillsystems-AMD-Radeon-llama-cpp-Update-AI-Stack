# Gillsystems Local Network Configuration

**Last Updated:** April 29, 2026
**Scope:** All Gillsystems projects — authoritative reference for local infrastructure, node identities, IPs, OS, roles, and storage layout.

---

## Network Subnet

| Detail | Value |
|--------|-------|
| **Subnet** | `192.0.2.0/24` |
| **DHCP / Assignment** | Static allocations per node (see below) |

---

## Node Inventory

| Node Name | IP Address | OS | Role | Storage | GPU | RAM | Disk |
|-----------|------------|----|------|---------|-----|-----|------|
| **primary-node** | `192.0.2.10` | Windows 11 Pro | Orchestrator / Primary Compute | 2 TB NVMe | Radeon 7900 XTX (24 GB) | 48 GB | Ryzen 9 5900X |
| **desktop-node** | `192.0.2.42` | Kubuntu | Storage Authority / Worker | 2 TB ZFS | Radeon 7600 (8 GB) | 16 GB | Ryzen 5 5600G |
| **mobile-node** | `192.0.2.93` | Windows 10 | Worker | 1 TB SSD | Vega 6 (integrated) | 20 GB | Ryzen 5 4500U |
| **deck-node** | `192.0.2.139` | SteamOS (Arch Linux) | Worker | 512 GB NVMe | AMD RDNA 2 APU (shared) | 16 GB unified | 512 GB |

---

## Node Details

### primary-node
- **IP:** `192.0.2.10`
- **OS:** Windows 11 Pro x64
- **Role:** Primary orchestrator / heavy compute node
- **Compute Tier:** Tier 1 (Production-Grade)
- **AI Build Target:** `gfx1100` (Navi 31 / RDNA 3)
- **Required Backend:** ROCm / HIP SDK (MUST use GPU; no fallback permitted)
- **CPU:** AMD Ryzen 9 5900X (Zen 3, 12 cores / 24 threads, 3.7 GHz base / 4.8 GHz boost, 64 MB L3, 105W TDP, no iGPU)
- **RAM:** 48 GB
- **GPU:** AMD Radeon 7900 XTX — 24 GB VRAM
- **Storage:** 2 TB NVMe
- **Model Path:** `C:\Models\Working_Models\`
- **LLM Inference Speed:** ~130 tokens/sec
- **Home Directory:** `(C:\Users\<user>) Laptop\`

---

### desktop-node
- **IP:** `192.0.2.42`
- **OS:** Kubuntu (Linux)
- **Role:** Storage authority and secondary worker
- **Compute Tier:** Tier 1 (Production-Grade)
- **AI Build Target:** `gfx1102` (Navi 33 / RDNA 3)
- **Required Backend:** ROCm (MUST use GPU; no fallback permitted)
- **CPU:** AMD Ryzen 5 5600G (Zen 3, 6 cores / 12 threads, 3.9 GHz base / 4.4 GHz boost, 16 MB L3, 65W TDP, integrated Radeon Vega 7)
- **RAM:** 16 GB
- **GPU:** AMD Radeon 7600 — 8 GB VRAM
- **Storage:** 2 TB — ZFS pool (canonical source of truth for the cluster)
  - ZFS Pool Root: `/gillsystems_zfs_pool/AI_storage/`
- **Model Path:** `/home/<user>/Desktop/Models/`
- **LLM Inference Speed:** ~60 tokens/sec
- **Home Directory:** `/home/<user>/`

---

### mobile-node
- **IP:** `192.0.2.93`
- **OS:** Windows 10 x64
- **Role:** Worker node
- **Compute Tier:** Tier 2 (Mobile/Edge)
- **AI Build Target:** `gfx90c` (Renoir / Vega)
- **Required Backend:** Vulkan (Default) or HIP with mandatory `LLAMA_HIP_UMA=1` environment variable
- **CPU:** AMD Ryzen 5 4500U (Zen 2, 6 cores / 6 threads, 2.375 GHz base / 4.0 GHz boost, 8 MB L3, 15W TDP mobile)
- **RAM:** 20 GB
- **GPU:** AMD Radeon Vega 6 (integrated)
- **Storage:** 1 TB SSD
- **Model Path:** `(C:\Users\<user>) Laptop\Desktop\Models\`
- **MAC Address:** `6D:B4:D3:4C:32:C8`
- **LLM Inference Speed:** ~9 tokens/sec
- **Home Directory:** `(C:\Users\<user>) Laptop\`

---

### deck-node
- **IP:** `192.0.2.139`
- **OS:** SteamOS (Arch Linux base)
- **Role:** Worker node
- **Compute Tier:** Tier 2 (Mobile/Edge)
- **AI Build Target:** `gfx1033` (Van Gogh / RDNA 2)
- **Required Backend:** Vulkan (Default) or HIP with mandatory `LLAMA_HIP_UMA=1` environment variable
- **CPU:** AMD Zen 2 (4 cores / 8 threads, up to 3.5 GHz)
- **RAM / VRAM:** 16 GB LPDDR5 unified (shared between CPU and GPU)
- **GPU:** AMD RDNA 2 (8 CUs, integrated APU — draws from unified 16 GB)
- **Storage:** 512 GB NVMe
- **Model Path:** `/home/deck/Desktop/Models/`
- **LLM Inference Speed:** ~30 tokens/sec
- **Home Directory:** `/home/deck/`
- **Hostname:** `deck`

---

## Storage Architecture Summary

```
Cluster Storage Layout
─────────────────────────────────────────────────────────────────
Tier 1 — LOCAL (all nodes)
  Each node maintains fast local storage on its own NVMe/SSD.
  Windows nodes: C:\ drive (NVMe or SSD)
  Linux / SteamOS nodes: /home/<user>/

Tier 2 — CANONICAL (HTPC/ZFS)
  /gillsystems_zfs_pool/AI_storage/
  └── (project-defined subdirectories)
─────────────────────────────────────────────────────────────────
```

**Key principles:**
- **Local-first**: each node reads/writes locally for performance
- **ZFS authority**: HTPC is the single canonical source of truth for the cluster
- **Network resilience**: local storage remains functional if HTPC is unreachable

---

## Node Identity

MAC addresses are the authoritative node identity mechanism (overrides hostname and IP):

| Node | MAC Address |
|------|-------------|
| primary-node | *(auto-detected — record here once confirmed)* |
| desktop-node | *(auto-detected — record here once confirmed)* |
| mobile-node | `6D:B4:D3:4C:32:C8` |
| deck-node | *(auto-detected — record here once confirmed)* |

Identity resolution order: **MAC → Hostname → IP fallback**

---

## Software (Common Baseline)

| Component | Version | Notes |
|-----------|---------|-------|
| **Python** | 3.10.x (3.10.11 recommended) | |
| **Node.js** | v20+ LTS | Required for GUI/frontend work |
| **Git** | Latest | All nodes |

---

## Quick Reference: Node IPs

```
primary-node        192.0.2.10   (Windows — Orchestrator)
desktop-node        192.0.2.42    (Linux   — Storage/Relay)
mobile-node      192.0.2.93    (Windows — Worker)
deck-node  192.0.2.139   (SteamOS — Worker)
```

---

## Server Launcher References

- **Shared templates:** `executables/server_edit_per_node.bat` and `executables/server_edit_per_node.sh` are the editable per-node server launchers in `executables/`.
- **primary-node:** `executables/server_primary_hip_windows.bat` is the dedicated Tier 1 server launcher for the RX 7900 XTX node at `192.0.2.10`.
- **desktop-node:** `executables/server_desktop_rocm_linux.sh` is the dedicated Tier 1 server launcher for the RX 7600 node at `192.0.2.42`.
- **mobile-node:** `executables/server_mobile_uma_windows.bat` is the dedicated Tier 2 server launcher for the Vega 6 node at `192.0.2.93`.
- **deck-node:** `executables/server_deck_vulkan_linux.sh` is the dedicated Tier 2 server launcher for the Steam Deck node at `192.0.2.139`.
- **Round 4 runtime contract:** production launchers now use the Gemma chat template explicitly, cap default generation length per node, and write run logs into the repo-root `logs/` directory.
- **API stop behavior:** OpenAI-compatible callers must still send explicit stop strings such as `"<|im_end|>"` and `"<|im_start|>"` when hard stop-word behavior is required.
- **Executable layout:** updater installs remain canonical at `C:\Gillsystems\llama.cpp\bin` on Windows and `/opt/gillsystems/llama.cpp/bin` on Linux, while successful runs also mirror those binaries into `<llama_cpp_source>/bin` for source-tree launch workflows.

---

*This document is the authoritative local infrastructure reference for all Gillsystems projects. Keep in sync when node IPs or hardware changes.*
