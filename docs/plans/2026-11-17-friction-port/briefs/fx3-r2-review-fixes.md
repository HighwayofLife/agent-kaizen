# FX3 r2: review findings on round 1

Risk: high. Model: sol / high.
Sol reason: second round on race, recovery and upgrade-compatibility code after a Sol review found gaps in round 1.

Round 1 (brief `fx3-actions.md` in this directory, committed as HEAD) was reviewed. Fix every finding below. Read `fx3-actions.md` first: its Rules section applies unchanged (red test first, no deferral, never weaken tests, keep user data recoverable, old/new compatibility, Python 3.9, no commit, no version/CHANGELOG change).

Priority: a finding marked as a regression versus the release candidate (HEAD~1) or as breaking `518da76`/`v0.12.0` state must be fixed outright, by fixing or by restoring HEAD~1 behaviour for that path. For residual races that no portable primitive can close, narrow the window and make the operation detect the conflict and keep the user's data (recoverable copy, reported, non-zero exit); say exactly what remains in the report as PARTIAL.

## Findings
- `scripts/kaizen_friction_actions.py:592` — Closing an action can still exceed the sidecar cap — a valid 1,048,576-byte store with a 2,097,015-byte sidecar left the verified action pending when the next save had to retain both metadata versions.
- `scripts/kaizen_friction_actions.py:534` — A later save can hide the original apply intent from `518da76` — closing at capacity writes `a`, but reopening an unrelated action frees enough space to rewrite it as `terminal`. The historical reader then accepts changing the same generation’s request from `apply` to `suggest`. The new test only removes a request.
- `scripts/kaizen_friction_apply.py:443` — Successful finalization leaves the exchange binding active indefinitely — removing a displaced ledger copy after publication blocks undo before the native inverse runs. HEAD~1 could still undo in that case.
- `scripts/kaizen_friction_apply.py:440` — A directory replacement just before finalization opens the backup directory leaves the displaced copy unreported — the command fails, but its earlier recovery message points to the decoy path. The new test swaps the directory after the FD is already pinned.
- `scripts/kaizen_friction_actions.py:705` — A completed apply written by `518da76` loses its intent on upgrade — replaying the original `apply` fails, while replaying the same action as `suggest` succeeds.

Report per finding: FIXED (test name) or PARTIAL (what remains, how it is detected and recovered).
