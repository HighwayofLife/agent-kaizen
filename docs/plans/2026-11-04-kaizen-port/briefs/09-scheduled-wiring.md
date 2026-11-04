# 09: scheduled wiring (project reports, checks file, retention, install via `kaizen-link`)

## Goal and why
Owner goal: the plugin's scheduled cycle runs packet outcomes and calibration, rules-lint, the drift check, shadow status, slow-test hooks and ledger measurement proposals, and records changes. The pieces exist as scripts after packets 01-07; this packet makes `kaizen-scheduled audit|review` run them, and makes `install-schedule --apply` install the scripts through `kaizen-link` instead of copying four files by hand.

## Context
- Repo: ~/github/highwayoflife/agent-kaizen. Python 3.9+ stdlib; read `AGENTS.md`. No personal paths or project names in tracked files. Confirm packets 01, 03, 06, 07a and 07b exist first (`ls scripts/kaizen-link scripts/rules-lint scripts/kaizen-project-report scripts/notes-ledger`; `python3 scripts/notes-ledger due --help`).
- `scripts/kaizen-scheduled`: `sibling(override, *names)` line ~525 finds sibling scripts next to this file (`HERE = Path(__file__).resolve().parent`, so symlinks resolve into the plugin); `_run_audit` ~800 runs token-audit and logs and today only READS `projects/index.json` (`_run_review` ~825 calls `discover(...)` and `write_index(...)`; on a fresh config dir the index does not exist, so the audit must do the same discovery and write before it generates project reports: reuse `discover(claude_home()/"projects", codex_home()/"sessions", read_index(audits))` then `write_index`); `report_path` ~818; `_run_review` ~825 loops due projects and runs `claude -p "/agent-kaizen:cycle <mode> <report>"` via `review_command` ~589; auto mode builds an allow list ~595-603 (token-audit + kaizen-backup only); `RETENTION_KINDS` ~615 with the `reports` kind (patterns relative to audits; read how "family" and "newest 5" work before adding patterns); `read_index` ~287 gives `{abs project path: key}`; `key(path)` ~163; `log()` ~173; `LOG_TO_STDERR`. Enrolled project = directory containing `docs/kaizen/`. Per-project report folder `<audits>/projects/<key>/`.
- `scripts/install-schedule`: docstring lines 11-13 say `--apply` "copies the runner, token-audit, kaizen-backup and pricing.json"; the copy block is at lines ~340-347 (`shutil.copy2(...)`, `AUDIT_NAME = "kaizen-token-audit"` at line 47, BIN at 46).
- New scripts and their CLIs (from earlier packets): `kaizen-link --check [--json]` (exit 1 on drift), `rules-lint [--repo DIR]...` (exit 1 on hits, last line `rules-lint: N stale-rule hit(s)`), `kaizen-project-report --project DIR --out FILE`, `notes-ledger due [--project DIR ...]` and `notes-ledger add ...`. Exit codes: `kaizen-link --check` and `rules-lint` exit 1 when they FIND something (their stdout is the finding and must be kept in the report); exit >= 2 or a crash is `unavailable: <reason>`. Treat exit 0 and 1 as success of the step for these two.
- Output contract (decided): global audit run writes `<audits>/checks-<yyyymmddThhmmssZ>.md` with `## Drift`, `## Stale rules`, `## Notes ledger: measurements due` (each section is the trimmed stdout of the step, at most 30 lines, or `unavailable: <reason>`), and for every enrolled project in the index that still exists writes `<audits>/projects/<key>/project-report-<ts>.md` via `kaizen-project-report`. `review` regenerates the due project's report right before launching Claude. `review` gains two flags (used by the end-to-end gate and for safe manual runs): `--propose-only` forces the cycle mode to `propose-only` whatever `scheduledAutonomy` says (and builds the command with the same restricted tools as propose mode), and `--force` treats the selected `--project-dir` projects as due (skips the activity gate, not the `enabled`/`schedule=off` checks). A failing step logs `step <name>: failed (...)` and never changes the audit/review exit code. Steps whose sibling script is missing are skipped silently. Env `KAIZEN_SKIP_CHECKS=1` skips all new steps (used for the timing comparison).
- Unattended permissions: in `auto` mode the allow list gains `Bash(python3 <HERE>/notes-ledger add:*)` and the `options.python` variant, only for `add` (never `set`; `due` is pre-computed by the runner). Append-only is enforced by deny rules too (review finding): when `notesLedger.csv`/`timeline` are configured, add `Edit(//<abs>)` and `Write(//<abs>)` deny rules for both resolved paths to the `--disallowedTools` list, built with the same fail-closed path check as `config_home_deny` (a path containing `,()*?[]\\` raises). A Bash redirect is not covered by deny rules; that known limit is already documented for `cp`/`touch` and stays (only the listed Bash commands are allowed).
- Superseded wording (rule): the sentence "copies the runner, token-audit, kaizen-backup and pricing" in `install-schedule`'s docstring and `docs/scheduling.md` is replaced. Append the regex `copies the runner, token-audit` (with a comment) to `scripts/rules-lint.patterns`, add a matching line to the fixture under `tests/fixtures/rules_lint/` and its test in `tests/test_rules_lint.py`, and make `python3 scripts/rules-lint --repo .` report 0 hits.

