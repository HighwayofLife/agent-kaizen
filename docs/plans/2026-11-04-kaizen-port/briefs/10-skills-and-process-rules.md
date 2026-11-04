# 10: skills, auditor agent and templates: the new workflow and the process rules

## Goal and why
Other users should get the same process as the owner: every new self-improvement tool or process goes into the plugin and runs on its schedule, each applied change is recorded and re-measured, and the planning rules from 2026-11-04 are part of the planning guidance. The skills and the `kaizen-auditor` agent must also know the new outputs of the scheduled run.

## Context
- Repo: ~/github/highwayoflife/agent-kaizen. Markdown only plus one test. Read `AGENTS.md`: skill frontmatter `name` = folder, quoted `description`, `disable-model-invocation: true`; every skill is in the README table (do not add skills); references written as the dollar-brace form of `CLAUDE_PLUGIN_ROOT` followed by a path must point at files that exist (tests/test_repo.py `test_plugin_root_references_exist`); this brief writes that prefix as `<PLUGIN_ROOT>`: in the files you edit, write it in the dollar-brace form like the existing skills do; no personal paths/names; writing style: plain, short sentences, no marketing; keep each SKILL.md short (cycle is 36 lines today).
- Scripts that now exist (earlier packets): `scripts/kaizen-link` (`--check` drift report, `--apply`), `scripts/packet-report`, `scripts/rules-lint`, `scripts/kaizen-project-report`, `scripts/notes-ledger` (`add`, `due`, `set`), `docs/outcome-log.md` (contract). Scheduled runs (packet 09) write `<audits>/checks-<ts>.md` (sections Drift, Stale rules, Notes ledger: measurements due) and `<audits>/projects/<key>/project-report-<ts>.md` (outcomes, calibration proposals, shadow reviews, slow tests, speed, pending project-ledger rows). Config keys (global only): `projectCommands`, `notesLedger`, `calibrationLadder`, `rulesLintFiles`, `localScripts`.
- The rules to add (owner's wording, 2026-11-04):
  1. Kaizen rule: every new self-improvement tool or process (audit section, report, lint, calibration, measurement) is added to the agent-kaizen plugin so it runs on the plugin's schedule. Each change gets a row in the notes ledger (what changed, why, how it will be measured) and is re-measured later.
  2. Planning rule A: a packet meant to speed up development or cut tokens or cost names one before/after measurement command in its acceptance criteria (a report script, a benchmark, or `--explain`); the baseline is taken before the change; unit tests alone do not show the saving.
  3. Planning rule B: a plan that adds or changes tooling ends with a packet that runs the new tools end to end once on real input and pastes the trimmed output into its plan row; the plan is not done until that run is clean.
  4. Planning rule C: a packet that changes a contract (a flag, trailer, file format or rule wording) adds the old wording to the stale list of `rules-lint` (and its test fixture) in the same packet, and fixes every hit.

## Edits (all in these files)
- `skills/cycle/SKILL.md`: step 1 also reads the newest `checks-*.md` (global audits folder) and `project-report-*.md` (this project's report folder) when present; new step after Review: "Outcomes and checks": calibration proposals (up or down one rung, from `project-report`; proposals only), `DRIFT`/`BROKEN` lines (propose `kaizen-link --apply`, or add the name to `localScripts` if the difference is intended), stale-rule hits (fix the wording or the pattern), measurement proposals from `notes-ledger due` (never run `notes-ledger set` without the owner's OK); step "Record": after each applied change run `python3 <PLUGIN_ROOT>/scripts/notes-ledger add ...` when `notesLedger` is configured (exit 3 means not configured: skip) in addition to the project ledger row; add the Kaizen rule (1) as a short paragraph under "Task". Keep propose-only behaviour unchanged.
- `skills/audit/SKILL.md`: add the new report files and say where each section comes from (token-audit report; project report; checks file).
- `skills/review/SKILL.md`: step 1 may use `notes-ledger due` and the project report as measurement sources; keep "proposals only; the owner approves".
- `skills/planning/SKILL.md`: add rules A, B, C as numbered requirements for plan packets (after the existing numbered list), and require plans to carry a final end-to-end packet when tooling changes.
- `skills/start/SKILL.md`: add a step: tell the user how a project feeds the audit (enrolment = `docs/kaizen/`; optional outcome log, link to `<PLUGIN_ROOT>/docs/outcome-log.md`), and offer `python3 <PLUGIN_ROOT>/scripts/kaizen-link --check` then, after OK and with a `kaizen-backup`, `--apply` so `<Claude config dir>/bin` links to the plugin (copy mode when the plugin is in a plugin cache).
- `skills/schedule/SKILL.md`: say what the scheduled audit and review now also produce (the two file types) and that `install-schedule --apply` installs scripts through `kaizen-link`.
- `skills/test-loop/SKILL.md`: one paragraph: a slow-test report command can be named in `projectCommands.<project>.slowTests` in the global config; it appears in the project report.
- `agents/kaizen-auditor.md`: it now reads the checks file and the project report first (prefer precomputed files; run `kaizen-project-report`, `kaizen-link --check`, `rules-lint`, `notes-ledger due` only when a file is missing; all are read-only except as noted by the scripts), includes calibration and drift in its ranked proposals, still returns at most 20 lines and never changes configuration. Tools list unchanged.
- `templates/global-CLAUDE.md`: add the Kaizen rule (1) as one numbered line in the style of its neighbours.
- `templates/agents/planner.md` and `templates/agent-context/planning.md`: add rules A, B, C in one or two lines each.

## Scope / do not touch
Only the files above plus a new `tests/test_process_rules.py`, which asserts that each rule's key phrase appears: Kaizen rule in `skills/cycle/SKILL.md` and `templates/global-CLAUDE.md`; rules A/B/C in `skills/planning/SKILL.md`, `templates/agents/planner.md` or `templates/agent-context/planning.md`. Do not edit scripts, README, CHANGELOG, version.

## Acceptance criteria
1. All edits above exist; each rule appears once per file in plain wording and the test passes.
2. `python3 -m unittest tests.test_repo tests.test_process_rules -v` passes (frontmatter, README table, plugin-root references).
3. `claude plugin validate .` passes.
4. `python3 scripts/rules-lint --repo .` (with `CLAUDE_CONFIG_DIR` set to an empty temp dir) prints 0 hits.
5. No SKILL.md grows by more than 25 lines (cycle may grow by up to 30).

## Verification
```
cd ~/github/highwayoflife/agent-kaizen
python3 -m unittest tests.test_repo tests.test_process_rules -v
python3 -m unittest discover -s tests
claude plugin validate .
CLAUDE_CONFIG_DIR=$(mktemp -d) python3 scripts/rules-lint --repo .
wc -l skills/*/SKILL.md | sort -n | tail -5
```

## Working tree
Codex packets run in their own git worktree (`git worktree add ~/github/highwayoflife/agent-kaizen-wt-10 -b kz-10`, created by the orchestrator). Work only there and run the commands from that directory.

## Reporting
Files changed, line counts before/after, test counts. Do not commit or push. Stop and report if a script name used in a skill does not exist.

## Suggested agent / model / effort
codex-engineer, Terra, medium. Risk: normal.
