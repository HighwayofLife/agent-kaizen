# FX6 r2: review findings on round 1

Risk: high. Model: sol / high.
Sol reason: second round on race, recovery and upgrade-compatibility code after a Sol review found gaps in round 1.

Round 1 (brief `fx6-probe-skill.md` in this directory, committed as HEAD) was reviewed. Fix every finding below. Read `fx6-probe-skill.md` first: its Rules section applies unchanged (red test first, no deferral, never weaken tests, keep user data recoverable, old/new compatibility, Python 3.9, no commit, no version/CHANGELOG change).

Priority: a finding marked as a regression versus the release candidate (HEAD~1) or as breaking `518da76`/`v0.12.0` state must be fixed outright, by fixing or by restoring HEAD~1 behaviour for that path. For residual races that no portable primitive can close, narrow the window and make the operation detect the conflict and keep the user's data (recoverable copy, reported, non-zero exit); say exactly what remains in the report as PARTIAL.

## Findings
- `scripts/host-probe:277` — The probe checks index flags before status reads the live index — setting `assume-unchanged` on a modified file between those reads makes a dirty worktree look prunable, while the base’s later flag check catches it.
- `skills/cycle/SKILL.md:24` — Canonical audit lookup still depends on local enrollment — when only the main checkout has a ledger, the skill asks the user to enroll again and `config show` points to the linked checkout. The test commits the ledger before creating the worktree, so it misses this case.
- `scripts/host-probe:463` — Descriptor thinning starts too late for a low file-descriptor limit — with 20 descriptors available, a deep branching output tree loses all directory evidence, while the base completes the scan.

Report per finding: FIXED (test name) or PARTIAL (what remains, how it is detected and recovered).
