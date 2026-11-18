# BF13b batch-review-6 fixes: friction prepare

Risk: normal. Model: terra / medium. Fix-Origin: batch-review. Fixes: P20.
Starts after P20b lands (P20b owns the same file). Changelog: none (record `docs/plans/2026-11-17-friction-port/changelog/BF13b.md` only if a fix is user-visible).

## Goal

A Sol review of P20 found eight defects in `scripts/kaizen_friction_prepare.py`. P20b has since extended that file; apply the fixes on top of its current code. Do not commit or push. Do not edit `.claude-plugin/plugin.json` or `CHANGELOG.md`. Do not delete or weaken existing tests. Fix ALL items, each with a regression test that fails before the fix; if one cannot be fixed, say exactly which and why. Never report a partial packet as complete.

Owned files: `scripts/kaizen_friction_prepare.py`, `scripts/kaizen-scheduled` (only if a fix needs the runner), `tests/test_friction_prepare.py`.

## Findings (line numbers are from P20 and may have moved)

1. ~225: automatic selection keeps every parsed candidate extract, so hundreds of near-limit extracts can exhaust memory before one is chosen. Fix: select by metadata (name, mtime, size) first, parse only the chosen candidate (plus at most a small fixed number of fallbacks), and cap the candidate count. Test: memory or parse count stays bounded with many candidates.
2. ~177: the report and extract are matched by metadata without binding their contents, so replacing an extract while keeping its metadata can put forged flags into the redacted view and private receipt. Fix: bind by content digest. The report must name its extract's sha256 (or the receipt must record and recheck it), read the extract once by fd, and hash those same bytes. Refuse on mismatch. Test: a swapped extract with identical metadata is refused.
3. ~285: preparation rejects indexed-output findings from linked worktrees when canonicalization changes their paths, so one valid probe finding aborts the whole preparation. Fix: compare canonical forms on both sides. An unmatched finding is dropped with a warning and never aborts the run. Test with a linked-worktree finding.
4. ~76: duplicate flag identities abort preparation even when `token-audit` legitimately emits the same regression signature for measured and row-gap timings. Fix: key identity on (signature, basis) or merge duplicates keeping the strongest basis; never abort on this. Test a mixed-basis audit.
5. ~231: an extract without a friction block exits before checking the probe, so actionable host findings disappear when the audit has no transcript friction evidence. Fix: still process probe findings when the extract has no friction block. Test it.
6. ~233: `hostActions=off` still requires a recent probe, so missing host evidence blocks otherwise valid audit flags. Fix: with `hostActions=off`, skip the probe requirement entirely and prepare audit flags only. Test it.
7. ~115: `os.fdopen` can raise before taking ownership of a directory descriptor; 20 rejected directory reads leaked 20 descriptors. Fix: fstat the fd for `S_ISREG` before `fdopen` and close it in `finally` on every rejection path. Test: the `/dev/fd` count is unchanged after many rejected directory entries.
8. ~303: the gate ignores the flap limit, so actions that need manual resolution can trigger review again and again when their evidence changes. Fix: apply the configured flap limit from the plan's action rules (read `docs/plans/2026-11-17-friction-port/plan.md` for the flap definition) so a flapping action is held for manual resolution. Test it.

## Verification

- `python3 -m unittest discover -s tests -p 'test_friction_prepare.py'`, `'test_runner.py'`, `'test_host_actions.py'`
- `git diff --check`

## Report

Each finding: fixed or not, and its test name. Files changed with line counts. Check results.

## Delta (after P20b landed, 0f9a3d8)

P20b changed `scripts/kaizen_friction_prepare.py` (+125 lines: signed receipts, live re-derivation, import/acknowledge). The line numbers above are stale: re-locate each finding in the current code. If P20b already fixed one, say so in the report with the test that covers it; otherwise fix it. Do ALL eight items. Keep P20b's tests passing.
