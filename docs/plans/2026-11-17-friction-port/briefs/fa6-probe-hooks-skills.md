# FA6 Final-audit fixes: host probe, hooks, skills

Fix-Origin: final-audit (0.13 range 2e0e643..6e63dba, Astra high, slice 6). Risk: high. Model: terra/high.

## Goal
The read-only final audit of release 0.13 reported these findings. Line numbers refer to commit 6e63dba; the branch may have moved slightly (main 0.12.0 was merged in), so locate by content.

1. `hooks/audit-notice.sh:73` — **MUST-FIX** — SessionStart runs Python from stdin with the checkout on its import path. A project-local `json.py` can execute before the hook even checks whether Kaizen is disabled.
1. `scripts/host-probe:229` — **MUST-FIX** — The probe runs `git status` with repository-local clean filters enabled. Inspecting a changed tracked file can execute a configured filter during an unattended, read-only audit.
1. `scripts/host-probe:495` — **MUST-FIX** — The output directory is checked for symlinks before the scan and reopened by pathname afterward. Replacing an ancestor during the scan redirects the full, unredacted report outside the selected directory.
1. `skills/friction/SKILL.md:17` — **MUST-FIX** — Interactive collection checks only `hostActions`. With `friction=off` and the default `hostActions=apply`, it still collects and saves process, path and worktree facts before preparation honors the opt-out.
1. `scripts/host-probe:267` — **SHOULD-FIX** — The directory scan recognizes Git repositories only by a `.git` entry. A bare repository inside an ignored build directory counts as regenerable output and can be recommended for backup exclusion.
1. `scripts/host-probe:272` — **SHOULD-FIX** — The scan queues directory pathnames. Replacing a queued directory with a symlink before `scandir` follows it outside the project and attributes unrelated files to regenerable output.
1. `scripts/host-probe:209` — **SHOULD-FIX** — Worktree registration pointers are read without a size limit or deadline. A backlink replaced with a FIFO after Git enumeration can hang the probe past its 30-second budget.
1. `hooks/audit-notice.sh:236` — **SHOULD-FIX** — Every enrolled SessionStart runs synchronous Git worktree discovery before checking whether an action store exists. Slow Git calls can consume the hook timeout and suppress the other notices.
1. `hooks/audit-notice.sh:223` — **SHOULD-FIX** — The action-notice reader treats a symlinked settings file as empty. A supported config symlink containing `hostActions=off` therefore still permits open-action notices.
1. `skills/cycle/SKILL.md:25` — **SHOULD-FIX** — A refresh from a linked worktree writes to that checkout’s `docs/kaizen/`. `friction prepare` rejects the resulting report because it accepts only the canonical project’s directory or the private report folder.
1. `scripts/host-probe:437` — **SHOULD-FIX** — Any matching process counts as active. An idle Spotlight or Time Machine daemon can trigger an indexed-output finding even though the catalogue requires evidence that it is among the busiest processes.
1. `agents/kaizen-auditor.md:21` — **SHOULD-FIX** — The interactive auditor’s command allowlist omits `host-probe` and `review --dry-run`, both required by its cycle instructions. It cannot refresh host evidence or establish the scope of a stale audit.
1. `scripts/kaizen_friction_sample.py:236` — **SHOULD-FIX** — When boot identity is unavailable, every high-load sample clears the rate-limit stamp and launches `ps`. This defeats the five-minute limit precisely when the host is busy.

## Rules
- Audit severities are often inflated. For each item, first confirm or refute it against the code, with a failing test where practical (red first). Fix confirmed items at their cause. List refuted or not-reproducible items in the report with evidence; do not make speculative changes for them.
- MUST-FIX items take priority; do every confirmed item, SHOULD-FIX included, unless the fix would exceed ~400 changed lines in total — then fix all MUST-FIX items and list the remaining SHOULD-FIX items as deferred with a one-line reason.
- Supported hosts and platforms are in `docs/hosts.md`; do not add support for a platform the project does not claim (refute such items with the doc line).
- Never weaken, skip or delete an existing test. Keep the existing CLI, file formats and exit codes unless a finding requires a change.
- Stay inside the files this slice names plus their tests; if a fix truly needs another file, say so in the report instead of editing it.
- Do not touch `.claude-plugin/plugin.json`, `CHANGELOG.md` or the version. If a user would notice the fix, write a short changelog fragment to `docs/plans/2026-11-17-friction-port/changelog/FA6.md` (ID = this packet's id); otherwise none.
- Gated items G1–G10 in plan.md stay out of scope. Do not commit or push.
- Report: per item CONFIRMED+fixed / REFUTED (evidence) / DEFERRED (reason), files changed, checks run.

## Verify
- `python3 -m unittest discover -s tests -p 'test_friction_host_probe.py'`
- `python3 -m unittest discover -s tests -p 'test_host_probe.py'`
- `python3 -m unittest discover -s tests -p 'test_hooks.py'`
- `python3 -m unittest discover -s tests -p 'test_friction_skill.py'`
- `python3 -m unittest discover -s tests -p 'test_friction_sampler.py'`
- `python3 -m unittest discover -s tests -p 'test_repo.py'`
- `python3 -m unittest discover -s tests -p 'test_rules_lint.py'`
- `python3 tools/context_budget.py`
- `git diff --check`
