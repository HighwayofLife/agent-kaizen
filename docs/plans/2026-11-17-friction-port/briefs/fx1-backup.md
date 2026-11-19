# FX1: kaizen-backup undo and journal safety

Risk: high. Model: sol / high.
Sol reason: concurrency (editor-save race during undo) and journal-identity recovery in backup/undo code.

## Items
1. `scripts/kaizen-backup:2297` — ordinary `undo run` still overwrites an in-place editor save made after the snapshot check and before `copy2` opens the destination; the final hash and inode checks pass, so undo exits successfully after losing the save. Fix: restore through a temp file in the same directory plus an atomic rename, re-checking the destination immediately before the rename, and detect a save that lands in the window (keep it as a recoverable copy, report, non-zero exit).
2. `scripts/kaizen-backup:1099` — reusing a renamed transaction's original folder name makes its corrupt journal look unrelated; undo can restore files without reversing the Git ref, and prune can delete the rollback copies. Fix: bind journals to a transaction identity that survives renames (not the folder name) so a corrupt or foreign journal blocks undo and prune instead of being ignored.

## Checks
python3 -m unittest discover -s tests -p 'test_kaizen_backup.py'; python3 -m unittest discover -s tests -p 'test_backup_commit.py' (slow, ~15 min).

## Rules
- Base: branch `release-0.13` (candidate 0.13.0). `518da76` is the 0.12-era base the friction work started from; `v0.12.0` is the last release. Background for each item: `docs/plans/2026-11-17-friction-port/plan.md` section "0.14 known issues" and `gate-results.md`.
- This is the **fix round for the release**: fix every item properly. Do not defer, do not revert a feature away, and do not report an item as accepted. If a race cannot be closed completely with portable Python on macOS and Linux, close it as far as the platform allows AND make the operation detect the conflict afterwards and keep the user's data (keep the displaced content as a recoverable copy, report it, exit non-zero). Losing user data silently is never acceptable.
- For each item: first a test that fails now (red), then the fix (green). Never weaken, skip or delete an existing test. If an existing test pins the unsafe behaviour, change it to pin the safe behaviour and say why in the report.
- Old/new compatibility matters: state written by `v0.12.0` and by `518da76` must still load, recover and undo after upgrading.
- Stay in the files named here plus their tests. Under ~400 changed lines if you can; say so if you must exceed it. Keep `python3 tools/context_budget.py` passing (the budget is nearly full: do not grow hook or skill context text).
- Python 3.9 compatible. Do not commit or push. Do not touch `.claude-plugin/plugin.json`, `CHANGELOG.md` or the version.
- Report: per item FIXED (test name) or PARTIAL (what remains and how it is detected and recovered), files changed, checks run with results.
