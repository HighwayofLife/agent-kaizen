# BF15b batch-review-8 fixes (scheduler)

Risk: normal. Model: terra / high. Fix-Origin: batch-review. Fixes: P23.
Depends on: P24b landed (P24b owns `scripts/kaizen-scheduled` while in flight). Jumps the queue ahead of P24.
Changelog: none.

## Goal

Batch review 8 (Sol medium, d394edb..0fefbc1) found three defects in P23's scheduled review wiring plus missing P23 test coverage. Fix ALL four, each with a regression test that fails before the fix. Line numbers are at 0fefbc1; P24b will have moved them, so find the code by function. Do not commit or push. Do not edit `.claude-plugin/plugin.json` or `CHANGELOG.md`; write the changelog fragment `docs/plans/2026-11-17-friction-port/changelog/BF15b.md`. Its content is `none` unless item 1 changes what a user sees (then one `fixed:` sentence).

Owned files: `scripts/kaizen-scheduled`, `scripts/kaizen_friction_prepare.py` (only if item 2 needs a shared recheck helper there), `tests/test_friction_review.py`, `tests/test_schedule.py`.

## Findings

1. `scripts/kaizen-scheduled:2202`: scheduled reviews never refresh the required host probe. With the default `hostActions=apply`, friction inputs are skipped on fresh installs and whenever the last probe is over an hour old, even when the scoped audit found new friction. Fix: refresh the probe in the scheduled run before deciding, using the same probe the interactive path uses. If the refresh fails, keep the current safe skip and log the reason. Test: fresh install and a stale probe both include friction inputs after a successful refresh; a failed refresh still skips.
2. `scripts/kaizen-scheduled:2555`: reconciliation imports against the frozen map without rechecking live policy, receipt age or current generation first, so a review can write suggestions or pending apply intents after friction is disabled or its evidence expires. Fix: recheck all three under the generation lock immediately before import (reuse BF14's lock-time recheck in `kaizen_friction_prepare.py`), and refuse without writing on any mismatch. Test: each of the three conditions changing between freeze and import writes nothing.
3. `scripts/kaizen-scheduled:2309`: friction is acknowledged before the proposal is published, so a rename failure or termination between the two writes makes the failed review suppress that evidence on the next run. Fix: publish first, then acknowledge, and make a crash between them recover by re-acknowledging an already-published proposal on the next run, without duplicating it. Test: an injected publish failure leaves the evidence unacknowledged; a simulated crash after publish recovers without a duplicate.
4. `tests/test_friction_review.py:42`: the audit-policy test checks only the argv helper with inherited global settings. Add P23's required coverage (read `docs/plans/2026-11-17-friction-port/briefs/23-*.md`): `auto-audit`, the heavy threshold, and a project override of the global setting, each through the scheduled path.

## Verification

- `python3 -m unittest discover -s tests -p 'test_friction_review.py'`
- `python3 -m unittest discover -s tests -p 'test_schedule.py'`
- `python3 -m unittest discover -s tests -p 'test_schedule_security.py'`
- `python3 -m unittest discover -s tests -p 'test_friction_apply.py'`
- `git diff --check`

Report: root cause and fix per item, files with line counts, check results. Do not delete or weaken tests.
