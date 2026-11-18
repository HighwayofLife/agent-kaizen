# BF15a batch-review-8 fixes (non-scheduler files)

Risk: normal. Model: sol / medium. Fix-Origin: batch-review. Fixes: P23, BF14.
Sol reason: item 3 is performance work on the contention overlap scan (quadratic in cohorts), and item 2 restores a measurement-validity invariant.
Depends on: BF14 landed (done). Runs in parallel with P24b (P24b owns `scripts/kaizen-scheduled`; do not touch it). Jumps the queue ahead of P24 (P24 edits `scripts/token-audit`).
Changelog: none.

## Goal

Batch review 8 (Sol medium, d394edb..0fefbc1) found eight defects. Five are in files P24b does not own; fix ALL five here, each with a regression test that fails before the fix. The three `scripts/kaizen-scheduled` findings go to BF15b. Do not commit or push. Do not edit `.claude-plugin/plugin.json` or `CHANGELOG.md`; write the changelog fragment `docs/plans/2026-11-17-friction-port/changelog/BF15a.md` containing `none`.

Owned files: `hooks/audit-notice.sh`, `scripts/kaizen_friction_prepare.py`, `scripts/token-audit`, `tests/test_hooks.py`, `tests/test_friction_prepare.py`, `tests/test_friction_timeline.py`, `tests/test_friction_codex.py`, `tests/test_friction_signals.py`, `tools/context-budget.json` (inventory only, if the hook changes).

## Findings

1. `scripts/kaizen_friction_prepare.py:390`: worktree findings are filtered against stored (acknowledged) evidence before the per-candidate merge, so an unchanged weaker finding from one worktree can replace the acknowledged stronger one from another, and the same candidate reopens on alternating runs. Fix: merge across worktrees first (keep the strongest per candidate), then compare the merged result with stored evidence. Test: two worktrees, stronger one acknowledged, weaker unchanged; two consecutive runs both report nothing new.
2. `scripts/token-audit:1769`: an invalid first observation no longer disqualifies its Codex call ID; a later pair for the same ID contributes a measured timing the pre-BF14 scanner rejected. Fix: an ID whose first observation is invalid (whatever the reason, including out-of-scope cwd or a future-dated header) stays disqualified for the rest of the rollout, while BF14's fix (out-of-scope rollouts must not consume pair slots or set the cap) still holds. Test both.
3. `scripts/token-audit:1244`: the overlap bisect skips only the initial interval prefix; cohorts with gaps still rescan intervening intervals (53,456 visits at 100 synthetic cohorts, 573,656 at 400). The existing regression test counts bisect calls and misses this. Fix: make the scan near-linear overall (for example a single sorted sweep, or a bisect for each cohort's own start and end). Results must be identical. Test: count interval visits and assert growth is roughly linear (for example visits at 400 cohorts < 6x visits at 100), plus an equality check of results against a brute-force reference on randomized fixtures with a fixed seed.
4. `hooks/audit-notice.sh:81`: the bounded config reader rejects symlinked configs, which the scheduler explicitly supports, so either config being a symlink suppresses every SessionStart audit notice. Fix: follow the symlink, then require that the target is a regular file within the size bound; FIFOs, devices, directories and oversized targets stay refused. Match the scheduler's symlink rules (read how `scripts/kaizen-scheduled` resolves config, without editing it). Test: a symlinked global config and a symlinked project config each still produce the notice; a symlink to a FIFO still does not hang. If the hook text changes, update the reviewed inventory in `tools/context-budget.json` and keep `python3 tools/context_budget.py` at exit 0.
5. (No code; context.) Keep every BF14 test passing.

## Verification

- `python3 -m unittest discover -s tests -p 'test_hooks.py'`
- `python3 -m unittest discover -s tests -p 'test_friction_prepare.py'`
- `python3 -m unittest discover -s tests -p 'test_friction_timeline.py'`
- `python3 -m unittest discover -s tests -p 'test_friction_codex.py'`
- `python3 -m unittest discover -s tests -p 'test_friction_signals.py'`
- `python3 tools/context_budget.py`
- `python3 tests/bench_token_audit.py --baseline d8a4cb7 --max-ratio 1.10`
- `git diff --check`

Report: root cause and fix per item, files with line counts, check results. Do not delete or weaken tests.
