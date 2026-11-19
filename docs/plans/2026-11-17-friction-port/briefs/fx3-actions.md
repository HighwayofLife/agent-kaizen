# FX3: friction action store and apply finalization

Risk: high. Model: sol / high.
Sol reason: persisted store format and cross-version compatibility, plus a directory-replacement race in finalization.

## Items
1. `scripts/kaizen_friction_apply.py:434` — finalization drops the directory binding before publishing the receipt; a directory replacement during the save can leave a recorded receipt pointing to a decoy. Keep the pinned directory FD through receipt publication and verify identity after.
2. `scripts/kaizen_friction_actions.py:431` — compacting a receipt can still leave the save over the cap: closing one verified action grew a valid 1,048,576-byte store to 1,048,580 bytes, leaving recovery pending. Compaction must never grow the store; closing an action at the cap must succeed.
3. `scripts/kaizen_friction_actions.py:523` — at the 1 MiB cap the writer moves live scheduled receipts into a `.receipts` sidecar that older runners (`v0.12.0` / `518da76`) cannot read; closing another project's receipt can block acknowledgement of an already-published review and let the old runner accept changed requests for the same generation. Fix so live scheduled receipts stay where old runners read them (evict closed/superseded data first), or make old runners fail closed rather than accept changed requests; prove it with a test that runs the old store-reading code (`git show 518da76:scripts/kaizen_friction_actions.py` into a temp module) against the new store.

## Checks
python3 -m unittest discover -s tests -p 'test_friction_apply.py'; test_host_actions.py; test_friction_prepare.py.

## Rules
- Base: branch `release-0.13` (candidate 0.13.0). `518da76` is the 0.12-era base the friction work started from; `v0.12.0` is the last release. Background for each item: `docs/plans/2026-11-17-friction-port/plan.md` section "0.14 known issues" and `gate-results.md`.
- This is the **fix round for the release**: fix every item properly. Do not defer, do not revert a feature away, and do not report an item as accepted. If a race cannot be closed completely with portable Python on macOS and Linux, close it as far as the platform allows AND make the operation detect the conflict afterwards and keep the user's data (keep the displaced content as a recoverable copy, report it, exit non-zero). Losing user data silently is never acceptable.
- For each item: first a test that fails now (red), then the fix (green). Never weaken, skip or delete an existing test. If an existing test pins the unsafe behaviour, change it to pin the safe behaviour and say why in the report.
- Old/new compatibility matters: state written by `v0.12.0` and by `518da76` must still load, recover and undo after upgrading.
- Stay in the files named here plus their tests. Under ~400 changed lines if you can; say so if you must exceed it. Keep `python3 tools/context_budget.py` passing (the budget is nearly full: do not grow hook or skill context text).
- Python 3.9 compatible. Do not commit or push. Do not touch `.claude-plugin/plugin.json`, `CHANGELOG.md` or the version.
- Report: per item FIXED (test name) or PARTIAL (what remains and how it is detected and recovered), files changed, checks run with results.
