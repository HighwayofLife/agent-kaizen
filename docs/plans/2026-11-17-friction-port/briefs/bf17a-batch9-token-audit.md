# BF17a Batch-9 review fixes: token-audit

Fix-Origin: batch-review (batch 9). Fixes: BF15a, BF16. Risk: normal. Model: terra / high.

## Goal
Batch review 9 (Sol, range bb32242..3f91471) reported these against `scripts/token-audit`:

1. `scripts/token-audit:1802` (BF16): regression cohorts that include Codex timings are signed into the MAC-bound baseline without safe-opening the Codex rollouts (the Claude transcripts are safe-opened since BF16). An externally writable rollout can skew later proposals through that authenticated baseline. Apply the same safe-open / rejection rule to rollouts that feed regression cohorts and the MAC, consistent with BF16's transcript handling (exclusion only from the regression cohorts and MAC, not from the usage summary).
2. `scripts/token-audit:1273` (BF15a): the overlap scan still intersects every long-running nonlocal cohort with all local overlap intervals before discarding the result. An in-memory check measured 10,100 intersections at 100 cohorts and 160,400 at 400. Make it sub-quadratic in practice (e.g. sorted intervals with a moving start index or bisect), with identical results. Add a test that counts the intersections or bounds the work.
3. `scripts/token-audit:1831` (BF15a): every rejected Codex call ID is stored in an uncapped set, so a large out-of-scope rollout can exhaust memory without hitting the pair limit. Cap or restructure it, with the same rejection semantics, and add a test.

## Rules
- First confirm or refute each finding against the code (and a failing test where practical). Fix the confirmed ones at their cause, test first. List refuted ones in the report with evidence.
- Never weaken, skip or delete an existing test. Do ALL items.
- Do not touch `.claude-plugin/plugin.json`, `CHANGELOG.md` or the version. Write a player-facing-style changelog fragment to `docs/plans/2026-11-17-friction-port/changelog/BF17a.md` only if a user would notice the fix; otherwise none.
- Gated items G1–G10 in plan.md stay out of scope. Do not commit or push.
- Report: per item CONFIRMED+fixed / REFUTED (evidence), files changed, checks run.

## Verify
- `python3 -m unittest discover -s tests -p 'test_friction_signals.py'`
- `python3 -m unittest discover -s tests -p 'test_friction_codex.py'`
- `python3 -m unittest discover -s tests -p 'test_token_audit_fixes.py'`
- `python3 tests/bench_token_audit.py --baseline d8a4cb7 --max-ratio 1.10`
