# FX4 r2: review findings on round 1

Risk: high. Model: sol / high.
Sol reason: second round on race, recovery and upgrade-compatibility code after a Sol review found gaps in round 1.

Round 1 (brief `fx4-prepare-scheduler.md` in this directory, committed as HEAD) was reviewed. Fix every finding below. Read `fx4-prepare-scheduler.md` first: its Rules section applies unchanged (red test first, no deferral, never weaken tests, keep user data recoverable, old/new compatibility, Python 3.9, no commit, no version/CHANGELOG change).

Priority: a finding marked as a regression versus the release candidate (HEAD~1) or as breaking `518da76`/`v0.12.0` state must be fixed outright, by fixing or by restoring HEAD~1 behaviour for that path. For residual races that no portable primitive can close, narrow the window and make the operation detect the conflict and keep the user's data (recoverable copy, reported, non-zero exit); say exactly what remains in the report as PARTIAL.

## Findings
- `scripts/kaizen-scheduled:3190` — The compatibility check misses the release-candidate helper — the FX4 runner omits its required `host` argument, so a partial upgrade leaves published reviews unacknowledged and subsequent cycles in propose-only mode. The reverse pairing also fails because the FX4 helper rejects the candidate runner’s publication arguments.
- `scripts/kaizen_friction_prepare.py:660` — The compatibility shim can overwrite a foreign `518da76` publication marker — those markers lack `audits`, so a second audit root sharing the backup directory can publish over the first root’s crash-recovery record and strand its acknowledgement.
- `scripts/kaizen_friction_actions.py:654` — An identical apply retry still fails for a completed `518da76` receipt — with the write gates enabled, the old runner records `terminal` without intent metadata, so the new runner loads the receipt but rejects the original request as different.
- `tests/test_friction_prepare.py:154` — The upgrade tests skip when `518da76` is absent from a shallow checkout — depth-1 CI can pass without running either mixed-version test, the legacy publication recovery test, or the signed timing-flag test.

Report per finding: FIXED (test name) or PARTIAL (what remains, how it is detected and recovered).
