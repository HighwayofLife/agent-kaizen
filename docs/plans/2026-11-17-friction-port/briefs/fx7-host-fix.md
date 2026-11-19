# FX7: host-fix undo races (P19 residuals)

Risk: high. Model: sol / high.
Sol reason: same-UID filesystem races in undo/rollback of host fixes (security-sensitive).

Host-fix live writes stay disabled in 0.13.0 (S3) — do not enable them — but the undo and rollback code must be correct before they ever are.

## Items
1. `scripts/host-fix` undo and rollback unlink the quarantine entry by name after the final identity check; a concurrent sync or restore that replaces that entry loses its file. Unlink only the entry you verified (rename it to a unique private name inside the pinned dir FD first, re-verify identity, then unlink; if identity changed, put it back and report).
2. Undo persists `retire-pending` after the last scope check, then renames through the pinned directory FD; a directory moved outside the eligible tree during that write is still mutated. Re-check scope after persisting and before the rename, and abort to a recoverable state if it changed.
3. Identity recovery for a moved directory walks unrelated mounts with blocking filesystem calls; an unavailable network mount can hang undo past the 20-second deadline. Stay on the original device (`st_dev`), never cross mount points, and enforce the deadline (time checks between calls; skip network/autofs mounts).

## Checks
python3 -m unittest discover -s tests -p 'test_host_fix.py'; test_host_actions.py; test_host_acceptance.py.

## Rules
- Base: branch `release-0.13` (candidate 0.13.0). `518da76` is the 0.12-era base the friction work started from; `v0.12.0` is the last release. Background for each item: `docs/plans/2026-11-17-friction-port/plan.md` section "0.14 known issues" and `gate-results.md`.
- This is the **fix round for the release**: fix every item properly. Do not defer, do not revert a feature away, and do not report an item as accepted. If a race cannot be closed completely with portable Python on macOS and Linux, close it as far as the platform allows AND make the operation detect the conflict afterwards and keep the user's data (keep the displaced content as a recoverable copy, report it, exit non-zero). Losing user data silently is never acceptable.
- For each item: first a test that fails now (red), then the fix (green). Never weaken, skip or delete an existing test. If an existing test pins the unsafe behaviour, change it to pin the safe behaviour and say why in the report.
- Old/new compatibility matters: state written by `v0.12.0` and by `518da76` must still load, recover and undo after upgrading.
- Stay in the files named here plus their tests. Under ~400 changed lines if you can; say so if you must exceed it. Keep `python3 tools/context_budget.py` passing (the budget is nearly full: do not grow hook or skill context text).
- Python 3.9 compatible. Do not commit or push. Do not touch `.claude-plugin/plugin.json`, `CHANGELOG.md` or the version.
- Report: per item FIXED (test name) or PARTIAL (what remains and how it is detected and recovered), files changed, checks run with results.
