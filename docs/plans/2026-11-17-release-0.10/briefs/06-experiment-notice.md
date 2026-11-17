# 06: Experiment notices in the schedule and at session start, plus the `pendingDays` key

## Goal and why

Experiments that are past their review date, or pending for more than N days, must be noticed without anyone remembering to look. Wire the read-only `experiment-check` (packet 02) into the scheduled checks report and into the registered SessionStart hook, and make `pendingDays` a real configuration key. The hook is registered for every user, so it must keep emitting one valid JSON object and exiting 0 on every path.

## Context

- agent-kaizen is a Claude Code plugin; scripts are stdlib-only Python 3.9, hooks are bash checked with `shellcheck -S warning hooks/*.sh`. Read `AGENTS.md` (Rules).
- `scripts/experiment-check` (packet 02, already merged) interface: `--project DIR [--pending-days N] [--today YYYY-MM-DD] [--json]`; first stdout line `experiment-check: N finding(s)`; exit 0 no findings, 1 findings, 2 usage or unreadable ledger (message on stderr). It reads `pendingDays` itself from the project's `docs/kaizen/config.json` (external), then the global `agent-kaizen.json`, then defaults to 10, so the schedule and the hook need not pass it.
- Scheduler: `scripts/kaizen-scheduled` `run_step` :1432-1455 (returns None when the sibling script is absent, `"unavailable: ..."` on failure, the first 30 stdout lines otherwise; `success` is the tuple of accepted exit codes), `run_checks` :1482-1507 (sections `Drift`, `Stale rules`, `Notes ledger: measurements due`; `project_args` built at :1489; the whole function returns early when `KAIZEN_SKIP_CHECKS=1`). `SCHEMA` :114-132 (kind `int` needs `minimum`; `valid_value` :190; `effective` :227 ignores unknown keys). `config set KEY=VALUE` parses kind `int` at about :2196-2215.
- Hook: `hooks/audit-notice.sh` (registered in `hooks/hooks.json:9`). Early exits that must stay: jq missing :6, bad cwd :10, not enrolled :30, `enabled` false :32, `schedule` off :40. Audit part: :42-67 find `latest`; exit at :67 when there is no unreviewed audit; marker `${latest%.md}.noticed-$(date +%F)` :68-69; message :70-72; JSON through `jq -n` :73-74. The enrolled root is the nearest ancestor with `docs/kaizen` (external) (:12-17). Hooks do not use `CLAUDE_PLUGIN_ROOT` today; derive the plugin root as `${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}`. Timeout fallback pattern to copy: `hooks/session-notes.sh:20-37` (`timeout`, `gtimeout`, or background sleep-and-kill).
- Tests: `tests/test_schedule_steps.py:60-100` (a temp scripts dir holds the runner copy and stubs of `kaizen-link`, `rules-lint`, `notes-ledger`; `check_text()` reads `checks-*.md`); `tests/test_hooks.py:346-410` (audit-notice tests; `run(hook, payload, env)` at :21 returns the parsed JSON or None; `bare_path()` :28 builds a PATH with only named tools). `tests/test_config_keys.py:41-60` (round trip and invalid values).
- Retention (`kaizen-scheduled:1205-1210`) deletes `*.noticed-*` markers after 30 days, so a marker named `experiments-<n>.noticed-<date>` in the audits directory is cleaned up automatically.
- Decisions already made (orchestrator): Terra `high`; the cycle skill text about experiments is packet 09's, not this packet's. This packet does not edit CHANGELOG.md or README.md; report the new env var so packet 12 can add its README row.

## Scope / do not touch

Creates: nothing.
Edit only: `scripts/kaizen-scheduled` (the `SCHEMA` entry and the `run_checks` step only), `hooks/audit-notice.sh`, `tests/test_schedule_steps.py`, `tests/test_hooks.py`, `tests/test_config_keys.py`, `docs/scheduling.md` (one config-table row near :80-92 and one sentence where the checks report is described).
Do not touch `scripts/experiment-check`, `skills/`, `hooks/hooks.json`, `hooks/session-notes.sh`, `README.md`, `CHANGELOG.md`.

## Steps

