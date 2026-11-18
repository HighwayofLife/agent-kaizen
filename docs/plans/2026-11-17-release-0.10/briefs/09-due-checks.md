# 09: Due checks: report, recorded completions, notices

## Goal and why

The model, roster and whats-new checks had never run in the field and nothing flagged it, because no completion date is recorded anywhere (file mtimes are not trustworthy). Record each completion when a skill really finishes, report checks that were never run or are older than their cadence (30, 60 and 30 days), and show that in the scheduled checks report and the session-start notice. This packet merges the report side and the recording side so one owner designs `checks.json`.

## Context

- agent-kaizen is a Claude Code plugin; scripts are stdlib-only Python 3.9, hooks are bash (`shellcheck -S warning hooks/*.sh`). Read `AGENTS.md` (Rules) and `docs/autonomy.md` (the write rules: one plain command per Bash call, no `cd`, no variables).
- Already merged: `scripts/experiment-check` (packet 02; interface `--project DIR [--pending-days N] [--today YYYY-MM-DD] [--json]`; first stdout line `experiment-check: N finding(s)`; exit 0 none, 1 findings, 2 usage or unreadable; JSON keys `project`, `today`, `pending_days`, `ledger`, `legacy_table`, `legacy_rows`, `metadata_since`, `findings`, `counts`, `status`); the scheduled step and hook notice that call it (packet 06; `run_checks` in `scripts/kaizen-scheduled:1482-1507` runs `run_step("experiment-check", options, ["--project", <canonical>], (0, 1))` and adds `## Experiments: <path>` sections; `hooks/audit-notice.sh` runs it once a day per project, bounded by `KAIZEN_NOTICE_TIMEOUT`, using the `$root` and `$key` it already finds).
- Per-project machine state lives in `<audits>/projects/<key>/` next to `state.json` (`scripts/kaizen-scheduled:697-722`). `key(path)` :263; `Project.folder` :540-545; `audits_dir()` :153; `canonical_project(directory)` :2064 returns the project a real run uses for a directory or one above it (a linked worktree resolves to the main worktree's project); `config_lock(path)` :2077 is an `flock` on `<name>.lock` for serialised read-modify-write; `write_config` :2026 shows write-to-temp then `os.replace` with mode preserved; `config set --for` handling at :2190-2245 shows how `--for DIR` is validated (`docs/kaizen/` (external) must exist). The hook finds the same key through `projects/index.json` (external) (`hooks/audit-notice.sh:19-28`), so it handles worktrees too. Retention does not touch `checks.json` (`RETENTION_KINDS` :1205).
- Skills to edit: `skills/models/SKILL.md` (Done when, :48-51), `skills/roster/SKILL.md` (Phase 6 and the end of the Task, :99-104), `skills/whats-new/SKILL.md` (Done when, about :43-45), `skills/cycle/SKILL.md` step 5 at :25-29 (the models line :26 infers the date from "the last `models-*.md` audit or ledger entry"; the roster line :28 from `model-roster.md` age). The ledger-row sentence at cycle :37 and the calibration sentence at :24 belong to other packets.
- Test style and helpers: `tests/test_experiment_check.py` (packet 02); `tests/test_schedule_steps.py:60-130` (stubs in a temp scripts dir; `check_text()`); `tests/test_hooks.py:346-410` and `run()` :21; for a linked worktree use real `git` as `tests/test_dispatch_guards.py:15-22` does. Config key tests: `tests/test_config_keys.py`.
- Decisions already made (orchestrator):
  - The state file is `<audits>/projects/<key>/checks.json` (key of the canonical project): `{"models": "YYYY-MM-DD", "roster": "...", "whats-new": "..."}` plus any other keys preserved. It is per machine, not tracked.
  - Only `kaizen-scheduled checks record` writes it, and only from the skill path described below; reads are by `experiment-check` and by the commands in this brief.
  - Write rules: serialise with `config_lock`; read-modify-write under the lock; write to a temp file in the same directory and `os.replace`; before replacing keep the previous file as `checks.json.bak`; an existing file that is not valid JSON or not an object is never overwritten (exit 2, message to fix or remove it).
  - Authorization: recording is bookkeeping, allowed in every interactive mode including `propose`, after the check ran to completion. Never when the check was skipped, declined or failed, and never in a scheduled or propose-only run (scheduled runs skip web checks). It writes no `kaizen-backup` manifest because it is not a project change; `.bak` is its rollback. State this in `docs/autonomy.md`.
  - Cadences: models 30 days, roster 60, whats-new 30. A missing file or key is "never run". Age strictly greater than the cadence is overdue. A future date, a non-ISO value or an unreadable file is `unknown` (actionable, never treated as fresh).
  - The nag fires for every enrolled project until its first recorded completion, because no state exists today; say so in `docs/scheduling.md`.
  - This packet does not edit CHANGELOG.md or README.md.

## Scope / do not touch

Creates: `tests/test_checks_record.py`.
Edit only: `scripts/experiment-check`, `tests/test_experiment_check.py`, `scripts/kaizen-scheduled` (the new `checks` command, the `run_checks` step arguments, the module docstring), `tests/test_schedule_steps.py`, `hooks/audit-notice.sh`, `tests/test_hooks.py`, `skills/models/SKILL.md`, `skills/roster/SKILL.md`, `skills/whats-new/SKILL.md`, `skills/cycle/SKILL.md` (:25-29 only), `docs/autonomy.md`, `docs/scheduling.md`, `scripts/rules-lint.patterns`, `tests/test_rules_lint.py` (one new test method; leave `tests/fixtures/rules_lint/` alone).
Do not touch `scripts/install-schedule`, `scripts/kaizen-link`, `scripts/README.md` (packet 11 documents the scripts), `README.md`, `CHANGELOG.md`.

## Steps

Part A (checker and writer):

1. `experiment-check --checks --state-file PATH` (PATH required with `--checks`, else exit 2): adds a text section `## Due checks` (one line per check, e.g. `- models: never run (cadence 30 days)`, `- roster: last 2026-09-01, 77 days ago (cadence 60 days): overdue`) and a JSON key `checks` = `[{name, last, cadence_days, age_days, status, reason}]` with `status` one of `never_run`, `overdue`, `fresh`, `unknown`. Never-run, overdue and unknown are findings: they count in the first line and set exit 1. Without `--checks` the output is byte-for-byte what packet 02 produces. Read-only; no network.
2. `kaizen-scheduled checks path --for DIR` prints the state-file path for DIR's canonical project (it does not create anything). `kaizen-scheduled checks record --for DIR NAME [--date YYYY-MM-DD]` (NAME one of `models`, `roster`, `whats-new`; default date is today in UTC; a future date or a DIR without `docs/kaizen/` exits 2) writes it by the write rules above and prints `recorded <name> <date> in <path>`. Add both to the module docstring and `--help`.
3. Tests for Part A: `tests/test_experiment_check.py` for `--checks` (never run, missing file, boundary at exactly the cadence and one day past, future date, malformed value, invalid JSON file, key preservation unaffected, JSON keys, byte-identical output without `--checks`); `tests/test_checks_record.py` for the writer (first write creates the file and directory; second preserves other keys and creates `.bak` holding the previous content; invalid JSON is not overwritten and exits 2; invalid name, future date and non-enrolled DIR exit 2; two writers started together with different names, repeated 10 times, always end with both keys; recording from a linked `git worktree` of an enrolled repo writes the main project's file, `checks path --for <worktree>` equals `checks path --for <main>`, and that path equals `Project.folder / "checks.json"` from the scheduler's `discover()` for the main directory (load the script with `runpy.run_path` as `tests/test_schedule_robustness.py:587` does)). Use `CLAUDE_CONFIG_DIR` pointing at a temp directory.

Checkpoint: run `git diff --stat`. If Part A alone is already over about 300 changed lines, or the total estimate is over 450, stop after Part A and report; the orchestrator dispatches Part B from this same brief.

Part B (wiring, skills, docs):

4. `run_checks`: add `["--checks", "--state-file", str(project.folder / "checks.json")]` to the per-project `experiment-check` call. Hook: when `$key` is non-empty, pass `--checks --state-file "$dir/projects/$key/checks.json"`; with no key, run without `--checks` (nowhere to look; never report never-run for an unknown state location).
5. Skills: in `models`, `roster` and `whats-new`, add a short section "Record the check" saying: only when this run completed the check and delivered its result (not skipped, declined or failed; never in a scheduled or propose-only run), run as one plain command `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kaizen-scheduled checks record --for . <models|roster|whats-new>`; if it fails, report that and do not edit the file by hand. In `cycle` step 5 replace the date inference: scheduled runs read the `## Due checks` lines inside the `## Experiments: ...` section of the newest `checks-*.md`; interactive runs run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kaizen-scheduled checks path --for .` and then `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/experiment-check --project . --checks --state-file <that path>` as two separate commands; a never-run or overdue check means follow its skill; keep the context-surface bullet unchanged.
6. Docs: `docs/autonomy.md` gains a short section before "Undo" stating the recording authorization above. `docs/scheduling.md` lists `<audits>/projects/<key>/checks.json` in the audits tree (about :104-114), describes `checks path|record` and `.bak`, and says the nag appears everywhere until the first recorded completion.
7. Stale wording: add a pattern for ``last `models-\*\.md` audit or ledger entry`` (the old inference) to `scripts/rules-lint.patterns`, a new test method in `tests/test_rules_lint.py` that writes the old sentence into a temp repo `CLAUDE.md` and expects a hit, and run `rg -n "models-\*\.md. audit or ledger" --glob '!docs/plans/**'` to confirm the old sentence is gone.
8. Tests for Part B: `tests/test_schedule_steps.py` (the stub receives `--checks --state-file <audits>/projects/<key>/checks.json` for each of two projects); `tests/test_hooks.py` (key found through `projects/index.json`: never-run notice appears; all three recorded fresh with a state file written by `checks record` gives no notice; no key gives no checks section; from a linked worktree path the same state file is used).

## Acceptance criteria

1. `experiment-check --checks` behaves as in step 1, including exit codes and JSON, and is unchanged without the flag.
2. `checks record` obeys every write rule; the concurrent test never loses a key; the linked-worktree test passes; `kaizen-scheduled --help` documents `checks`.
3. The scheduled report shows per-project due checks from the recorded state; the hook shows them only when the state location is known.
4. The three skills and `cycle` describe recording and reading as in step 5, with no hand-edit instruction and no date inference left from `models-*.md`, ledger entries or `model-roster.md` age; no skill text tells a scheduled run to record.
5. `docs/autonomy.md` and `docs/scheduling.md` match the behaviour; the stale-wording test passes.
6. Existing tests in the regression modules stay green; `shellcheck -S warning hooks/*.sh` is clean.

## Verification

```sh
python3 -m unittest discover -s tests -p 'test_experiment_check.py' -v
python3 -m unittest discover -s tests -p 'test_checks_record.py' -v
python3 -m unittest discover -s tests -p 'test_schedule_steps.py' -v
python3 -m unittest discover -s tests -p 'test_hooks.py' -v
for m in test_rules_lint test_process_rules test_config_keys test_repo; do python3 -m unittest discover -s tests -p "$m.py"; done
python3 scripts/kaizen-scheduled checks --help
shellcheck -S warning hooks/*.sh
```

## Reporting

At most 20 lines: files changed, test results, which parts were done, limitations, one proposed CHANGELOG bullet (do not edit CHANGELOG.md). Do not commit or push. Stop and report if packet 02 or 06 interfaces differ from those above.

## Suggested agent / model / effort and risk

`codex-engineer` / Terra medium. Risk: **normal**. Estimated size: 480 lines, over the usual limit because the orchestrator merged two packets; the checkpoint after Part A is the declared split. Batch reviewer regression modules: `test_experiment_check`, `test_checks_record`, `test_schedule_steps`, `test_hooks`, `test_rules_lint`, `test_process_rules`.
