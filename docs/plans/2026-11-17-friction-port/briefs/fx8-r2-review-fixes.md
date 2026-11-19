# FX8 r2: review findings on round 1

Risk: low. Model: terra / medium.

Round 1 (brief `fx8-tests-docs.md` in this directory, committed as HEAD) was reviewed. Fix every finding below. Read `fx8-tests-docs.md` first: its Rules section applies unchanged (red test first, no deferral, never weaken tests, keep user data recoverable, old/new compatibility, Python 3.9, no commit, no version/CHANGELOG change).

Priority: a finding marked as a regression versus the release candidate (HEAD~1) or as breaking `518da76`/`v0.12.0` state must be fixed outright, by fixing or by restoring HEAD~1 behaviour for that path. For residual races that no portable primitive can close, narrow the window and make the operation detect the conflict and keep the user's data (recoverable copy, reported, non-zero exit); say exactly what remains in the report as PARTIAL.

## Findings
- `tests/test_schedule_followup.py:112` — The kill tests proceed when the grandchild PID file exists but is still empty — killing the writer in that window leaves `assert_helper_gone()` parsing an empty string and failing even when cleanup worked.
- `tests/test_schedule_robustness.py:75` — The checked-in signal tests never arrange for the launcher to inherit ignored SIGHUP or SIGINT — removing the reset here or in the dispatch fixture can pass normal CI while restoring the failure under `trap '' HUP INT`.
- `tools/ci-local:24` — The environment regression test covers only `StubCase` — deleting the CI scrub leaves that test green while CI subprocesses inherit the caller’s backup and usage database paths.
- `tests/test_friction_sampler.py:65` — The benchmark test accepts the literal output `median p95` — it passes without numeric timings, an iteration count, or a warm-up count.

Report per finding: FIXED (test name) or PARTIAL (what remains, how it is detected and recovered).
