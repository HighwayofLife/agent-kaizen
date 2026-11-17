# 02: Experiment checker (`experiment-check`) and the ledger columns

## Goal and why

Every efficiency-ledger row in the field stayed `measured: pending` for weeks and a started experiment was never initialised; nothing noticed. Give every experiment a metric command and a review date in the existing project ledger, and add a read-only checker that lists rows past their review date, rows pending too long, and rows missing the new fields. Packets 06 (notices) and 09 (due checks) build on this script's output, so the interface below is fixed.

## Context

- agent-kaizen is a Claude Code plugin; scripts are stdlib-only Python 3.9, tests in `tests/`. Read `AGENTS.md` (Rules).
- The project ledger is `docs/kaizen/LEDGER.md` (external), created by `skills/start/SKILL.md:25-27` with the header `date | change | why (which audit finding) | expected effect | measured effect | keep/revert`. Existing parsers find columns by lowercase header name, so appended columns do not break them: `scripts/kaizen-project-report:57-90` (pending = measured cell exactly `pending`) and `hooks/session-notes.sh:47-77`.
- Every writer of ledger rows must follow the new contract: `skills/start/SKILL.md:25-27`, `docs/autonomy.md:81` (step 5 "Ledger row"; other skills defer to it), `skills/models/SKILL.md:46`, `skills/roster/SKILL.md:101`, `skills/cycle/SKILL.md:37` (project ledger row; leave the `notes-ledger add` CSV part alone, it is a separate file).
- `kaizen-scheduled config` files: project `docs/kaizen/config.json` (external), global `<CLAUDE_CONFIG_DIR or ~/.claude>/agent-kaizen.json` (copy the one-line pattern at `scripts/packet-report:223`). Unknown keys are ignored by `kaizen-scheduled`, so reading `pendingDays` here is safe; packet 06 registers the key for `config set`.
- Test style: `tests/test_packet_report.py:1-17`. CI runs `--help` on every tracked script (`.github/workflows/ci.yml:46-50`): `#!/usr/bin/env python3`, executable bit.
- Decisions already made (orchestrator):
  - New columns are appended: `metric command` and `review date` (header names, case-insensitive, found by name). Old six-column tables and old rows stay valid.
  - A row dated before `2026-11-17` (constant `METADATA_SINCE`) is legacy: its missing fields are never a finding. Rows dated on or after it must carry both fields when open.
  - A metric command is written in backticks and never executed. A literal pipe inside a cell is written `\|`; the parser splits cells on an unescaped `|` and unescapes `\|`.
  - Open row = `measured effect` cell empty or (case-insensitive) starting with `pending`, and `keep/revert` cell not starting with `reverted`.
  - `pendingDays`: `--pending-days` flag, else project config, else global config, else 10; a value that is not an integer of at least 1 (or is a bool) is ignored with a one-line stderr note. Age is strictly greater than N.
  - Exit codes: 0 no findings, 1 findings, 2 usage error or unreadable/malformed ledger (message on stderr). A missing `LEDGER.md` is not an error: exit 0 with `no ledger`.
- This packet does not edit CHANGELOG.md.

## Scope / do not touch

Creates: `scripts/experiment-check`, `tests/test_experiment_check.py`.
Edit only: `skills/start/SKILL.md`, `skills/models/SKILL.md`, `skills/roster/SKILL.md`, `skills/cycle/SKILL.md` (the ledger-row step at :37 only), `docs/autonomy.md` (:81 only), `tests/test_session_notes.py` and `tests/test_project_report.py` (one added test each).
Do not touch `scripts/kaizen-scheduled`, `hooks/`, `scripts/install-schedule`, `scripts/kaizen-link`, `scripts/README.md`, `README.md`, `CHANGELOG.md`.

## Interface (fixed; packets 06 and 09 depend on it)

`experiment-check --project DIR [--pending-days N] [--today YYYY-MM-DD] [--json]`; read-only; no network; never runs a metric command.

Text output: first line `experiment-check: N finding(s)`. Then, only for non-empty sections, in this order: `## Past review date`, `## Pending too long`, `## Missing metadata`, `## Malformed`; each row is one line (`- <date> <change, 60 chars> | review <date> | <detail>`), at most 8 rows per section then `... K more`. When the table has no new columns, or there are legacy rows with no metadata, add the line `legacy: R row(s) have no metric command or review date (not a finding)`. Missing ledger: `experiment-check: 0 finding(s)` then `no ledger`.

