# FA2 r2: regressions from r1 (final round)

Fix-Origin: final-audit. Risk: high. Model: sol / high.
Sol reason: escalation — two earlier rounds on this packet each introduced regressions in race/durability code; this round fixes or reverts them.

## Goal
A Sol review of your r1 commit (HEAD; briefs `fa2-r1-review-fixes.md` and the original `fa2-*.md` in this directory) found these regressions introduced by r1:

1. `scripts/token-audit:449` — A Claude denial with an invalid outer timestamp and a recent nested timestamp is dropped before replay reconciliation — a conflicting acceptance that the base marked ambiguous can now be signed.
1. `scripts/token-audit:297` — The Codex canary fully decodes oversized output records when the envelope timestamp comes last or a closing brace is missing — a 4 MB record raised peak parser allocations from about 12 KB to 8 MB.
1. `scripts/token-audit:2995` — Reports are now written as UTF-8, but the comparison reader still uses the locale encoding — on CP1252, a report containing `Á` silently disappears from baseline comparisons.

## Rules
- For each item: fix it narrowly, OR revert the r1 hunk that caused it and mark the original r1/audit item it addressed as DEFERRED (it goes to the 0.14 known-issues list). Prefer the revert when the fix is not small and obviously safe. Behaviour must be no worse than at the FA commit before r1 for every supported setup.
- No new features or hardening beyond these items. Under ~150 changed lines. Stay in the files r1 touched.
- Add a regression test for each fixed item where practical; never weaken, skip or delete an existing test.
- Do not commit or push. Do not touch plugin.json, CHANGELOG.md or the version.
- Report: per item FIXED / REVERTED (+ which original item is now DEFERRED) / REFUTED (evidence), files changed, checks run.
