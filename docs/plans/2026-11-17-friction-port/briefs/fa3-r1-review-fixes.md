# FA3 r1: pre-merge review fixes

Fix-Origin: final-audit (Sol high pre-merge review of FA3 commit 88ab86b). Risk: high. This is the ONLY fix round for this packet.
Sol reason: concurrent ledger swap, receipt-store consistency and ACL security checks.

## Goal
The original brief is `fa3-apply-actions.md` (same directory); its rules still apply. A Sol review of your FA3 commit reported:

1. **MUST-FIX** `scripts/kaizen_friction_apply.py:516` — A backup-directory replacement is detected after the swap, but reconciliation can later accept the installed row and record a decoy at the replacement path — the journal can point to the wrong copy of the displaced ledger.
1. **MUST-FIX** `scripts/kaizen_friction_actions.py:373` — Migrating legacy pending receipts duplicates their IDs before saving — an in-memory check showed a valid 580 KB store exceeding the 1 MiB cap when recovery tried to clear its pending receipts.
1. **SHOULD-FIX** `scripts/kaizen_friction_prepare.py:426` — Scheduled replay drops a completed action from the reconstructed request before reaching `import_actions` — the production path still rejects an identical retry after successful application.
1. **SHOULD-FIX** `scripts/kaizen_friction_apply.py:393` — Cross-device backup storage now blocks ledger operations for enrolled non-Git projects — existing effects in those projects can become unreconcilable and unundoable.
1. **SHOULD-FIX** `scripts/kaizen_friction_apply.py:397` — Recovery leaves legacy `.ledger-displaced` files inside the worktree — existing copies still prevent a clean baseline after the ledger edit is committed.
1. **SHOULD-FIX** `scripts/kaizen_friction_actions.py:505` — Superseded, unacknowledged interactive receipts remain forever even though their generation can no longer be acknowledged — abandoned imports can still exhaust the shared store.
1. **SHOULD-FIX** `tests/test_friction_apply.py:873` — The timeout rises from 30 to 90 seconds for every fixture command, including install and undo — the stated reason covers scheduled reviews only, and the broader increase has no recorded load evidence.

## Priorities (in order)
1. **Regressions your FA commit introduced** (behaviour that worked at the merge base and now breaks: crashes on malformed input, refusing supported setups or platforms, cap overflows, blocked operations for supported project kinds, slower hot paths). Fix all of them.
2. **MUST-FIX items.** Fix them, test first.
3. **SHOULD-FIX items** that are cheap and local.
- You may DEFER an item whose only trigger is a concurrent attacker who can already rewrite the user's own repository config, files or the plugin's private state during the run (residual TOCTOU), or which needs a design change beyond this packet. Give a one-line reason for each; these go to the 0.14 known-issues list.
- Keep this round under ~250 changed lines. Do not touch files outside the original slice. Do ALL items you decide to fix; never weaken, skip or delete a test (timeouts only with stated load evidence and the narrowest scope).
- Do not commit or push. Update this packet's changelog fragment only if user-visible behaviour changed.
- Report: per item FIXED / DEFERRED (reason) / REFUTED (evidence), files changed, checks run.

## Scope note
The `kaizen_friction_prepare.py` replay item belongs to FA4's file; DEFER it here with that reason (it will be a follow-up after both land).