## Scope / do not touch
Edit `scripts/kaizen-scheduled` (audit/review steps, allow list, retention only), `scripts/install-schedule` (replace copy block and docstring), `docs/scheduling.md` (the `--apply` sentence and the reports/storage file list), `scripts/rules-lint.patterns` + its fixture/test line, `tests/test_schedule.py` (update expectations of the install output). Create `tests/test_schedule_steps.py`. Do not edit skills (packet 10) or README/CHANGELOG/version (packet 11).

`install-schedule --apply` new behaviour: run the sibling `kaizen-link --apply --mode auto --replace --only <list>` where the list is: kaizen-scheduled, kaizen-token-audit, token-audit, kaizen-backup, kaizen-pricing.json, pricing.json, kaizen-link, rules-lint, rules-lint.patterns, packet-report, kaizen-project-report, notes-ledger, usage-series, usage-compare (skip names that do not exist). Names in the global `localScripts` are skipped by `kaizen-link` itself. Print the plan first (run `kaizen-link` without `--apply` and show it), then apply with `--replace-prefixed` so only `kaizen-` names are ever renamed; a differing generically named file (for example another tool's `rules-lint`) is reported as DRIFT and left alone. Print what kaizen-link printed. Jobs keep calling `<bin>/kaizen-scheduled`. In copy mode (plugin under a plugin cache) jobs survive plugin moves as before. `--remove` unchanged.

## Acceptance criteria
1. With a temp config dir, temp project (`docs/kaizen/`, `out/packets.jsonl` fixture) in the index, and stub siblings (small scripts passed by overriding `HERE`-relative lookup or via env hooks you add for tests), `kaizen-scheduled audit` writes `checks-*.md` with the three sections and `projects/<key>/project-report-*.md`; one stub exiting 1 gives `unavailable:` text and the audit still exits 0.
2. `review` regenerates the project report before launching the (stub) claude command and still passes `/agent-kaizen:cycle <mode> <report>` unchanged.
3. `auto` allow list contains `notes-ledger add` and not `notes-ledger set`; `propose` list unchanged. Existing deny rules unchanged.
4. `housekeep` removes expired `checks-*.md` and `project-report-*.md` under the `reports` retention rule (add tests; 365 days, newest 5 kept per family).
5. `install-schedule --apply` into a temp config dir creates the managed names in `bin/` (links, or copies when the fake plugin root is under `/plugins/cache/`) and `kaizen-link --check` there exits 0; existing `tests/test_schedule.py` pass after updating message expectations.
6. `KAIZEN_SKIP_CHECKS=1` skips all new steps.
7. Fresh config dir with no `projects/index.json`: `kaizen-scheduled audit` discovers the enrolled temp project, writes the index, and writes its project report.
8. A stub `kaizen-link --check` that prints a DRIFT line and exits 1, and a stub `rules-lint` that prints hits and exits 1, show their stdout in the checks file (not `unavailable`); exit 2 shows `unavailable:`.
9. `review --propose-only --force --project-dir D` (stub claude) passes `/agent-kaizen:cycle propose-only <report>` and the propose-mode tool lists even when `scheduledAutonomy=auto`; `--force` skips the activity gate.
10. Auto-mode deny list contains `Edit(` and `Write(` rules for the configured ledger csv and timeline, and a ledger path containing `(` makes command building fail closed.
11. `install-schedule --apply` into a temp config dir: a pre-existing differing `kaizen-scheduled` is renamed `.replaced-<date>` and relinked; a pre-existing differing `rules-lint` is left alone and reported; `usage-series --help` works from the temp bin in copy mode.
12. `python3 scripts/rules-lint --repo .` prints 0 hits; full suite passes. (The scheduled-audit wall-time measurement runs in packet 13 on real data.)

## Verification
```
cd ~/github/highwayoflife/agent-kaizen
python3 -m unittest tests.test_schedule_steps tests.test_schedule tests.test_housekeep tests.test_rules_lint -v
python3 -m unittest discover -s tests
python3 scripts/kaizen-scheduled --help && python3 scripts/install-schedule --help
CLAUDE_CONFIG_DIR=$(mktemp -d) python3 scripts/rules-lint --repo .
```

## Working tree
Codex packets run in their own git worktree (`git worktree add ~/github/highwayoflife/agent-kaizen-wt-09 -b kz-09`, created by the orchestrator, after groups A-C are merged). Work only there.

## Reporting
Files changed, test counts, any step you could not wire and why. Do not commit or push. Stop and report if the retention "family" logic cannot take the new patterns without a redesign.

## Suggested agent / model / effort
codex-engineer, Sol, high (orchestrator decision: unattended permission allow and deny lists are security-sensitive). Risk: high (changes what an unattended job runs and its permissions; per-packet review before merge).

## Delta from the group A batch review (2026-11-04)
- `install-schedule` still installs with `shutil.copy2`. Once links exist, this raises `SameFileError` or overwrites the plugin source. Route every install through `kaizen-link` (`--replace-prefixed` for `kaizen-` names) and remove the direct copy path. Add a test with a pre-existing symlinked bin entry.
- `kaizen-link --bin DIR` alone still writes hooks into the real `<claude home>/hooks`. Pass `--hooks-dir` explicitly wherever `install-schedule` targets a non-default bin, and document this in docs/scheduling.md.
