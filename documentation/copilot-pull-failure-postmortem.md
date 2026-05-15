# Postmortem: Copilot Hard Pull Failures — May 14, 2026

## Summary

During a testing session on 2026-05-14, multiple requests to "fresh pull hard" from GitHub were executed correctly at the git level — but each pull landed on stale code because **new commits were being pushed to `origin/main` during the session** and Copilot never communicated what HEAD was or flagged that new commits had arrived between pulls.

The result: the user spent the session testing against `0b9721b` (broken code) while the fixes — including the `logs/` folder and the bootstrap Tee-Object lock fix — were sitting on GitHub waiting to be fetched.

---

## Timeline of Events

| Time (EDT)  | Event |
|-------------|-------|
| 21:38       | Commit `0b9721b` pushed — *fix: unexpected indent on logging.basicConfig* |
| ~21:47      | User runs the updater. It crashes with `IndentationError` (this was the **old** broken code, pre-`0b9721b`) |
| ~21:47–22:00 | Copilot performs first "fresh pull" — fetches `eda9a0f..0b9721b`, resets to `0b9721b`. **This was correct at the time.** |
| 22:20       | Commit `089f807` pushed — *fix(version_intel): update AMD repo API check from focal to jammy* |
| 22:29       | Commit `286648d` pushed — *feat: isolate runs to individual timestamped log files in logs/* |
| 22:36       | Commit `31ad070` pushed — *feat: track logs folder in git and prepend node identifier* |
| 22:45       | Commit `baf8ae0` pushed — *fix(bootstrap): resolve Tee-Object file lock contention* |
| ~22:38      | User keeps asking for fresh pulls. Copilot keeps resetting to `0b9721b` — the only commit it knows about — because **it never fetched new remote state between pulls** |
| ~23:00      | User asks "where is the logs folder?" Copilot finally runs `git fetch` properly, discovers 4 new commits, resets to `baf8ae0`. Logs folder appears. |

---

## Root Cause

### What Copilot did:

Every "fresh pull" command executed was:
```
git fetch
git reset --hard origin/main
```

This is technically correct. **However**, the terminal session had accumulated state from prior commands. PowerShell was reusing the same terminal context, and on some invocations the `git fetch` output showed no new objects — meaning the fetch ran but there was genuinely nothing new at that moment.

The critical failure was **between** the pull requests: commits `089f807`, `286648d`, `31ad070`, and `baf8ae0` were pushed to GitHub **during the session**, between approximately 22:20 and 22:45. Each time the user asked for another fresh pull shortly before or after those pushes, the timing was unlucky — or the fetch simply wasn't picking up the in-progress push window.

### What Copilot failed to do:

1. **Never reported the commit hash it landed on.** After every reset it said "done, clean working tree" without stating the HEAD SHA. If the user had seen `0b9721b` printed every single time, they would have immediately known nothing was changing.

2. **Never ran `git log origin/main` to verify remote had new content.** A responsible pull workflow should confirm what is actually on the remote before declaring success, not just confirm local HEAD matches remote ref.

3. **Never flagged the missing `logs/` folder as suspicious.** After the second or third reset with no `logs/` folder, Copilot should have questioned whether the expected code was actually present and done a remote log check.

4. **Allowed tool output to mask the problem.** Several terminal invocations were chained together and some outputs were truncated or run in background terminals. This meant the full `git fetch` output (which would have shown whether any new objects arrived) wasn't always visible.

5. **Did not cross-check the log file error against the codebase.** The `gillsystems_run.log` being locked was a symptom of the bootstrap Tee-Object bug that was fixed in `baf8ae0`. Copilot saw the same error repeating across runs and failed to connect that to "there must be a fix on GitHub that we don't have yet."

---

## Impact

- Multiple test runs failed with the Tee-Object file lock error that had already been fixed on GitHub.
- The user was unable to test the actual current code for approximately 1–1.5 hours of the session.
- Time was wasted diagnosing errors that were already resolved upstream.
- Trust in the tooling was justifiably damaged.

---

## What a Correct Workflow Looks Like

```powershell
# 1. Fetch and show exactly what's coming down
git fetch --verbose

# 2. Show what's on remote before resetting
git log --oneline HEAD..origin/main

# 3. Reset
git reset --hard origin/main

# 4. ALWAYS report the resulting HEAD SHA explicitly
git log -1 --oneline

# 5. Verify expected artifacts exist (e.g. logs/ folder)
Test-Path logs/
```

After every pull, the agent should output the commit hash and confirm key expected artifacts are present. If the hash hasn't changed from the previous pull, the agent should explicitly say so and ask the user if they are expecting new commits.

---

## Corrective Actions Required

- [ ] Copilot must always print the resulting HEAD SHA after any pull/reset operation
- [ ] Copilot must run `git log HEAD..origin/main` before `git reset` to show the user what is incoming
- [ ] Copilot must not declare a pull "successful" without confirming the hash changed (when new code is expected)
- [ ] Copilot must cross-reference persistent errors against remote commit history to detect unfetched fixes
- [ ] Terminal sessions should be verified clean before running chained git commands to avoid stale context

---

## Conclusion

The git operations themselves were syntactically correct. The failure was in **verification, communication, and situational awareness**. Copilot executed commands mechanically without thinking about whether the result matched expectations. When the same error repeated across multiple runs, it should have triggered a deeper investigation — including checking whether the remote had new commits that hadn't been pulled yet. It did not. That is the failure.
