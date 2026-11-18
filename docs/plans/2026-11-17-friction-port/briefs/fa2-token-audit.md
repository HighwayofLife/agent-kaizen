# FA2 Final-audit fixes: token-audit

Fix-Origin: final-audit (0.13 range 2e0e643..6e63dba, Astra high, slice 2). Risk: high. Model: terra/high.

## Goal
The read-only final audit of release 0.13 reported these findings. Line numbers refer to commit 6e63dba; the branch may have moved slightly (main 0.12.0 was merged in), so locate by content.

1. `scripts/token-audit:993` — **MUST-FIX** — The Darwin ancestry check rejects even a deny-only ACL. I confirmed it rejects this Mac’s home directory, which excludes ordinary Claude and Codex transcripts from signed permission evidence and regression baselines.
1. `scripts/token-audit:404` — **MUST-FIX** — A timestamp-less Claude denial is discarded before replay reconciliation. If the same tool ID also has a valid acceptance, the audit can sign that acceptance with zero ambiguity despite the conflicting decision.
1. `scripts/token-audit:1797` — **MUST-FIX** — After the secure open rejects a Codex transcript, the fallback reopens it by path in blocking mode. A `.jsonl` FIFO can hang the audit indefinitely. The Claude fallback at line 2017 has the same defect.
1. `scripts/token-audit:2704` — **MUST-FIX** — Every extract write uses Unix-only `os.O_NOFOLLOW` and `os.O_DIRECTORY`. On native Windows, the uncaught `AttributeError` aborts a normal audit before it writes the Markdown report, even with `--no-friction`.
1. `scripts/token-audit:365` — **SHOULD-FIX** — Codex pairing takes the first textual `timestamp` in the record. I verified that a payload timestamp preceding the envelope timestamp wins, which can move a call across the audit cutoff or distort its overlap.
1. `scripts/token-audit:1796` — **SHOULD-FIX** — An unsafe Codex rollout increments the global warning before `--cwd` filters it. One unrelated project’s group-writable rollout therefore suppresses the selected project’s regression signature.
1. `scripts/token-audit:1365` — **SHOULD-FIX** — A skipped sample file clears `durationMs` already supplied by the Claude transcript. An oversized or unreadable sample day can turn measured execution into a row-gap estimate or remove a prompted call from timing entirely.
1. `scripts/token-audit:2725` — **SHOULD-FIX** — The extract inclusion check omits `permission_waits`. An audit containing only prompted calls without measured durations reports their wait in Markdown but drops the entire friction block from the machine-readable extract.
1. `scripts/token-audit:260` — **SHOULD-FIX** — The format canary requires a quoted value immediately before the closing braces. I verified that a valid Codex output ending in numeric `exit_code` contributes zero records, undercounting format coverage.

## Rules
- Audit severities are often inflated. For each item, first confirm or refute it against the code, with a failing test where practical (red first). Fix confirmed items at their cause. List refuted or not-reproducible items in the report with evidence; do not make speculative changes for them.
- MUST-FIX items take priority; do every confirmed item, SHOULD-FIX included, unless the fix would exceed ~400 changed lines in total — then fix all MUST-FIX items and list the remaining SHOULD-FIX items as deferred with a one-line reason.
- Supported hosts and platforms are in `docs/hosts.md`; do not add support for a platform the project does not claim (refute such items with the doc line).
- Never weaken, skip or delete an existing test. Keep the existing CLI, file formats and exit codes unless a finding requires a change.
- Stay inside the files this slice names plus their tests; if a fix truly needs another file, say so in the report instead of editing it.
- Do not touch `.claude-plugin/plugin.json`, `CHANGELOG.md` or the version. If a user would notice the fix, write a short changelog fragment to `docs/plans/2026-11-17-friction-port/changelog/FA2.md` (ID = this packet's id); otherwise none.
- Gated items G1–G10 in plan.md stay out of scope. Do not commit or push.
- Report: per item CONFIRMED+fixed / REFUTED (evidence) / DEFERRED (reason), files changed, checks run.

## Verify
- `python3 -m unittest discover -s tests -p 'test_friction_signals.py'`
- `python3 -m unittest discover -s tests -p 'test_friction_codex.py'`
- `python3 -m unittest discover -s tests -p 'test_friction_timeline.py'`
- `python3 -m unittest discover -s tests -p 'test_token_audit_fixes.py'`
- `python3 tools/context_budget.py`
- `git diff --check`
