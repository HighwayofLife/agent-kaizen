# FA2 r1: pre-merge review fixes

Fix-Origin: final-audit (Sol high pre-merge review of FA2 commit e8b527f). Risk: high. This is the ONLY fix round for this packet.

## Goal
The original brief is `fa2-token-audit.md` (same directory); its rules still apply. A Sol review of your FA2 commit reported:

1. `scripts/token-audit:438` — A nested timestamp can cause a timestamp-less Claude denial to be discarded before replay reconciliation — reproduced an acceptance that remains eligible for signing despite the conflicting denial.
1. `scripts/token-audit:355` — `--no-friction` still opens Claude and Codex transcripts in blocking mode — a `.jsonl` FIFO can still hang the audit.
1. `scripts/token-audit:2981` — The Markdown write uses the locale encoding — on Windows with CP1252, the default report’s `≥` raises an encoding error after the extract check succeeds in degrading gracefully.
1. `scripts/token-audit:292` — The canary counts a numeric-ending Codex output with a missing envelope brace — a truncated record is reported as valid coverage.
1. `scripts/token-audit:372` — The new timestamp scan adds work even when the timestamp leads the record — the packet’s tool-heavy fixture was 20% slower than the merge base in memory. The full benchmark fixture stayed within budget.
1. `scripts/token-audit:1893` — An unreadable or nonregular Codex rollout increments the unscoped warning again at line 2015 — one skipped transcript is reported as two.

## Priorities (in order)
1. **Regressions your FA commit introduced** (behaviour that worked at the merge base and now breaks: crashes on malformed input, refusing supported setups or platforms, cap overflows, blocked operations for supported project kinds, slower hot paths). Fix all of them.
2. **MUST-FIX items.** Fix them, test first.
3. **SHOULD-FIX items** that are cheap and local.
- You may DEFER an item whose only trigger is a concurrent attacker who can already rewrite the user's own repository config, files or the plugin's private state during the run (residual TOCTOU), or which needs a design change beyond this packet. Give a one-line reason for each; these go to the 0.14 known-issues list.
- Keep this round under ~250 changed lines. Do not touch files outside the original slice. Do ALL items you decide to fix; never weaken, skip or delete a test (timeouts only with stated load evidence and the narrowest scope).
- Do not commit or push. Update this packet's changelog fragment only if user-visible behaviour changed.
- Report: per item FIXED / DEFERRED (reason) / REFUTED (evidence), files changed, checks run.
