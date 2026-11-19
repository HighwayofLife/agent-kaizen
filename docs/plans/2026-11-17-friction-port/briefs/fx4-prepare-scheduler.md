# FX4: friction prepare and scheduler upgrade compatibility

Risk: high. Model: sol / high.
Sol reason: protocol compatibility between old/new runner and helper across an upgrade, signed-input digests and broker recovery.

## Items
1. `scripts/kaizen-scheduled:3129` — the runner and publication helper use incompatible calling conventions across the upgrade: an old runner skips project reviews with the new helper, and a new runner forces propose-only reviews with the old helper. Make both directions work (version handshake or accept both conventions), with tests that pair old (`518da76`) and new code each way.
2. `scripts/kaizen_friction_prepare.py:621` — publication validation and audit-root checks can bypass broker recovery: a malformed marker or a marker owned by another audit root can strand actions that `518da76` recovered. Recovery must run first and must not be skipped by those checks.
3. `scripts/kaizen_friction_prepare.py:463` — reconciliation recomputes the view digest using the new flag format: valid signed v1 inputs prepared by `518da76` with timing-basis flags can no longer be imported or acknowledged after upgrading. Compute the digest in the format the input was signed with.
4. `scripts/kaizen_friction_prepare.py:426` (deferred from FA3) — scheduled replay drops a completed action from the reconstructed request before reaching `import_actions`; the production path rejects an identical retry after successful application. An identical retry must be accepted idempotently.
5. P28 gate: `friction prepare` on an audit run with a single `--cwd` on a project that has linked worktrees is refused with the generic 'preparation refused; local evidence or private state is invalid or unavailable'. Keep the refusal, but print a specific reason telling the user to audit the project with all its linked worktrees (and how).

## Checks
python3 -m unittest discover -s tests -p 'test_friction_prepare.py'; test_friction_review.py; test_schedule.py; test_schedule_steps.py; test_schedule_security.py; test_schedule_robustness.py; test_runner.py.

## Rules
- Base: branch `release-0.13` (candidate 0.13.0). `518da76` is the 0.12-era base the friction work started from; `v0.12.0` is the last release. Background for each item: `docs/plans/2026-11-17-friction-port/plan.md` section "0.14 known issues" and `gate-results.md`.
- This is the **fix round for the release**: fix every item properly. Do not defer, do not revert a feature away, and do not report an item as accepted. If a race cannot be closed completely with portable Python on macOS and Linux, close it as far as the platform allows AND make the operation detect the conflict afterwards and keep the user's data (keep the displaced content as a recoverable copy, report it, exit non-zero). Losing user data silently is never acceptable.
- For each item: first a test that fails now (red), then the fix (green). Never weaken, skip or delete an existing test. If an existing test pins the unsafe behaviour, change it to pin the safe behaviour and say why in the report.
- Old/new compatibility matters: state written by `v0.12.0` and by `518da76` must still load, recover and undo after upgrading.
- Stay in the files named here plus their tests. Under ~400 changed lines if you can; say so if you must exceed it. Keep `python3 tools/context_budget.py` passing (the budget is nearly full: do not grow hook or skill context text).
- Python 3.9 compatible. Do not commit or push. Do not touch `.claude-plugin/plugin.json`, `CHANGELOG.md` or the version.
- Report: per item FIXED (test name) or PARTIAL (what remains and how it is detected and recovered), files changed, checks run with results.
