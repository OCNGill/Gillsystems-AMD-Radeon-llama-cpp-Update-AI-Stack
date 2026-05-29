# Gillsystems Update AI Engine Software — Conductor Index

## Project
**Gillsystems AI Stack Updater Agent**

An autonomous, reboot-resilient agent system that keeps ROCm/HIP and llama.cpp always at their latest stable versions across Windows and Linux — targeting AMD consumer GPUs.

## Authoritative Files
- `conductor/index.md` ← You are here
- `conductor/product.md`
- `conductor/product-guidelines.md`
- `conductor/tech-stack.md`
- `conductor/tracks.md`
- `conductor/workflow.md`
- `conductor/setup_state.json`

## Status
**Phase:** Debug / Document — Round 6 complete: 4 launcher bugs fixed (Jinja template crash, broken bash continuation, missing repeat-penalty, missing batch flags). All launchers now pass `--repeat-penalty 1.15 --repeat-last-n 128`. Main launcher uses `--chat-template gemma` (no external Jinja file). Engineering reference consolidated.
**Version:** 2.4.0
**Last Updated:** 2026-05-29
**Round 6 Summary:** 4 bugs fixed across 4 production launcher scripts. 12/12 tests passing. See [`CHANGELOG.md`](../CHANGELOG.md) and [`documentation/Gemma4_tuning_31_and_E4B.md`](../documentation/Gemma4_tuning_31_and_E4B.md) for authoritative reference.
