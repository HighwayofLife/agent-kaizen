# FX7 r2: review findings on round 1

Risk: high. Model: sol / high.
Sol reason: second round on race, recovery and upgrade-compatibility code after a Sol review found gaps in round 1.

Round 1 (brief `fx7-host-fix.md` in this directory, committed as HEAD) was reviewed. Fix every finding below. Read `fx7-host-fix.md` first: its Rules section applies unchanged (red test first, no deferral, never weaken tests, keep user data recoverable, old/new compatibility, Python 3.9, no commit, no version/CHANGELOG change).

Priority: a finding marked as a regression versus the release candidate (HEAD~1) or as breaking `518da76`/`v0.12.0` state must be fixed outright, by fixing or by restoring HEAD~1 behaviour for that path. For residual races that no portable primitive can close, narrow the window and make the operation detect the conflict and keep the user's data (recoverable copy, reported, non-zero exit); say exactly what remains in the report as PARTIAL.

## Findings
- `scripts/host-fix:449` — Undo and rollback can unlink a replacement at the cleanup name — if a sync restores a different file after the final identity check, the link-count check reports the conflict only after the restored file is gone.
- `scripts/host-fix:449` — Undo can delete the marker outside the eligible worktree — moving the directory after the final scope check lets cleanup unlink through the pinned descriptor and report success.
- `scripts/host-fix:810` — The parent reopens the recovered path outside the timed worker — an unavailable network mount placed over that path after lookup can still block undo beyond 20 seconds.
- `scripts/host-fix:538` — Recovery skips the output’s own same-device bind mount — if a marked directory moves within that mount, the base finds it by inode, while HEAD can report an interrupted undo complete with the quarantined marker still present.

Report per finding: FIXED (test name) or PARTIAL (what remains, how it is detected and recovered).