JSON (`--json`, one object): `project`, `today`, `pending_days`, `ledger` (path or null), `legacy_table` (true when the header lacks either new column), `legacy_rows` (int), `metadata_since`, `findings` (list of `{kind, row, date, change, age_days, metric_command, review_date, reason}`, where `metric_command` is the cell with surrounding backticks stripped and `\|` unescaped, or null when empty; `kind` is `past_review`, `pending_too_long`, `missing_metadata` or `malformed`; `row` is the 1-based data-row number; a row can appear under more than one kind), `counts` (kind to int), `status` (`ok` or `findings`).

Finding rules: `past_review` = open and `review date` strictly before today. `pending_too_long` = open and age (today minus row date) strictly greater than N, for every open row including legacy ones. `missing_metadata` = open, dated on or after `METADATA_SINCE`, and the table has the new columns and either cell is empty (`n/a`, `-`, `none` count as empty). `malformed` = non-empty `review date` that is not `YYYY-MM-DD`, or a row with a non-empty `change` and a non-ISO `date`. Separator and header rows are skipped silently. Short rows (fewer cells than the header) read missing cells as empty.

## Steps

1. Write `scripts/experiment-check` and `tests/test_experiment_check.py`; run them.
2. Update the writers: `skills/start/SKILL.md` creates the eight-column header (the six existing, then `metric command`, `review date`) and tells the skill that every new row gets both fields: the command in backticks, a pipe written `\|`, "never run automatically"; the review date `YYYY-MM-DD`, the day the metric will be read (normally the next audit; at most 30 days out). If an existing ledger has the old six columns, the first new row adds the two header cells and two separator cells in the same Edit and leaves older rows untouched. Mirror one short sentence of that rule in `docs/autonomy.md:81`, `skills/models/SKILL.md:46`, `skills/roster/SKILL.md:101` and `skills/cycle/SKILL.md:37`, each pointing at `${CLAUDE_PLUGIN_ROOT}/skills/start/SKILL.md` for the format. `${CLAUDE_PLUGIN_ROOT}/scripts/experiment-check` may be named as the checker.
3. Add one test to `tests/test_session_notes.py` (an eight-column ledger with an old pending row still counts as pending; model it on :49-56) and one to `tests/test_project_report.py` (same ledger lists the pending row; model it on :44-56).

## Acceptance criteria

1. `scripts/experiment-check --help` exits 0 and documents flags, exit codes and the config key.
2. Legacy six-column table with open rows: no `missing_metadata`, `legacy_table` true, `legacy_rows` counted, exit 0 unless a row is pending longer than N.
3. Eight-column table: boundaries tested with `--today`: pending exactly N days is not a finding, N+1 is; review date equal to today is not past review, the day before is; row dated 2026-11-16 with empty fields is legacy, 2026-11-17 is `missing_metadata`.
4. Measured rows (`measured effect` filled) and rows whose `keep/revert` starts with `reverted` are never findings.
5. `\|` inside a metric command is unescaped in JSON `metric_command` and does not shift later columns; a short row does not crash.
6. Malformed review date and malformed row date are reported under `malformed`; missing ledger exits 0 with `no ledger`; a ledger without `date` or `measured effect` headers exits 2 with a stderr message; unreadable path exits 2.
7. `--pending-days` precedence: flag over project config over global config over 10; `0`, `-1`, `"x"`, `true` in a config file are ignored with a stderr note; `--pending-days 0` exits 2. Test with `CLAUDE_CONFIG_DIR` pointing at a temp directory.
8. `--json` has exactly the keys above; text first line is `experiment-check: N finding(s)`; output with 20 findings stays within about 40 lines.
9. The command in a ledger row is never executed (a test row whose command would create a marker file leaves no marker).
10. The five writer files describe the new columns; `rg -n "keep/revert" skills docs/autonomy.md` shows no six-column header left in a writer instruction. The session-notes and project-report tests pass with the eight-column ledger.

## Verification

```sh
python3 -m unittest discover -s tests -p 'test_experiment_check.py' -v
scripts/experiment-check --help
for m in test_session_notes test_project_report test_repo test_process_rules; do python3 -m unittest discover -s tests -p "$m.py"; done
rg -n "keep/revert" skills docs/autonomy.md
```

## Reporting

At most 20 lines: files changed, test results, limitations, one proposed CHANGELOG bullet (do not edit CHANGELOG.md). Do not commit or push. Stop and report if a writer file is missing or reads differently from the lines above. Split trigger: if the packet exceeds about 400 changed lines, finish the script, its tests and `skills/start/SKILL.md`, then stop and list the unfinished writer edits for a follow-up packet.

## Suggested agent / model / effort and risk

`codex-engineer` / Terra medium. Risk: **normal**. Estimated size: 420 lines. Batch reviewer regression modules: `test_session_notes`, `test_project_report`, `test_process_rules`, `test_repo`.
