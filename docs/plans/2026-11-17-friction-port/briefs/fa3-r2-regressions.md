# FA3 r2: regressions from r1 (final round)

Fix-Origin: final-audit. Risk: high. Model: sol / high.
Sol reason: escalation — two earlier rounds on this packet each introduced regressions in race/durability code; this round fixes or reverts them.

## Goal
A Sol review of your r1 commit (HEAD; briefs `fa3-r1-review-fixes.md` and the original `fa3-*.md` in this directory) found these regressions introduced by r1:

1. `scripts/kaizen_friction_apply.py:419` — Recovery clears the backup-directory binding before saving the final phase — I reproduced a retry that marked the effect recorded while its backup path pointed to a decoy in a replacement directory.
1. `scripts/kaizen_friction_actions.py:456` — Closing legacy pending receipts can still exceed the 1 MiB cap — in memory, a valid 1,048,472-byte store needed 1,059,798 bytes after closure, so recovery could not clear the pending work.
1. `scripts/kaizen_friction_apply.py:446` — Migration aborts on readable legacy backups in a read-only directory — reconciliation and undo now fail even when the preferred backup location is writable.
1. `scripts/kaizen_friction_apply.py:393` — The local fallback also runs inside Git checkouts when both private locations are on other devices — it leaves untracked copies that block later scheduled mutations even after the ledger edit is committed.

## Rules
- For each item: fix it narrowly, OR revert the r1 hunk that caused it and mark the original r1/audit item it addressed as DEFERRED (it goes to the 0.14 known-issues list). Prefer the revert when the fix is not small and obviously safe. Behaviour must be no worse than at the FA commit before r1 for every supported setup.
- No new features or hardening beyond these items. Under ~150 changed lines. Stay in the files r1 touched.
- Add a regression test for each fixed item where practical; never weaken, skip or delete an existing test.
- Do not commit or push. Do not touch plugin.json, CHANGELOG.md or the version.
- Report: per item FIXED / REVERTED (+ which original item is now DEFERRED) / REFUTED (evidence), files changed, checks run.