1. `kaizen-scheduled`: add `"pendingDays": {"kind": "int", "default": 10, "minimum": 1}` to `SCHEMA` (project-overridable, not global-only). In `run_checks`, after the existing sections, for each project run `run_step("experiment-check", options, ["--project", str(project.canonical)], (0, 1))`. Add a section `## Experiments: <canonical path>` when the output is not None and does not start with `experiment-check: 0 finding`; an `unavailable: ...` result is included, so failures stay visible; the per-project path keeps identity; the early return for `KAIZEN_SKIP_CHECKS=1` is unchanged.
2. `hooks/audit-notice.sh`: keep the audit logic, but where it exits at :67 and :69 set an `audit_msg` variable and continue instead. Add the experiment notice: only when `$root` is non-empty, `python3` is on PATH and `<plugin root>/scripts/experiment-check` exists; once per day per project through a marker `$dir/experiments-<cksum of $root>.noticed-$(date +%F)` created only after a message is emitted (`mkdir -p "$dir"` first, failures ignored); run `python3 <script> --project "$root"` bounded by `${KAIZEN_NOTICE_TIMEOUT:-10}` seconds; only exit status 1 yields a message (statuses 0, 2, timeout and anything else stay silent); the message is `Experiments need attention in this project (docs/kaizen/LEDGER.md):` plus at most 12 output lines plus `When there is a pause, run /agent-kaizen:review.`. Join the audit and experiment messages with a blank line and emit one `jq -n` object; if both are empty exit 0 with no output. Every path exits 0.
3. Tests, then `docs/scheduling.md`.

## Acceptance criteria

1. `pendingDays` appears in `kaizen-scheduled config show`; `config set pendingDays=5` and `config set --for DIR pendingDays=5` persist (global and project file); `0`, `-1`, `x`, `true` are rejected or ignored (follow the invalid-value pattern at `tests/test_config_keys.py:41-60`).
2. Scheduled: a stub `experiment-check` printing findings gives a `## Experiments: <project path>` section in `checks-*.md`; the stub receives `--project <canonical>`; output `experiment-check: 0 finding(s)` adds no section; exit 2 gives `unavailable: exit 2` in the report; two projects give two sections each carrying its own path; with `KAIZEN_SKIP_CHECKS=1` no checks file is written; with no `experiment-check` sibling present the other sections are unchanged.
3. Hook: with no audit and a ledger with a past-review row (real `experiment-check`), output is one JSON object containing the experiment text; with both an unreviewed audit and findings the single object contains both; a second call the same day gives no experiment text while the audit notice keeps its own marker rules; `schedule=off` and `"enabled": false` give no output; project with no findings gives no output; exit 2 (malformed ledger), missing script (`CLAUDE_PLUGIN_ROOT` pointing at an empty directory), missing `python3` (use `bare_path`) and a hung checker (stub that sleeps, `KAIZEN_NOTICE_TIMEOUT=1`, wall time under about 5 s) all exit 0 with valid or empty output and the audit notice still emitted when one exists. Existing audit-notice tests stay green unchanged.
4. `docs/scheduling.md` documents the `pendingDays` row, the experiments section of the checks report, and the hook notice with its once-a-day marker and `KAIZEN_NOTICE_TIMEOUT`.
5. `shellcheck -S warning hooks/*.sh` is clean.

## Verification

```sh
python3 -m unittest discover -s tests -p 'test_schedule_steps.py' -v
python3 -m unittest discover -s tests -p 'test_hooks.py' -v
python3 -m unittest discover -s tests -p 'test_config_keys.py' -v
python3 -m unittest discover -s tests -p 'test_session_notes.py'
shellcheck -S warning hooks/*.sh
```

## Reporting

At most 20 lines: files changed, test results, new env var name and default, limitations, one proposed CHANGELOG bullet (do not edit CHANGELOG.md). Do not commit or push. Stop and report if `run_checks` or the hook differ materially from the lines above or `scripts/experiment-check` does not match the interface. If the packet exceeds about 400 changed lines, stop and report.

## Suggested agent / model / effort and risk

`codex-engineer` / Terra `high` (a SessionStart hook that must always succeed). Risk: **normal**. Estimated size: 300 lines. Batch reviewer regression modules: `test_schedule_steps`, `test_hooks`, `test_config_keys`, `test_session_notes`.
