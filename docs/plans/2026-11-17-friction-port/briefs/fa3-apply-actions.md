# FA3 Final-audit fixes: friction apply and host actions

Fix-Origin: final-audit (0.13 range 2e0e643..6e63dba, Astra high, slice 3). Risk: high. Model: sol/high.
Sol reason: concurrent ledger swap, receipt-store consistency and ACL security checks.

## Goal
The read-only final audit of release 0.13 reported these findings. Line numbers refer to commit 6e63dba; the branch may have moved slightly (main 0.12.0 was merged in), so locate by content.

1. `scripts/kaizen_friction_apply.py:499` — **MUST-FIX** — The ledger swap resolves `.ledger-displaced` by name after validating its directory descriptor — a concurrent directory replacement can redirect the swap and displace the live ledger before verification detects it.
1. `scripts/kaizen_friction_actions.py:378` — **MUST-FIX** — Preserving one skipped action restores the entire generation’s old receipt — completing a valid sibling can save it as both `done` and `pending`, causing every subsequent store load to fail.
1. `scripts/kaizen_friction_actions.py:80` — **MUST-FIX** — Darwin ACL checks cover only the final directory — an ancestor whose ACL grants rename or deletion rights passes the mode checks, allowing another account to displace otherwise private state.
1. `scripts/kaizen_friction_actions.py:465` — **SHOULD-FIX** — Import replay compares the original intent with mutable execution status — once an `apply` receipt becomes `terminal`, retrying the identical request is rejected as a different request.
1. `scripts/kaizen_friction_actions.py:520` — **SHOULD-FIX** — Verification checks `.nomedia` only in the canonical checkout — a marker there can close a finding from a linked worktree whose output remains indexed.
1. `scripts/kaizen_friction_actions.py:513` — **SHOULD-FIX** — Inotify verification uses a fixed 100,000-watch threshold while detection uses twice the tracked-file count — a 100,000-file project with 120,000 watches can be marked done while the detector still flags it.
1. `scripts/kaizen_friction_apply.py:460` — **SHOULD-FIX** — Every ledger publication leaves an untracked backup inside the project — even after the ledger edit is committed, the next scheduled mutation cannot establish a clean Git baseline while that backup remains.
1. `scripts/kaizen_friction_actions.py:481` — **SHOULD-FIX** — Every imported generation is retained, including empty receipts — repeated reviews eventually exhaust the shared 1 MiB store and block new imports across projects.

## Rules
- Audit severities are often inflated. For each item, first confirm or refute it against the code, with a failing test where practical (red first). Fix confirmed items at their cause. List refuted or not-reproducible items in the report with evidence; do not make speculative changes for them.
- MUST-FIX items take priority; do every confirmed item, SHOULD-FIX included, unless the fix would exceed ~400 changed lines in total — then fix all MUST-FIX items and list the remaining SHOULD-FIX items as deferred with a one-line reason.
- Supported hosts and platforms are in `docs/hosts.md`; do not add support for a platform the project does not claim (refute such items with the doc line).
- Never weaken, skip or delete an existing test. Keep the existing CLI, file formats and exit codes unless a finding requires a change.
- Stay inside the files this slice names plus their tests; if a fix truly needs another file, say so in the report instead of editing it.
- Do not touch `.claude-plugin/plugin.json`, `CHANGELOG.md` or the version. If a user would notice the fix, write a short changelog fragment to `docs/plans/2026-11-17-friction-port/changelog/FA3.md` (ID = this packet's id); otherwise none.
- Gated items G1–G10 in plan.md stay out of scope. Do not commit or push.
- Report: per item CONFIRMED+fixed / REFUTED (evidence) / DEFERRED (reason), files changed, checks run.

## Verify
- `python3 -m unittest discover -s tests -p 'test_friction_apply.py'`
- `python3 -m unittest discover -s tests -p 'test_host_actions.py'`
- `python3 tools/context_budget.py`
- `git diff --check`
