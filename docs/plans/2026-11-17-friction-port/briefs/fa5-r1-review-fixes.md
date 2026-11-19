# FA5 r1: pre-merge review fixes

Fix-Origin: final-audit (Sol high pre-merge review of FA5 commit f1b7b37). Risk: high. This is the ONLY fix round for this packet.

## Goal
The original brief is `fa5-allow-worktree.md` (same directory); its rules still apply. A Sol review of your FA5 commit reported:

1. `scripts/dispatch-status:89` — `--worktree-facts` runs legacy PATH-based Git and `git status` before the guarded scan — the public command can still execute an untrusted Git binary or a configured clean filter.
1. `scripts/kaizen_worktree_facts.py:290` — Git reloads configuration and the index after the safety check — a concurrent update can still cause advisory status to execute a clean filter.
1. `scripts/worktree-prune:1` — The fixed shebang requires Python 3.9+ at `/usr/bin/python3` — direct invocation breaks on supported setups where a compatible Python is installed elsewhere.
1. `scripts/allow-rule:747` — Recovery adopts an editor-added grant without proof of publication — a later undo can revoke the editor’s grant once writes are enabled.
1. `scripts/kaizen_worktree_facts.py:277` — Repository identity is taken from the registered primary path — a replacement clone at that path with the same branch and tip can supply another repository’s cleanliness.
1. `scripts/kaizen_worktree_facts.py:231` — An ordinary uninitialized submodule suppresses status for the whole worktree — unrelated dirt is reported as unknown.
1. `scripts/kaizen_worktree_facts.py:228` — Submodule path resolution happens outside the exception handler — a symlink loop can abort the entire report on Python 3.9.
1. `tests/test_dispatch_status.py:169` — The filter fixture leaves its only filtered file marked assume-unchanged — the test can pass even when Git is allowed to run filters.

## Priorities (in order)
1. **Regressions your FA commit introduced** (behaviour that worked at the merge base and now breaks: crashes on malformed input, refusing supported setups or platforms, cap overflows, blocked operations for supported project kinds, slower hot paths). Fix all of them.
2. **MUST-FIX items.** Fix them, test first.
3. **SHOULD-FIX items** that are cheap and local.
- You may DEFER an item whose only trigger is a concurrent attacker who can already rewrite the user's own repository config, files or the plugin's private state during the run (residual TOCTOU), or which needs a design change beyond this packet. Give a one-line reason for each; these go to the 0.14 known-issues list.
- Keep this round under ~250 changed lines. Do not touch files outside the original slice. Do ALL items you decide to fix; never weaken, skip or delete a test (timeouts only with stated load evidence and the narrowest scope).
- Do not commit or push. Update this packet's changelog fragment only if user-visible behaviour changed.
- Report: per item FIXED / DEFERRED (reason) / REFUTED (evidence), files changed, checks run.

## Scope note
`scripts/dispatch-status` is in scope for this round (its `--worktree-facts` path is item 1).
