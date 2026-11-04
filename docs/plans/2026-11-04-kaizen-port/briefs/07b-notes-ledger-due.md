# 07b: `notes-ledger due` (measurement proposals)

## Goal and why
On later cycles, propose the measured effect for notes-ledger rows still marked `measured=no` once enough data exists. It only proposes; the owner approves with `notes-ledger set` (packet 07a). It must compare like with like, never mixing token-audit reports of different scope or window.

## Context
- Repo: ~/github/highwayoflife/agent-kaizen. Python 3.9+ stdlib; read `AGENTS.md`. No personal paths or project names in tracked files.
- Depends on 07a (`scripts/notes-ledger` with config loader, CSV reader, `add`, `set`), 02 (`scripts/packet-report` with `--since/--until/--json`) and 04 (`notesLedger.measureAfterDays`, default 7). Confirm they exist first.
- Token-audit reports live in `<claude home>/audits/` as `token-audit-*.md`, and `<claude home>/audits/projects/<key>/` for per-project ones. Each has `<!-- token-audit-headline {json} -->` (intensity keys: see `intensity = (...)` in `scripts/token-audit` line ~1080; volume keys are never compared) and `<!-- token-audit-scope {json} -->`. Mirror the scope matching of `previous_audit` in `scripts/token-audit` (line ~996): only reports with identical scope JSON are comparable; reports without scope metadata (before 0.4.0) are never compared.
- Report date: parse from the file name (`token-audit-YYYYMMDDThhmmss...Z.md` or `token-audit-YYYY-MM-DD.md`).

## CLI
`notes-ledger due [--project DIR ...] [--json]`. For each CSV row with `measured == no`, status `active`, age >= `measureAfterDays`, print a proposal:
1. Choose the newest report dated before the row date and the newest dated after the row date with identical scope (search each scope that has reports on both sides; prefer the global scope). Need at least two reports dated after the row date in that scope. Else `Not enough data: <reason>` (too few reports / no comparable scope / row too new).
2. Headline intensity keys: before, after, percent change.
3. For each `--project DIR` with an outcome log: `packet-report --until D --json` vs `--since D --json`: first-pass, fix rate, median wall, packets, only when both sides have n >= 8, else `too few packets`.
4. The row's own `Measure:` text verbatim.
Output per row: `Row: <date> <change[:80]>`, the numbers, then `Proposed measured effect: <one factual line with numbers and n>` or `Not enough data: ...`. Never writes any file. No `notesLedger` configured: print `notes-ledger: not configured`, exit 0.

## Scope / do not touch
Edit `scripts/notes-ledger` (add the `due` subcommand and its helpers only) and extend `tests/test_notes_ledger.py` (add a new test class; do not change 07a's tests). No version/CHANGELOG edits.

## Acceptance criteria
1. Fixtures with two later same-scope reports and packets n >= 8 on both sides give a proposal with numbers.
2. Reports of a different scope or window on one side give `Not enough data: no comparable scope` (test incompatible reports); a pre-0.4.0 report without scope is never used.
3. Too few reports, too few packets, row too new, `measured=yes` and non-active rows are skipped or explained as described; nothing is written (assert file hashes unchanged).
4. `--json` prints one object per row.
5. Full suite passes.

## Verification
```
cd ~/github/highwayoflife/agent-kaizen   # your worktree
python3 -m unittest tests.test_notes_ledger -v
python3 -m unittest discover -s tests
python3 scripts/notes-ledger due --help
```

## Working tree
Codex packets run in their own git worktree (`git worktree add ~/github/highwayoflife/agent-kaizen-wt-07b -b kz-07b`, created by the orchestrator, based on the merged 07a). Work only there.

## Reporting
Files changed, test counts, how scopes are matched. Do not commit or push.

## Suggested agent / model / effort
codex-engineer, Terra, medium. Risk: normal.
