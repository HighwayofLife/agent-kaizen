# 07a: `notes-ledger add` and `set` (record changes in the owner's notes ledger)

## Goal and why
Owner request: whenever a self-improvement change is applied, record it in a notes ledger (for this owner: a CSV plus a timeline file in a separate notes repo). Paths belong in user config, not code. This packet adds the write side: `add` (append-only, usable unattended) and `set` (owner-approved update). Packet 07b adds `due` (measurement proposals) to the same script.

## Context
- Repo: ~/github/highwayoflife/agent-kaizen. Python 3.9+ stdlib; read `AGENTS.md`. No personal paths or project names in tracked files.
- Depends on packet 04: global key `notesLedger` = `{ "csv": path, "timeline": path?, "measureAfterDays": int? }` in `<claude home>/agent-kaizen.json` (claude home = `$CLAUDE_CONFIG_DIR` or `~/.claude`; copy the paths helper from `scripts/token-audit` lines 17-29; read the JSON directly; `~` expanded). Confirm `rg -n notesLedger scripts/kaizen-scheduled` finds it.
- CSV format (owner's example, read-only: `~/github/highwayoflife/agent-field-notes/data/changes.csv`): header `date,category,change,source,status,measured`; `date` YYYY-MM-DD; `status` planned|active|superseded|reverted; `measured` `no` or `yes`. The "why" and "Measure:" text live inside the `change` cell: `<change> Why: <why> Measure: <measure>`. Use the `csv` module (commas are quoted).
- Timeline format (read-only: `.../findings/changes-timeline.md`): intro paragraph, then 7-day blocks `## yyyy-mm-dd to yyyy-mm-dd`, each with a table `| date | change | status | measured |` and a separator row. Timeline rows hold a shortened change text. Infer block ranges from the headings; with no block covering a date, append a new block continuing the 7-day cadence from the last heading. Keep every other byte of the file unchanged.

## CLI
```
notes-ledger add --date D --category C --change TEXT --why TEXT --measure TEXT --source S [--status planned|active] [--dry-run]
notes-ledger set --match SUBSTRING [--status S] [--measured yes|no] [--effect TEXT] [--dry-run]
```
(`due` is added by packet 07b; leave the argument parser extensible, and make `notes-ledger --help` list `add` and `set`.)
- `add`: appends the CSV row (status default `active`, measured `no`) and, if `timeline` is configured, the timeline row. No `notesLedger.csv` configured: exit 3 with `notes-ledger: no notesLedger.csv in agent-kaizen.json` (callers treat this as optional).
- Concurrency and partial failure (review finding): take an exclusive `fcntl.flock` on `<csv>.lock` (create it next to the CSV) for the whole command. Duplicate detection is per destination: a destination that already has the row (same date, and the CSV change cell or timeline cell equals/prefixes the new text) is skipped, so a retry after a failure between the CSV append and the timeline write completes only the missing timeline row. Print `already recorded` only when both destinations have it. CSV appends are one `write()` of a full line plus flush and fsync; timeline edits rewrite the file through a temp file and rename.
- `set`: the owner-approved write. Finds exactly one CSV row whose change contains `--match` (error exit 2 on zero or several), updates `status`/`measured`, and `--effect TEXT` appends ` Result: TEXT` to the change cell. The matching timeline row is the one with the same date whose change cell is contained in, or is a prefix of, the CSV change cell; update its status and measured columns. Prints a before/after of the row. Rewrites go through a temp file and rename, under the same lock.
- Unattended scheduled runs may call `add` only (packet 09 allow-lists `notes-ledger add` and denies direct edits to the ledger files).

## Scope / do not touch
Create `scripts/notes-ledger` (executable) and `tests/test_notes_ledger.py` (temp dirs, inline fixture CSV/timeline; never read the owner's real notes repo in tests). Hidden test hook allowed: env `NOTES_LEDGER_FAIL_AFTER_CSV=1` makes `add` exit 1 right after the CSV write. Do not edit other files. No version/CHANGELOG edits.

## Acceptance criteria
1. `add` on temp CSV+timeline appends one correctly quoted row and one timeline row in the right block; a second identical `add` prints `already recorded`; a date outside all blocks creates a new block; everything else in both files is byte-identical.
2. `add` without config exits 3 with the message; `--dry-run` writes nothing.
3. With `NOTES_LEDGER_FAIL_AFTER_CSV=1` the CSV has the row and the timeline does not; re-running `add` without the variable adds only the timeline row (CSV has exactly one copy).
4. Two `add` processes started together with different rows both succeed; both rows are in both files, no torn lines.
5. `set --match` updates exactly one CSV row and its timeline row (same date + prefix/contained rule); zero or several matches exit 2 and change nothing.
6. `--help` works for the script and each subcommand.
7. Full suite passes.

## Verification
```
cd ~/github/highwayoflife/agent-kaizen   # your worktree
python3 -m unittest tests.test_notes_ledger -v
python3 -m unittest discover -s tests
python3 scripts/notes-ledger --help
```

## Working tree
Codex packets run in their own git worktree (`git worktree add ~/github/highwayoflife/agent-kaizen-wt-07a -b kz-07a`, created by the orchestrator). Work only there.

## Reporting
Files changed, test counts. Do not commit or push. Stop and report if the timeline cannot be updated without rewriting other lines.

## Suggested agent / model / effort
codex-engineer, Terra, medium. Risk: normal.
