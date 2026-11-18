# BF12 batch-review-5 fixes (BF11, P22, P17)

Risk: normal. Model: terra / medium. Fix-Origin: batch-review. Fixes: BF11, P22, P17.
Changelog: none (record `docs/plans/2026-11-17-friction-port/changelog/BF12.md` only if a fix is user-visible; otherwise do not create it).

## Goal

A Sol review of the landed range `1ae2479..11d4ae8` found six defects. Fix ALL six, each with a regression test that fails before the fix. Do not commit or push. Do not edit `.claude-plugin/plugin.json` or `CHANGELOG.md`. Do not delete or weaken existing tests.

Owned files: `scripts/token-audit`, `hooks/audit-notice.sh`, `tests/test_friction_samples.py`, `tests/test_friction_timeline.py`, `tests/test_hooks.py`, `tests/test_usage.py`, `tools/context-budget.json` (only if the notice text length changes; it must stay at or under 1,024 bytes).

## Findings

1. `scripts/token-audit` ~line 1177: contention confirmation checks only the reported signature's calls and samples over their full durations. A Codex call can supply the only overlap, and Claude load sampled before that overlap can still yield a confirmed flag. Fix: confirm only when compatible local-load samples fall inside the actual overlap interval of the calls being flagged, with the host of the overlapping calls matching the sample's host. Test: a Codex-only overlap plus a Claude sample before the overlap leads to unconfirmed.
2. `hooks/audit-notice.sh` ~line 186: opt-outs are read from the checkout before actions resolve to the canonical project. A linked worktree can show the canonical project's action count even when that project disabled notices. Fix: resolve to the canonical project first, then apply that project's opt-out (and the checkout's own, if set). Test in `tests/test_hooks.py` with a linked worktree whose canonical project has opted out, so no count is emitted.
3. `scripts/token-audit` ~line 1008: skipping a daily sample file over the byte limit leaves join candidates read earlier valid. Near UTC midnight, a conflicting record in the skipped day can leave a retained record wrongly classified as measured. Fix: when an adjacent day in the join window is skipped (too large or rejected), records whose window touches that day degrade to estimated/unconfirmed, never measured. Test near midnight.
4. `scripts/token-audit` ~line 1694: CWD hashing happens after the raw path and its canonical form enter the unbounded `realpaths` cache, so rollouts with many large, distinct CWDs can exhaust memory. Fix: bound the cache (entry count and per-key length; over-long paths are hashed before caching or are not cached). Test: many distinct long CWDs keep the cache within its bound.
5. `hooks/audit-notice.sh` ~line 211: the suggested command assumes `kaizen-scheduled` is on PATH, and the CLI ignores the hook's `AUDIT_DIR` override. Following the notice can fail or open a different action store. Fix: point the suggestion at the resolved installed path the hook already knows (or the plugin-relative script), and pass the store location the hook actually used when `AUDIT_DIR` is overridden. Keep the notice within budget. Test the emitted command text under an `AUDIT_DIR` override.
6. `scripts/token-audit` ~line 1004: wrapping a directory named like a daily TSV raises before the descriptor is closed, so rejected entries leak file descriptors. Fix: fstat-check `S_ISREG` on the opened fd and close it on every rejection path (try/finally). Test: a directory named `YYYY-MM-DD.tsv` is skipped, and the open-fd count does not grow (use `os.listdir('/dev/fd')` before and after).

Use `python3 -I` style imports where tests already do. Keep the existing safe-open pattern (dir-fd walk, `O_NOFOLLOW`, owner and mode checks).

## Verification

- `python3 -m unittest discover -s tests -p 'test_friction_samples.py'`
- `python3 -m unittest discover -s tests -p 'test_friction_timeline.py'`
- `python3 -m unittest discover -s tests -p 'test_hooks.py'`
- `python3 -m unittest discover -s tests -p 'test_usage.py'`
- `python3 tests/bench_token_audit.py --baseline d8a4cb7 --max-ratio 1.10`, also with `--no-friction`
- `git diff --check`; `tools/ci-local --python 3.9` (report any sandbox-only failures from `ps` or lock writes)

## Report

Files changed with line counts; each finding with fixed or not, and its test name; check results.
