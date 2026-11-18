# BF13a batch-review-6 fixes: token-audit, notice, installer

Risk: normal. Model: terra / medium. Fix-Origin: batch-review. Fixes: BF12, P21, P20.
Changelog: none (record `docs/plans/2026-11-17-friction-port/changelog/BF13a.md` only if a fix is user-visible).

## Goal

A Sol review of the landed range `4b9d8d3..73832b6` found 13 defects. This packet fixes the five outside `scripts/kaizen_friction_prepare.py` (BF13b handles those, after P20b). Do not commit or push. Do not edit `.claude-plugin/plugin.json` or `CHANGELOG.md`. Do not delete or weaken existing tests. Fix ALL items, each with a regression test that fails before the fix; if one cannot be fixed, say exactly which and why. Never report a partial packet as complete.

Owned files: `scripts/token-audit`, `hooks/audit-notice.sh`, `scripts/install-schedule`, `tests/test_friction_samples.py`, `tests/test_friction_timeline.py`, `tests/test_usage.py`, `tests/test_hooks.py`, `tests/test_schedule.py`, `tests/test_install_schedule.py`, `tools/context-budget.json` (only if the notice text changes; stay at or under 1,024 bytes).

## Findings

1. `scripts/token-audit` ~1205: contention expands each call into every intersecting overlap segment. 400 staggered calls used about 12 MB, and growth is quadratic up to the 16,384-call cap. Fix: compute overlap with a sweep-line over sorted start/end events (O(n log n)), keeping only what confirmation needs (per call: overlapping interval bounds and the overlapping host set), or cap segments per call with an explicit "capped" degrade to unconfirmed. Keep current confirmation semantics (BF12 item 1: samples must fall inside the actual overlap, from the matching host). Test: a 2,000-staggered-call fixture keeps `tracemalloc` peak under a stated bound (for example 4 MB), and existing contention tests still pass.
2. `scripts/token-audit` ~1752: the turn map still keeps raw CWDs from up to 16,384 turns, so large distinct paths can exhaust memory despite the bounded realpath cache. Fix: store the bounded or hashed CWD form (the same one BF12 used for the cache) in the turn map, never the raw string over the length bound. Test: many distinct long CWDs keep turn-map memory bounded.
3. `hooks/audit-notice.sh` ~203: the canonical config read follows symlinks and has no size limit or timeout, so a FIFO can hang SessionStart and a large file can exhaust memory. Fix: read only a regular file (no symlink follow, not a FIFO or device), capped at a small size (for example 64 KiB), and treat anything else as absent. Test with a FIFO (the hook returns promptly) and with an oversized file.
4. `hooks/audit-notice.sh` ~187: a global opt-out is applied before the canonical project override is read, so a linked checkout without its own setting suppresses notices the canonical project enabled. Fix: precedence is checkout setting, then canonical project setting, then global, with the first explicit value winning. Keep BF12's rule that a canonical opt-out suppresses a linked checkout's count. Test both directions.
5. `scripts/install-schedule` ~50: the copied install leaves out `kaizen_friction_sample.py`, so installed `token-audit` silently runs without local samples. Fix: add it to `MANAGED_NAMES` (identity name), and extend the copied-install test in `tests/test_schedule.py` to assert the installed `token-audit` imports the sampler beside it.

## Verification

- `python3 -m unittest discover -s tests -p 'test_friction_samples.py'`, `'test_friction_timeline.py'`, `'test_usage.py'`, `'test_hooks.py'`, `'test_schedule.py'`, `'test_install_schedule.py'`, `'test_context_budget.py'`
- `python3 tests/bench_token_audit.py --baseline d8a4cb7 --max-ratio 1.10`, also with `--no-friction`
- `git diff --check`

## Report

Each finding: fixed or not, and its test name. Files changed with line counts. Check results.
