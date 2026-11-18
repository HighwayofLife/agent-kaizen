# FA1 r1: pre-merge review fixes

Fix-Origin: final-audit (Sol high pre-merge review of FA1 commit 9c35b72). Risk: high. This is the ONLY fix round for this packet.
Sol reason: TOCTOU, durability (fsync ordering) and permission-restoring undo in the backup/undo transaction code.

## Goal
The original brief is `fa1-backup.md` (same directory); its rules still apply. A Sol review of your FA1 commit reported:

1. MUST-FIX `scripts/kaizen-backup:278` — Forced undo recreates missing parents with umask-derived permissions — a formerly `0700` directory can become `0755`, exposing restored files that relied on the directory for privacy.
1. MUST-FIX `scripts/kaizen-backup:2214` — Shared-path checks run only when a Git-backed change populated `versions` — an ordinary-only `undo run` can overwrite an intervening editor save and exit successfully. Reproduced in memory.
1. MUST-FIX `scripts/kaizen-backup:1131` — Commit syncs the current backup inode without matching it to the copy verified in preflight — a same-mode replacement between those steps can leave a published ref whose undo rejects the backup.
1. MUST-FIX `scripts/kaizen-backup:1139` — Sync stops at the backup root’s immediate parent, although `mkdir(parents=True)` can create several ancestors — a power loss can still discard the manifest, copies, and journal while the Git ref survives.
1. SHOULD-FIX `scripts/kaizen-backup:1106` — Legacy mode validation depends on the live file’s permissions — a missing target or a legitimate chmod blocks restoration even with `--force`.
1. SHOULD-FIX `scripts/kaizen-backup:2128` — Ordinary undo now parses every ref journal — one corrupt or unreadable record blocks unrelated rollbacks, including scheduled recovery.
1. SHOULD-FIX `scripts/kaizen-backup:1736` — The backup source walk requires read access to every ancestor — `begin` now rejects readable files behind search-only directories that it previously backed up.
1. SHOULD-FIX `scripts/kaizen-backup:1881` — Prune still protects journaled folders by name alone — it can delete an old renamed transaction’s rollback material before the owner restores its original name.

## Priorities (in order)
1. **Regressions your FA commit introduced** (behaviour that worked at the merge base and now breaks: crashes on malformed input, refusing supported setups or platforms, cap overflows, blocked operations for supported project kinds, slower hot paths). Fix all of them.
2. **MUST-FIX items.** Fix them, test first.
3. **SHOULD-FIX items** that are cheap and local.
- You may DEFER an item whose only trigger is a concurrent attacker who can already rewrite the user's own repository config, files or the plugin's private state during the run (residual TOCTOU), or which needs a design change beyond this packet. Give a one-line reason for each; these go to the 0.14 known-issues list.
- Keep this round under ~250 changed lines. Do not touch files outside the original slice. Do ALL items you decide to fix; never weaken, skip or delete a test (timeouts only with stated load evidence and the narrowest scope).
- Do not commit or push. Update this packet's changelog fragment only if user-visible behaviour changed.
- Report: per item FIXED / DEFERRED (reason) / REFUTED (evidence), files changed, checks run.
