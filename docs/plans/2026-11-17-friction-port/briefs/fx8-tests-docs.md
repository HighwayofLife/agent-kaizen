# FX8: sampler bench mode, test-harness robustness, gate brief corrections

Risk: low. Model: terra / medium.

## Items
1. `tests/test_friction_sampler.py --bench` exits 0 with no output (no `__main__`). Add a `__main__` that runs the unit tests normally and, with `--bench`, times the sampler's hot path over a synthetic workload (N iterations, warm-up, median and p95 printed) without network or real config, finishing in under ~30 s.
2. Test-suite robustness (P28 gate): tests fail when the runner was started with SIGHUP or SIGINT ignored, or when `KAIZEN_BACKUP_DIR` or `KAIZEN_USAGE_DB` is set in the environment. Make the affected tests (find them with `rg -n 'SIGHUP|SIGINT|KAIZEN_BACKUP_DIR|KAIZEN_USAGE_DB' tests`) reset those signal dispositions in the child they spawn and scrub those variables from the environments they build, and make `tools/ci-local` scrub them too. Do not change product scripts.
3. `docs/plans/2026-11-17-friction-port/briefs/28-real-input-gate.md`: (a) the prune fixture must age the `.git` pointer, the admin `index` and `logs/HEAD`, and the common branch log to at least 24 h old, not leave the pointer unaged; (b) the single-`--cwd` audit command works only on projects without linked worktrees: say to audit the project together with all its linked worktrees; (c) use symlink-resolved scratch paths on macOS.

## Checks
python3 tests/test_friction_sampler.py; python3 tests/test_friction_sampler.py --bench; python3 -m unittest discover -s tests -p 'test_friction_sampler.py'; then the test files you changed, also run once with `trap '' HUP INT` and with KAIZEN_BACKUP_DIR=/nonexistent KAIZEN_USAGE_DB=/nonexistent exported.

## Rules
- Base: branch `release-0.13` (candidate 0.13.0). `518da76` is the 0.12-era base the friction work started from; `v0.12.0` is the last release. Background for each item: `docs/plans/2026-11-17-friction-port/plan.md` section "0.14 known issues" and `gate-results.md`.
- This is the **fix round for the release**: fix every item properly. Do not defer, do not revert a feature away, and do not report an item as accepted. If a race cannot be closed completely with portable Python on macOS and Linux, close it as far as the platform allows AND make the operation detect the conflict afterwards and keep the user's data (keep the displaced content as a recoverable copy, report it, exit non-zero). Losing user data silently is never acceptable.
- For each item: first a test that fails now (red), then the fix (green). Never weaken, skip or delete an existing test. If an existing test pins the unsafe behaviour, change it to pin the safe behaviour and say why in the report.
- Old/new compatibility matters: state written by `v0.12.0` and by `518da76` must still load, recover and undo after upgrading.
- Stay in the files named here plus their tests. Under ~400 changed lines if you can; say so if you must exceed it. Keep `python3 tools/context_budget.py` passing (the budget is nearly full: do not grow hook or skill context text).
- Python 3.9 compatible. Do not commit or push. Do not touch `.claude-plugin/plugin.json`, `CHANGELOG.md` or the version.
- Report: per item FIXED (test name) or PARTIAL (what remains and how it is detected and recovered), files changed, checks run with results.
