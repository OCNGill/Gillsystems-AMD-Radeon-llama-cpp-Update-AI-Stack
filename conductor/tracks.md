# Tracks Registry

## Active Tracks
| Track | Folder | Status | 7D Phase |
|-------|--------|--------|----------|
| T-001: Agent Architecture & Core | `conductor/tracks/T-001-agent-core/` | **Round 6 complete — 4 launcher bugs fixed, tests at 12/12** | Debug / Document |

## Delivered Tracks
| Track | Version | Date | Notes |
|-------|---------|------|-------|
| T-001: Agent Architecture & Core | v2.4.0 | 2026-05-29 | **Round 6:** 4 launcher bugs fixed. Main Rig: Jinja file crash fixed (uses `--chat-template gemma`). HTPC: broken bash continuation fixed. All 4 nodes: `--repeat-penalty`/`--repeat-last-n` now active. HTPC: `-b`/`-ub` batch flags added. 12/12 tests pass. Engineering reference consolidated in `documentation/Gemma4_tuning_31_and_E4B.md`. |
| T-001: Agent Architecture & Core | v2.3.0 | 2026-05-28 | Round 5 optimization: KV-cache q8_0 on main 31B launcher, `--chat-template gemma` removed from main launcher (31B GGUF embeds its own template), edge-node launchers retain the flag. All 8 launcher tests pass. |
| T-001: Agent Architecture & Core | v2.1.0 | 2026-05-27 | Round 3 shipped a launcher profile that later regressed under the shared cluster verification prompt. Round 4 corrects the production launchers in-repo and keeps the same prompt for the live rerun. |
