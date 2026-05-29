# Gill Systems AI Stack - Active Reminders

## Round 6 Complete (2026-05-29)
- [x] Fixed Main Rig `--chat-template-file` crash (replaced with `--chat-template gemma`)
- [x] Fixed HTPC broken bash continuation chain (blank line removed)
- [x] Added `--repeat-penalty 1.15 --repeat-last-n 128` to all 4 launchers
- [x] Added `-b 2048 -ub 512` to HTPC launcher
- [x] Tests updated and passing (12/12)
- [x] Dry-run verified on all nodes
- [x] Created `documentation/Gemma4_tuning_31_and_E4B.md` reference doc
- [x] Created `documentation/roos_first_auto_iteration.md` autonomous iteration report
- [x] Created `plans/round-6-launcher-refactor-plan.md` architectural plan

## Verification Steps Remaining
- [ ] **PULL AND TEST ALL NODES**
  - Start with **Main** (192.0.2.10)
  - Verify `server_primary_hip_windows.bat` launches without Jinja file error
  - Run the `tests/test_server_launchers.py` suite on Main
  - Proceed to other nodes:
    - [ ] HTPC (192.0.2.42)
    - [ ] Laptop (192.0.2.93)
    - [ ] Steam Deck (192.0.2.139)
