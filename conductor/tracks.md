# Tracks Registry

## Active Tracks
| Track | Folder | Status | 7D Phase |
|-------|--------|--------|----------|
| T-001: Agent Architecture & Core | `conductor/tracks/T-001-agent-core/` | **Round 8 complete — packaged (wheel/sdist), multi-gen GPU detection, privacy scrub; tests at 113/113** | Delivered |

## Delivered Tracks
| Track | Version | Date | Notes |
|-------|---------|------|-------|
| T-001: Agent Architecture & Core | v2.6.0 | 2026-09-21 | **Round 8:** invalid build-backend fixed → wheel + sdist build clean and install-verified in a fresh venv. GPU detection covers all AMD gens: PCI `7480` mislabel corrected (Navi 33 → gfx1102), Vega/UMA iGPU IDs added (Raven/Picasso/Renoir/Cezanne → gfx90c), Rembrandt 680M → gfx1035, Phoenix 780M → gfx1103, RDNA3 dGPU additions. llama_builder `bin_dir` NameError fixed. Full privacy scrub: node names/IPs (RFC 5737)/usernames/handles removed from all tracked files + git history (filter-repo, author identity mailmapped); per-node launchers renamed to generic per-profile names. 113/113 tests pass. |
| T-001: Agent Architecture & Core | v2.5.0 | 2026-09-17 | **Round 7:** headless sudo validation (`sudo -n whoami`), ROCm install timeout 1800s + `GILL_ROCM_TIMEOUT`, `--skip-rocm` no longer demands root. Verified headless end-to-end on the desktop node. |
| T-001: Agent Architecture & Core | v2.4.0 | 2026-05-29 | **Round 6:** 4 launcher bugs fixed. Main Rig: Jinja file crash fixed (uses `--chat-template gemma`). HTPC: broken bash continuation fixed. All 4 nodes: `--repeat-penalty`/`--repeat-last-n` now active. HTPC: `-b`/`-ub` batch flags added. 12/12 tests pass. Engineering reference consolidated in `documentation/Gemma4_tuning_31_and_E4B.md`. |
| T-001: Agent Architecture & Core | v2.3.0 | 2026-05-28 | Round 5 optimization: KV-cache q8_0 on main 31B launcher, `--chat-template gemma` removed from main launcher (31B GGUF embeds its own template), edge-node launchers retain the flag. All 8 launcher tests pass. |
| T-001: Agent Architecture & Core | v2.1.0 | 2026-05-27 | Round 3 shipped a launcher profile that later regressed under the shared cluster verification prompt. Round 4 corrects the production launchers in-repo and keeps the same prompt for the live rerun. |
