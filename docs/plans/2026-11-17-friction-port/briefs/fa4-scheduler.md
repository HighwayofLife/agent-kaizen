# FA4 Final-audit fixes: scheduler and preparation

Fix-Origin: final-audit (0.13 range 2e0e643..6e63dba, Astra high, slice 4). Risk: high. Model: sol/high.
Sol reason: privilege boundary between the unattended model and the runner, symlink TOCTOU and crash-recovery ordering.

## Goal
The read-only final audit of release 0.13 reported these findings. Line numbers refer to commit 6e63dba; the branch may have moved slightly (main 0.12.0 was merged in), so locate by content.

1. [scripts/kaizen-scheduled:2945](scripts/kaizen-scheduled#L2945) — **MUST-FIX** — Reconciliation executes Python helpers from the installation directory after the model exits — when an auto review covers the installation checkout, the model can edit those helpers and the runner then executes the changed code with its own permissions.
1. [scripts/kaizen-scheduled:2993](scripts/kaizen-scheduled#L2993) — **MUST-FIX** — Comment stripping reopens the temporary output by pathname and truncates it — replacing that entry with a symlink between validation and writing can overwrite an unrelated user file.
1. [scripts/kaizen-scheduled:1288](scripts/kaizen-scheduled#L1288) — **MUST-FIX** — The host-action deny rules use the default audits directory even when `--audits` selects another — I confirmed that an override inside the reviewed project leaves its action store and receipts covered by the model’s edit grant.
1. [scripts/kaizen-scheduled:2475](scripts/kaizen-scheduled#L2475) — **MUST-FIX** — A publication-recovery error skips the entire project and leaves the scheduler exit status successful — an unsafe or symlinked backup directory can suppress every ordinary review even with friction disabled and no publication pending.
1. [scripts/kaizen_friction_prepare.py:600](scripts/kaizen_friction_prepare.py#L600) — **SHOULD-FIX** — The publication marker is shared across `--audits` roots but stores only the proposal basename — a run using another root can delete the original recovery marker when it finds no proposal there.
1. [scripts/kaizen_friction_prepare.py:611](scripts/kaizen_friction_prepare.py#L611) — **SHOULD-FIX** — Recovery unlinks the publication marker before the caller persists `reviewed_at` — a crash in that gap leaves a published proposal and an old activity cutoff, allowing the same review to run again.
1. [scripts/kaizen-scheduled:2477](scripts/kaizen-scheduled#L2477) — **SHOULD-FIX** — A recovered review records recovery time as its activity cutoff — commits and sessions created after publication but before recovery are skipped by the next activity gate.
1. [scripts/kaizen-scheduled:2657](scripts/kaizen-scheduled#L2657) — **SHOULD-FIX** — A failed friction import is logged and the review still advances `reviewed_at` — under the default activity gate, a transient import failure can go unretried until the evidence expires.
1. [scripts/kaizen_friction_prepare.py:358](scripts/kaizen_friction_prepare.py#L358) — **SHOULD-FIX** — The indexed-output fallback catches ownership refusals as well as missing paths — an output belonging to a separately enrolled nested repository can become a host-action suggestion for its parent.
1. [scripts/kaizen-scheduled:723](scripts/kaizen-scheduled#L723) — **SHOULD-FIX** — Discovery treats every `.git` file as a linked-worktree pointer — ordinary submodules use a `.git` file pointing to their common Git directory, so valid enrolled submodules lose friction preparation and host actions.
1. [scripts/kaizen_friction_prepare.py:343](scripts/kaizen_friction_prepare.py#L343) — **SHOULD-FIX** — The prepared view drops timing basis and gives measured and row-gap regressions for the same subject the same ID — the reviewer cannot reliably distinguish an estimate from a measurement when ranking them.

## Rules
- Audit severities are often inflated. For each item, first confirm or refute it against the code, with a failing test where practical (red first). Fix confirmed items at their cause. List refuted or not-reproducible items in the report with evidence; do not make speculative changes for them.
- MUST-FIX items take priority; do every confirmed item, SHOULD-FIX included, unless the fix would exceed ~400 changed lines in total — then fix all MUST-FIX items and list the remaining SHOULD-FIX items as deferred with a one-line reason.
- Supported hosts and platforms are in `docs/hosts.md`; do not add support for a platform the project does not claim (refute such items with the doc line).
- Never weaken, skip or delete an existing test. Keep the existing CLI, file formats and exit codes unless a finding requires a change.
- Stay inside the files this slice names plus their tests; if a fix truly needs another file, say so in the report instead of editing it.
- Do not touch `.claude-plugin/plugin.json`, `CHANGELOG.md` or the version. If a user would notice the fix, write a short changelog fragment to `docs/plans/2026-11-17-friction-port/changelog/FA4.md` (ID = this packet's id); otherwise none.
- Gated items G1–G10 in plan.md stay out of scope. Do not commit or push.
- Report: per item CONFIRMED+fixed / REFUTED (evidence) / DEFERRED (reason), files changed, checks run.

## Verify
- `python3 -m unittest discover -s tests -p 'test_friction_prepare.py'`
- `python3 -m unittest discover -s tests -p 'test_friction_review.py'`
- `python3 -m unittest discover -s tests -p 'test_schedule_security.py'`
- `python3 -m unittest discover -s tests -p 'test_schedule_robustness.py'`
- `python3 -m unittest discover -s tests -p 'test_schedule.py'`
- `python3 -m unittest discover -s tests -p 'test_schedule_steps.py'`
- `python3 tools/context_budget.py`
- `git diff --check`
