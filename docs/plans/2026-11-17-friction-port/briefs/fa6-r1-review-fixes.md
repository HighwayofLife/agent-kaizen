# FA6 r1: pre-merge review fixes

Fix-Origin: final-audit (Sol high pre-merge review of FA6 commit 664cb50). Risk: high. This is the ONLY fix round for this packet.

## Goal
The original brief is `fa6-probe-hooks-skills.md` (same directory); its rules still apply. A Sol review of your FA6 commit reported:

1. `scripts/host-probe:199` — The filter check covers only the parent repository and runs separately from `git status` — status can still execute clean filters configured in submodules or added after the check.
1. `scripts/host-probe:37` — Output setup unconditionally uses POSIX-only flags — the Windows CLI crashes before it can write a report.
1. `tests/test_friction_sampler.py:205` — Cancellation can arrive before the child installs its SIGTERM-ignore handler — the cancellation test can pass without exercising cleanup of a TERM-resistant child.
1. `scripts/host-probe:416` — `resolve()` can follow a symlink introduced after the symlink check — the descriptor-based scan can still count files outside the worktree as regenerable.
1. `hooks/audit-notice.sh:249` — Once the shared action store exists, SessionStart still waits synchronously for Git discovery — a slow checkout can suppress every notice.
1. `scripts/host-probe:595` — The probe prints the original pathname even if the pinned output directory moved — callers receive success with a path that does not locate the report.
1. `skills/cycle/SKILL.md:24` — Linked worktrees write refreshed audits to the canonical checkout but never search it — later runs can reuse a stale audit and repeat the refresh.
1. `scripts/host-probe:332` — The scan keeps one descriptor open per queued sibling directory — wide build trees can exhaust the descriptor limit and discard all directory findings.
1. `scripts/kaizen_friction_sample.py:232` — Intermittent boot-ID failures reset the rate limit on each transition — a mocked known/unknown/known sequence admitted three queries at the same timestamp.

## Priorities (in order)
1. **Regressions your FA commit introduced** (behaviour that worked at the merge base and now breaks: crashes on malformed input, refusing supported setups or platforms, cap overflows, blocked operations for supported project kinds, slower hot paths). Fix all of them.
2. **MUST-FIX items.** Fix them, test first.
3. **SHOULD-FIX items** that are cheap and local.
- You may DEFER an item whose only trigger is a concurrent attacker who can already rewrite the user's own repository config, files or the plugin's private state during the run (residual TOCTOU), or which needs a design change beyond this packet. Give a one-line reason for each; these go to the 0.14 known-issues list.
- Keep this round under ~250 changed lines. Do not touch files outside the original slice. Do ALL items you decide to fix; never weaken, skip or delete a test (timeouts only with stated load evidence and the narrowest scope).
- Do not commit or push. Update this packet's changelog fragment only if user-visible behaviour changed.
- Report: per item FIXED / DEFERRED (reason) / REFUTED (evidence), files changed, checks run.
