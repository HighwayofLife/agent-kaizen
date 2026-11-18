# Context map (verified at commit 778f546)

Later runs re-verify only the lines they cite. Corrections are appended at the end.

## Repo rules and checks

- `AGENTS.md:8-13`: Python 3.9+, stdlib only; commands `python3 -m unittest discover -s tests`, `shellcheck -S warning hooks/*.sh`, `claude plugin validate .`. Rules: skills need quoted `description`, `disable-model-invocation: true`, README table row; no personal paths (tests/test_repo.py scans every tracked file, including docs/plans/).
- `.github/workflows/ci.yml:46-50`: every tracked executable under `scripts/` (not `.json .md .patterns .py`, not `preambles/`, `prompts/`) must exit 0 on `--help`. New scripts: shebang `#!/usr/bin/env python3`, executable bit committed.
- `.github/workflows/ci.yml:63-80`: the version/changelog gate runs only on pull requests.
- `tests/test_repo.py:35` manifest test needs `## <plugin version>` in CHANGELOG.md; `:70` README must list every skill as `` `/agent-kaizen:<name>` ``; `:76` privacy scan.
- Verify form: `python3 -m unittest discover -s tests -p 'test_X.py' -v`. Run on the current tree and green: test_packet_report, test_schedule_steps, test_hooks, test_dispatch_guards, test_process_rules, test_repo, test_config_keys, test_install_schedule, test_kaizen_link, test_rules_lint, test_session_notes. `python3 -m unittest tests.test_schedule_steps` fails (tests/ has no `__init__.py`; the module imports `test_scripts` bare); `tests.test_packet_report`, `tests.test_hooks`, `tests.test_dispatch_guards`, `tests.test_process_rules`, `tests.test_repo` also work.
- Test style: subprocess with `sys.executable`, `tempfile`, `unittest`; see `tests/test_packet_report.py:14-17`. Stub helpers (`StubCase`, `executable`, `write`, `FAKE_CODEX`) are in `tests/test_scripts.py:16-70`.
- No `tools/codemap`; `tools/ci-local` is added by a separate change (precondition of packet 12).

## Ledger

- Writer: `skills/start/SKILL.md:25-27` (six columns: date, change, why (which audit finding), expected effect, measured effect, keep/revert).
- Other writers: `docs/autonomy.md:81` (step 5 "Ledger row"), `skills/models/SKILL.md:46`, `skills/roster/SKILL.md:101`, `skills/cycle/SKILL.md:37` (also writes the notes-ledger CSV via `notes-ledger add`; the CSV is separate and stays). Other skills say "add a ledger row" generically and follow `docs/autonomy.md`.
- Readers by header name: `scripts/kaizen-project-report:57-90` (`date`, `measured effect`, `change`; pending = exactly `pending`), `hooks/session-notes.sh:47-77` (same columns, six-day rule). `scripts/notes-ledger:315` is the separate CSV.

## packet-report

- `scripts/packet-report`: docstring keys :3-13; `normalize_model` :43; `summarize` :49 (fixed/audited sets :52-55, groups :63-93, histories :96-115); `render` :123-157 (sections: `Packet outcomes` first, `Calibration proposals` last, :151); `DEFAULTS` :159-161 (`lines=0`); `read_rows` :164-205 (`row = dict(DEFAULTS, **row)` :175, validation :176-190); `main` :207.
- No `tokens_in`, `tokens_out`, `cost` or `merge_sha` use anywhere in the script. `docs/outcome-log.md:7-31` lists them (tokens, no cost, no severity).
- `scripts/kaizen-project-report:39-52` runs packet-report with `--markdown` and splits at `lines.index('Calibration proposals')`: new sections go before that heading.
- `tests/test_packet_report.py:24` asserts the exact key set of the JSON (`assertEqual(set(data), {...})`); additive keys need that updated. Fixture `tests/fixtures/packets.jsonl` (17 rows).
- Stale wording: `scripts/README.md:545` (normalised against the ladder), `skills/cycle/SKILL.md:24` (up or down one rung only), `:26` (last models audit or ledger entry).

