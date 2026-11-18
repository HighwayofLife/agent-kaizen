# BF16 P24 review residuals (two Medium findings)

- **Risk** — normal. Lands on green checks and is reviewed with the next batch.
- **Fix-Origin** — batch-review (P24 final Sol high review, 2026-11-18). Fixes: P24.
- **Changelog** — none (internal hardening of unreleased code).
- **Depends on** — P25 landed (both touch `scripts/kaizen-scheduled`).

## Goal

Fix two Medium findings left by P24's final security review. Both are live in a proposal-only 0.13.0. Fix both, and give each a regression test that fails before the fix.

1. **`scripts/token-audit`, around the signed regression baseline (≈ line 2814 at 755874b).** The audit signs timing comparisons built partly from transcripts that its safe-open check rejected. Externally writable transcript data can then become an authenticated baseline and skew later regression proposals. Fix: comparisons only include rows from transcripts that passed the safe-open check. If any input to the comparison cohorts was rejected, the audit writes no regression MAC; an unsigned report is already skipped as a baseline. Test: a rejected transcript is present, so no `token-audit-friction-mac` line is written and the next run uses no baseline from it.
2. **`scripts/kaizen-scheduled`, interrupted-run recovery (≈ line 2406 at 755874b).** In a degraded proposal-only review, an error while recovering an interrupted run skips the cleanup of recordless legacy receipts. That unrelated error leaves those suggestions pending and blocks manual dismissal or completion. Fix: make the recordless legacy receipt cleanup independent of interrupted-run recovery. It needs no native effect and runs under proposal-review checks even when recovery fails. The recovery error itself still surfaces and still fails closed for native effects. Test: interrupted-run recovery raises, and a recordless legacy `linux-localsearch` receipt still becomes a terminal suggestion with no marker written.

## Scope

Owned files: `scripts/token-audit`, `scripts/kaizen-scheduled`, `tests/test_friction_timeline.py`, `tests/test_friction_review.py`, `tests/test_friction_prepare.py`. Do not touch the gated items recorded as G1–G8 in `plan.md`. Do not weaken or delete tests. Do not commit or push. Do not edit `.claude-plugin/plugin.json` or `CHANGELOG.md`. No changelog fragment is needed.

## Verification

- `python3 -m unittest discover -s tests -p 'test_friction_timeline.py'`
- `python3 -m unittest discover -s tests -p 'test_friction_review.py'`
- `python3 -m unittest discover -s tests -p 'test_friction_prepare.py'`
- `python3 -m unittest discover -s tests -p 'test_token_audit_fixes.py'`
- `git diff --check`
