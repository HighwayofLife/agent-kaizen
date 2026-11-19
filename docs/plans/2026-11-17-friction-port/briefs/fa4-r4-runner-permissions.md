# FA4 r4: runner permission rules broke

Fix-Origin: final-audit. Risk: high. Model: sol / high.
Sol reason: the regression is in the scheduled runner's permission-boundary rules (security-sensitive), introduced by this packet's earlier rounds.

## Goal
This branch's FA4 commits (everything after `518da76`; earlier briefs `fa4-*.md` in this directory) make two tests in `tests/test_runner.py` fail. They pass at `518da76`:

- `test_runner.ExecutionTests.test_modes_and_permission_boundaries` (subtest mode='auto', number=1)
- `test_runner.ExecutionTests.test_permission_auto_dry_run_has_same_deny_rules`

The assertion shows the generated permission list now has an `Edit(//<repo path>...)` rule where the expected list has a `Read(//<temp dir>...)` rule. Find which FA4 hunk changed the runner's permission or allow/deny rule generation, and restore the `518da76` rules for these modes. Do this by a narrow fix, or by reverting that hunk; if reverting undoes an FA4 audit item, name the item as deferred. Never widen the permissions a scheduled run gets.

## Rules
- The two tests are the spec. Do not edit `tests/test_runner.py` or any other existing test.
- Keep the FA4 fixes that do not touch permission rules. Under ~100 changed lines. Stay in files FA4 already changed.
- Do not commit or push. Do not touch plugin.json, CHANGELOG.md or the version.
- Report: the cause (file:line and hunk), FIXED or REVERTED (plus any deferred item), files changed, checks run.
