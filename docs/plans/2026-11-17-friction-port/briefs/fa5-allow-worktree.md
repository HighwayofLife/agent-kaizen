# FA5 Final-audit fixes: allow-rule and worktree tools

Fix-Origin: final-audit (0.13 range 2e0e643..6e63dba, Astra high, slice 5). Risk: high. Model: terra/high.

## Goal
The read-only final audit of release 0.13 reported these findings. Line numbers refer to commit 6e63dba; the branch may have moved slightly (main 0.12.0 was merged in), so locate by content.

1. `scripts/kaizen_worktree_facts.py:250` — **MUST-FIX** — Advisory `git status` can invoke a repository-configured clean filter while inspecting a modified tracked file, executing code during a read-only audit.
1. `scripts/worktree-prune:1` — **MUST-FIX** — The shebang resolves `python3` through the caller’s `PATH`. A checkout-local interpreter earlier on `PATH` executes before `-I` or any repository checks take effect.
1. `scripts/kaizen_worktree_facts.py:226` — **MUST-FIX** — When fixed Git is unavailable, the `PATH` fallback skips the resolver’s checkout exclusions. A repository-local `git` can execute before the advisory report identifies its source.
1. `scripts/allow-rule:745` — **SHOULD-FIX before enabling writes** — If an add stops before publication and an editor independently adds the same rule, recovery records it as managed. A later undo can remove the editor’s grant.
1. `scripts/allow-rule:845` — **SHOULD-FIX before enabling writes** — If an interrupted undo loses its staged file while settings stay unchanged, every retry reopens the missing file and other transactions remain blocked behind the pending undo.
1. `scripts/worktree-prune:157` — **SHOULD-FIX** — An unrecognized file such as a saved patch in the linked Git admin directory passes preflight. The command reports the tree eligible even though the patch has no verified recovery copy.
1. `scripts/kaizen_worktree_facts.py:250` — **SHOULD-FIX** — A stale registration whose path now belongs to another checkout gets that checkout’s status. The report can pair `clean=true` from one repository with the branch and tip of another.
1. `scripts/allow-rule:153` — **SHOULD-FIX** — A truncated newest extract in the project-specific store is silently skipped. An older acceptance can therefore produce a proposal even when the latest audit recorded a denial.
1. `scripts/worktree-prune:171` — **SHOULD-FIX** — The private-ref walk appends every child without an entry cap. A large `refs` or `logs` directory can exhaust memory before the later bounded scan starts.
1. `scripts/kaizen_worktree_facts.py:255` — **SHOULD-FIX** — One assume-unchanged entry makes cleanliness unknown even when `git status` explicitly reports an unrelated untracked file. The report loses a confirmed dirty result.

## Rules
- Audit severities are often inflated. For each item, first confirm or refute it against the code, with a failing test where practical (red first). Fix confirmed items at their cause. List refuted or not-reproducible items in the report with evidence; do not make speculative changes for them.
- MUST-FIX items take priority; do every confirmed item, SHOULD-FIX included, unless the fix would exceed ~400 changed lines in total — then fix all MUST-FIX items and list the remaining SHOULD-FIX items as deferred with a one-line reason.
- Supported hosts and platforms are in `docs/hosts.md`; do not add support for a platform the project does not claim (refute such items with the doc line).
- Never weaken, skip or delete an existing test. Keep the existing CLI, file formats and exit codes unless a finding requires a change.
- Stay inside the files this slice names plus their tests; if a fix truly needs another file, say so in the report instead of editing it.
- Do not touch `.claude-plugin/plugin.json`, `CHANGELOG.md` or the version. If a user would notice the fix, write a short changelog fragment to `docs/plans/2026-11-17-friction-port/changelog/FA5.md` (ID = this packet's id); otherwise none.
- Gated items G1–G10 in plan.md stay out of scope. Do not commit or push.
- Report: per item CONFIRMED+fixed / REFUTED (evidence) / DEFERRED (reason), files changed, checks run.

## Verify
- `python3 -m unittest discover -s tests -p 'test_allow_rule.py'`
- `python3 -m unittest discover -s tests -p 'test_worktree_prune.py'`
- `python3 -m unittest discover -s tests -p 'test_scripts.py'`
- `python3 tools/context_budget.py`
- `git diff --check`
