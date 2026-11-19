# FA4 r1: pre-merge review fixes

Fix-Origin: final-audit (Sol high pre-merge review of FA4 commit e2d9da0). Risk: high. This is the ONLY fix round for this packet.
Sol reason: privilege boundary between the unattended model and the runner, symlink TOCTOU and crash-recovery ordering.

## Goal
The original brief is `fa4-scheduler.md` (same directory); its rules still apply. A Sol review of your FA4 commit reported:

1. **MUST-FIX** `scripts/kaizen-scheduled:3114` — Publication rereads `state.json` after the model exits and preserves a later `reviewed_at` — an auto review with `--audits` inside the checkout can suppress future activity-gated reviews.
1. **MUST-FIX** `scripts/kaizen_friction_prepare.py:609` — A null or numeric marker cutoff raises `AttributeError` outside the scheduler’s recovery handler — one malformed marker aborts ordinary reviews for every later project.
1. **SHOULD-FIX** `scripts/kaizen_friction_prepare.py:613` — A newer preparation generation deletes an already-published marker before persisting its cutoff — interactive preparation after a crash can reopen the same review window.
1. **SHOULD-FIX** `scripts/kaizen-scheduled:2745` — Successful friction-disabled reviews retain the old cutoff after a publication recovery error — a persistent backup-directory fault makes the scheduler pay to review the same activity repeatedly.
1. **SHOULD-FIX** `scripts/kaizen-scheduled:3100` — A project with unknown Git scope triggers a recovery failure whenever the shared action store exists, even with no marker — ordinary auto reviews regress to propose-only and the scheduler exits nonzero.

## Priorities (in order)
1. **Regressions your FA commit introduced** (behaviour that worked at the merge base and now breaks: crashes on malformed input, refusing supported setups or platforms, cap overflows, blocked operations for supported project kinds, slower hot paths). Fix all of them.
2. **MUST-FIX items.** Fix them, test first.
3. **SHOULD-FIX items** that are cheap and local.
- You may DEFER an item whose only trigger is a concurrent attacker who can already rewrite the user's own repository config, files or the plugin's private state during the run (residual TOCTOU), or which needs a design change beyond this packet. Give a one-line reason for each; these go to the 0.14 known-issues list.
- Keep this round under ~250 changed lines. Do not touch files outside the original slice. Do ALL items you decide to fix; never weaken, skip or delete a test (timeouts only with stated load evidence and the narrowest scope).
- Do not commit or push. Update this packet's changelog fragment only if user-visible behaviour changed.
- Report: per item FIXED / DEFERRED (reason) / REFUTED (evidence), files changed, checks run.
