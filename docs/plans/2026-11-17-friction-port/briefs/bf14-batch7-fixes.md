# BF14 batch-review-7 fixes

Risk: normal. Model: terra / medium. Fix-Origin: batch-review. Fixes: BF13a, P20b, BF13b.
Depends on: P23 and P18d landed (both done) (they own `scripts/kaizen_friction_prepare.py` and `scripts/token-audit` while in flight). Jumps the queue ahead of P24.
Changelog: none.

## Goal

Batch review 7 (Sol medium, 634c943..253dd03) found six defects, and item 7 is a pre-existing check failure. Fix ALL nine, each with a regression test that fails before the fix. Do not commit or push. Do not edit `.claude-plugin/plugin.json` or `CHANGELOG.md`. Do not delete or weaken tests. The line numbers are from 253dd03; P23 and P18d have since changed these files, so re-locate each finding in the current code and report any already fixed.

Owned files: `hooks/audit-notice.sh`, `scripts/kaizen_friction_prepare.py`, `scripts/token-audit`, `tests/test_hooks.py`, `tests/test_friction_prepare.py`, `tests/test_friction_timeline.py`, `tools/context-budget.json`, `tests/test_friction_codex.py`, `tests/test_friction_signals.py`.

## Findings

1. `hooks/audit-notice.sh:65`: early `jq` reads of the global and active-checkout config bypass BF13a's bounded config reader, so a FIFO there can hang SessionStart and an oversized file can exhaust memory. Fix: route every config read through the bounded reader (regular file only, no FIFO, size cap). Test: a FIFO and an oversized file at each config path; the hook exits promptly with no notice and no hang (use a timeout in the test).
2. `scripts/kaizen_friction_prepare.py:374`: valid findings from two worktrees can collide after canonicalization; identical output paths for the same catalog action abort the whole preparation, including unrelated audit flags. Fix: merge identical (catalog action, canonical path) findings into one candidate (summing or keeping the stronger evidence, recording both sources) instead of aborting. Test: two worktrees with the same output path produce one candidate and the unrelated flags survive.
3. `scripts/kaizen_friction_prepare.py:333`: linked-worktree findings need the output path to exist in the main checkout because the selector resolver uses strict resolution, so an output directory built only in the linked worktree is dropped after a warning. Fix: canonicalize the path relative to the linked worktree's own top level (still refusing escapes and symlinks out of the tree), and require existence only there. Test.
4. `scripts/kaizen_friction_prepare.py:285`: reconciliation reads policy and time before taking the generation lock, so a queued import or acknowledgement can proceed after friction is disabled or its receipt expires. Fix: re-read the policy and `now` after acquiring the lock and re-check enablement and receipt expiry under it. Test: disable friction (or expire the receipt) while a second call waits on the lock; it refuses.
5. `scripts/kaizen_friction_prepare.py:75`: measured and estimated regressions share one acknowledgement bucket, so acknowledging a larger row-gap estimate suppresses a newly measured regression for the same command. Fix: key acknowledgements by basis (`measured`, `estimated`, `unconfirmed`) as well as identity; a measured regression is never suppressed by an estimated acknowledgement. Test.
6. `scripts/token-audit:1214`: the contention overlap scan restarts from the first local interval for every cohort (a 16,383-call, 5,461-cohort benchmark took 19.2 s versus 7.3 s before BF13a). Fix: sort intervals once and advance a moving start pointer (or bisect) per cohort while keeping BF13a's memory bound. Add a test that the scan does linear-ish work (for example, count interval visits on a synthetic input) and keep `tests/bench_token_audit.py` within budget.

7. `tools/context_budget.py` fails on `release-0.13` with "hooks/audit-notice.sh: hook changed; review and update inventory": BF13a changed the hook without updating the reviewed inventory in `tools/context-budget.json`. After fix 1, review the hook's literal output bytes and update the inventory entry (hash and reviewed byte count) the way the file's other entries are recorded. The total must stay within the 1024-byte budget (it was 1023); if fix 1 adds printed bytes, trim them rather than raising the budget. Check: `python3 tools/context_budget.py` exits 0.

8. `scripts/token-audit:2598` (live, regression from P18d): the legacy extract-store mode repair applies to arbitrary `--extract-out` destinations and follows symlinked ancestors, so an audit can strip group/other access from an unrelated user-owned directory. Fix: repair the mode only for the default extract store directory the tool itself creates, reached by a dir-fd walk with `O_NOFOLLOW|O_DIRECTORY` from a trusted root, and only when owned by euid; for a custom `--extract-out`, never chmod: warn and skip writing extracts if the mode is not 0700. Tests: a custom 0755 `--extract-out` keeps its mode; a symlinked ancestor is not followed; the default legacy store is still repaired.
9. `scripts/token-audit:1766` (live): Codex rollouts with a future-dated header allocate tool-pair slots before checking cwd scope, so an out-of-scope rollout can mark the audit capped and suppress valid allow-rule proposals. Fix: count a pair toward the cap only after its cwd scope is established and in scope. Test in `tests/test_friction_codex.py`.

## Verification

- `python3 -m unittest discover -s tests -p 'test_hooks.py'`
- `python3 -m unittest discover -s tests -p 'test_friction_prepare.py'`
- `python3 -m unittest discover -s tests -p 'test_friction_timeline.py'`
- `python3 -m unittest discover -s tests -p 'test_runner.py'`
- `python3 tests/bench_token_audit.py --baseline d8a4cb7 --max-ratio 1.10` and with `--no-friction`
- `python3 tools/context_budget.py`
- `python3 -m unittest discover -s tests -p 'test_friction_codex.py'`
- `python3 -m unittest discover -s tests -p 'test_friction_signals.py'`
- `git diff --check`

## Report

Each finding: fixed or not, and its test name. Files changed with line counts. Check results.
