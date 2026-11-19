# FA4 r2: regressions from r1 (final round)

Fix-Origin: final-audit. Risk: high. Model: sol / high.
Sol reason: escalation — two earlier rounds on this packet each introduced regressions in race/durability code; this round fixes or reverts them.

## Goal
A Sol review of your r1 commit (HEAD; briefs `fa4-r1-review-fixes.md` and the original `fa4-*.md` in this directory) found these regressions introduced by r1:

1. `scripts/kaizen_friction_prepare.py:617` — Cutoff validation runs before broker recovery — a malformed cutoff now strands pending host actions until the marker is repaired.
1. `scripts/kaizen_friction_prepare.py:625` — Recovery now reads a superseded proposal before clearing its marker — an owner edit that grows the report beyond 1 MiB leaves the marker in place, downgrades later reviews to propose-only, and makes the scheduler exit nonzero.

## Rules
- For each item: fix it narrowly, OR revert the r1 hunk that caused it and mark the original r1/audit item it addressed as DEFERRED (it goes to the 0.14 known-issues list). Prefer the revert when the fix is not small and obviously safe. Behaviour must be no worse than at the FA commit before r1 for every supported setup.
- No new features or hardening beyond these items. Under ~150 changed lines. Stay in the files r1 touched.
- Add a regression test for each fixed item where practical; never weaken, skip or delete an existing test.
- Do not commit or push. Do not touch plugin.json, CHANGELOG.md or the version.
- Report: per item FIXED / REVERTED (+ which original item is now DEFERRED) / REFUTED (evidence), files changed, checks run.