## Scheduler and state

- `scripts/kaizen-scheduled`: `SCHEMA` :114-132 (kinds `int` with `minimum`, `enum`, `strings`, ...; `valid_value` :190), `project_config_path` :161, `effective` :227, `key` :263, `Project` :540-545 (`folder = audits/projects/<key>`), `discover` :557, `read_state/write_state` :697-722, `parse_time` :686 (`Z` to `+00:00`, requires tzinfo), `sibling` :901, `run_step` :1432 (30 lines of stdout, `success` tuple), `run_checks` :1482-1507 (sections `Drift`, `Stale rules`, `Notes ledger: measurements due`; `project_args` :1489), `write_config` :2026 (tmp + replace), `canonical_project` :2064, `config_lock` :2077 (flock on `<name>.lock`), argparse `main` :2111 (`config show|set --for`).
- Retention `RETENTION_KINDS` :1205: `*.noticed-*` markers expire after 30 days; `checks.json` is not matched by any pattern.
- `hooks/audit-notice.sh`: root = nearest `docs/kaizen` ancestor :12-17; key via `projects/index.json` walk :19-28; early exits at :30, :32, :40, :67 and :69; marker `${latest%.md}.noticed-$(date +%F)` :68; JSON via `jq -n` :73. Hooks do not use `CLAUDE_PLUGIN_ROOT` (they run via `bash "${CLAUDE_PLUGIN_ROOT}/hooks/audit-notice.sh"`, `hooks/hooks.json:9`); `hooks/session-notes.sh:20-37` has the timeout fallback pattern (`timeout`, `gtimeout`, or sleep-and-kill).
- `scripts/install-schedule:50-56` `MANAGED_NAMES`, filter :425; `scripts/kaizen-link:28-39` `SCRIPTS`; tests `tests/test_kaizen_link.py:120-160` (copy mode into a fake plugin cache), `tests/test_install_schedule.py`.
- `tests/test_schedule_steps.py:60-100` stubs sibling scripts in a temp scripts dir and checks `checks-*.md` text; add new step tests there. `tests/test_hooks.py:346-410` audit-notice tests (`run` helper :23; env `AUDIT_DIR`, `CLAUDE_CONFIG_DIR`).
- `tests/test_config_keys.py:11-17` default keys list, `:41-60` round-trip and invalid values.

## Dispatch

- `scripts/codex-dispatch`: `arguments()` :36-57 (flags, `--resume`, `-o`, `brief`), `reason_guard` :245 (a model such as Sol needs a standalone `Sol reason:` line outside code fences), `main` :266 (cwd check :268-271, brief read and guard :272-282). Tests: `tests/test_dispatch_guards.py` (class `DispatchGuardTests(StubCase)`), helper `dispatch()` `tests/test_scripts.py:78`, stub codex `FAKE_CODEX` :17-35.

## Other

- `docs/outcome-log.md:33-37`: single `os.write` on an `O_APPEND` descriptor; `scripts/kaizen-scheduled:1080` uses O_APPEND for the notes lock.
- `templates/plan/briefs/01-example.md`: headings `Goal and why`, `Code locations`, `What is known`, `Scope`, `Acceptance criteria`, `Verify`, `Report`.
- `README.md:195-213` skills table; `README.md:234-238` repo tree listing scripts.
- `CHANGELOG.md:5` first heading `## 0.9.1 (2026-11-10)`; plugin version 0.9.1; `.claude-plugin/marketplace.json` has no version field.

## Discrepancies found in the input

- The first plan put `checks.json` in `docs/kaizen/`; moved to `<audits>/projects/<key>/checks.json` (canonical per-machine state).
- `kaizen-scheduled` per-project state is not in the project tree, so `experiment-check --checks` takes `--state-file`.
- `cycle/SKILL.md` calibration text is at :24, not :25; check-date text at :25-29.
- Packet-report never read token fields; "0 vs missing" is new behaviour, not a bug fix.
