# FX2 r2: review findings on round 1

Risk: high. Model: sol / high.
Sol reason: second round on race, recovery and upgrade-compatibility code after a Sol review found gaps in round 1.

Round 1 (brief `fx2-token-audit.md` in this directory, committed as HEAD) was reviewed. Fix every finding below. Read `fx2-token-audit.md` first: its Rules section applies unchanged (red test first, no deferral, never weaken tests, keep user data recoverable, old/new compatibility, Python 3.9, no commit, no version/CHANGELOG change).

Priority: a finding marked as a regression versus the release candidate (HEAD~1) or as breaking `518da76`/`v0.12.0` state must be fixed outright, by fixing or by restoring HEAD~1 behaviour for that path. For residual races that no portable primitive can close, narrow the window and make the operation detect the conflict and keep the user's data (recoverable copy, reported, non-zero exit); say exactly what remains in the report as PARTIAL.

## Findings
- `scripts/token-audit:3021` — Extract publication suppresses temporary-link cleanup failures — the audit can exit 0 with a two-link extract that `allow-rule` rejects, blocking access to older valid extracts in the same store.
- `scripts/token-audit:3000` — The publication check compares only inode identity — an in-place write after linking passes verification, destroys the original extract bytes, and leaves the report bound to a stale hash.
- `scripts/token-audit:526` — Claude usage takes the first `timestamp` anywhere in the row — a pre-window nested timestamp before an in-window top-level timestamp drops the call count from 1 in the release candidate to 0.
- `scripts/token-audit:3089` — A symlinked Claude config still supplies unresolved transcript paths to the trusted reader — the extract is written, but accepted permissions are omitted and `allow-rule` cannot use it. The new symlink test has no transcript.
- `scripts/token-audit:148` — Oversized Codex output is validated one non-ASCII character at a time — a 4 MB UTF‑8 fixture took about 0.62 s versus 0.001 s in the release candidate, even with friction disabled.

Report per finding: FIXED (test name) or PARTIAL (what remains, how it is detected and recovered).
