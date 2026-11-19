# FX5 r2: review findings on round 1

Risk: high. Model: sol / high.
Sol reason: second round on race, recovery and upgrade-compatibility code after a Sol review found gaps in round 1.

Round 1 (brief `fx5-worktree.md` in this directory, committed as HEAD) was reviewed. Fix every finding below. Read `fx5-worktree.md` first: its Rules section applies unchanged (red test first, no deferral, never weaken tests, keep user data recoverable, old/new compatibility, Python 3.9, no commit, no version/CHANGELOG change).

Priority: a finding marked as a regression versus the release candidate (HEAD~1) or as breaking `518da76`/`v0.12.0` state must be fixed outright, by fixing or by restoring HEAD~1 behaviour for that path. For residual races that no portable primitive can close, narrow the window and make the operation detect the conflict and keep the user's data (recoverable copy, reported, non-zero exit); say exactly what remains in the report as PARTIAL.

## Findings
- `scripts/allow-rule:431` — Cleanup unlinks a pathname after verifying an open inode — an atomic save that replaces the pathname between those steps is silently deleted, while the reread checks the old inode.
- `scripts/dispatch-status:153` — Scope is resolved from the current `-C` path — if a symlink is retargeted after launch, the default listing can expose another repository’s command and brief path.
- `scripts/allow-rule:742` — A prepublication marker can authorize a grant the tool never installed — if an editor moves the staged file into place after the marker is saved but before the tool renames it, recovery adopts the grant and undo can revoke it.
- `scripts/allow-rule:738` — Recovery rejects a valid `518da76` exchange after an in-place edit — a crash before the receipt followed by an unrelated settings edit leaves the published grant without a usable undo record, even with its original inode and intact parked preimage.
- `scripts/allow-rule:677` — Recovery silently skips an edited backup — if the process dies after saving the receipt and an editor then changes the displaced file, retry reports success without identifying the recovery copy.
- `scripts/kaizen_worktree_facts.py:297` — Advisory status now requires writable temporary storage — the read-only sandbox changed all 12 worktree results to `unknown`, while the release candidate classified all 12.
- `scripts/kaizen_worktree_facts.py:280` — A submodule initialized after enumeration is skipped by the separate child scan — if it lands at the expected commit with local edits, the parent status suppresses those edits and reports `clean=true`.
- `scripts/dispatch-status:148` — The scope parser leaves a quoted `~/…` target unexpanded — `codex-dispatch` accepts it, but the default listing hides that same-repository run.

Report per finding: FIXED (test name) or PARTIAL (what remains, how it is detected and recovered).
