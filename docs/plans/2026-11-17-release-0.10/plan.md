# Agent Kaizen 0.10.0 feature plan

## Summary

Add value-stream events and a flow report, an experiment register in the project ledger, honest packet calibration, brief preflight, and due-check notices. Twelve packets in four waves, merged into one unpublished integration branch (`release-0.10`) and released once. No implementation has been run; every `file:line` below was checked against the tree at commit 778f546.

## Goal / non-goals

Goal: any enrolled project gets the five features. New scripts make no network calls and use Python 3.9-compatible standard library only; every new script answers `--help` (CI checks this).

Non-goals: changes to `.github/workflows/ci.yml`, `tools/ci-local`, `scripts/usage-db` or `docs/examples/` (a separate change owns them); automatic wiring into a user's orchestrator; running metric commands; recovering past check dates.

## Context

Details and verified line ranges are in `context.md`. The facts the plan rests on:

- `scripts/packet-report` reads no token or cost field today and defaults a missing `lines` to 0 (`DEFAULTS` at :159, merged at :175); model names are normalised only against the calibration ladder (`normalize_model` :43). `kaizen-project-report` splits packet-report's text at the line `Calibration proposals` (:50-52), so new report sections must come before it.
- The project ledger `docs/kaizen/LEDGER.md` is created by `skills/start/SKILL.md:25` with six columns (`date | change | why (which audit finding) | expected effect | measured effect | keep/revert`). Both existing parsers (`scripts/kaizen-project-report:57-90`, `hooks/session-notes.sh:47-77`) find columns by header name, so appended columns are safe.
- Per-project machine state lives in `<audits>/projects/<key>/` (`state.json`, `kaizen-scheduled:698-722`), with `key(canonical_project)`; `audit-notice.sh:19-28` resolves the same key through `projects/index.json` for worktrees. `canonical_project()` is at `kaizen-scheduled:2064`, `config_lock()` at :2077.
- Scheduled checks are built in `run_checks` (`kaizen-scheduled:1482-1507`) from `run_step` (:1432), which returns None when a sibling script is absent. Installed copies only get scripts named in `scripts/install-schedule:50-56` (`MANAGED_NAMES`, filter at :425) and `scripts/kaizen-link:28-39` (`SCRIPTS`).
- No `tools/codemap` and no `tools/ci-local` in this checkout.

## Approach

- Timing uses an append-only event file (`out/packet-events.jsonl`), never edits to outcome rows. `docs/flow.md` freezes the schema and default path in packet 01; the report (05) and skill (10) cite it.
- The experiment register reuses the ledger: two appended header columns (`metric command`, `review date`), found by name. Old six-column tables and old rows stay valid and are reported as "legacy, no metadata", never as errors. One read-only checker (`experiment-check`) serves the schedule and the SessionStart hook.
- Last-completed dates for the model, roster and whats-new checks live in a per-machine file `<audits>/projects/<key>/checks.json`, beside the existing `state.json`, resolved with the existing canonical-project and key rules. Only `kaizen-scheduled checks record` writes it (lock, write-to-temp plus `os.replace`, `.bak` of the previous file). This replaces the earlier idea of a tracked `docs/kaizen/checks.json`: a tracked file would be per-worktree, cross-machine and conflict-prone.
- `pendingDays` (default 10) is a config key (project `docs/kaizen/config.json`, then global `agent-kaizen.json`); `--pending-days` overrides it. `experiment-check` reads the files itself, so schedule, hook and CLI all honour it.
- Calibration HOLD needs complete evidence; anything unknown keeps the old rule (UP).
- Rejected: a second experiment ledger or CSV; executing metric commands; inferring completion from mtimes; shell-side JSON editing of `checks.json`; integrating into the user's orchestrator.

## Decisions needed

None blocking. These reversible choices were made by the orchestrator or the planner and are listed so a reviewer can object:

1. No Sol packets: 01, 05, 06 run on Terra `high`, the rest on Terra `medium`.
2. `kaizen-scheduled checks record` is bookkeeping, allowed in every interactive mode (including `propose`) after a check actually completes, never in a scheduled or propose-only run. It writes no `kaizen-backup` manifest (it is not a project change; `.bak` is its rollback). Packet 09 documents this in `docs/autonomy.md`.
3. The due-check nag fires for every enrolled project until its first recorded completion (no state exists anywhere today). The release notes say so.

## Assumptions

- Local-filesystem O_APPEND with one `os.write` per event is the supported writer; network filesystems are not promised. A line is capped at 4096 bytes so one write stays atomic in practice.
- Wait = `queued` + `slot-wait`; every other non-terminal state is touch time. Documented in `docs/flow.md` (packet 05 adds the section).
- A row with `merge_sha` is landed. Missing token, cost, line and severity fields stay unknown; `tokens_in` of 0 is ambiguous, not missing and not known.
- Thresholds are configurable defaults, not a claim about optimal routing.
- `experiment-check --checks` adds a section to the same report; without it the output is unchanged.
- Exit codes for new checkers: 0 nothing to report, 1 findings, 2 usage or unreadable input (matches `kaizen-link --check` and `rules-lint`, run with `success=(0, 1)`).
- Briefs declare files they create on a `Creates:` line in the Scope section, or mark an inline path ` (new)`; a path that exists only in a user's project or at run time is marked ` (external)`. A declaration at any occurrence waives that path in the whole brief. Packet 03's lint also only checks inline-code spans that look like repo paths (first segment is an existing directory, or the last segment has an extension). Packet 03 adds the `Creates:` line to `templates/plan/briefs/01-example.md`. This plan's own briefs follow the convention, and packet 12 lints one of them as part of the smoke run.
- Ledger metric commands are written in backticks; a literal pipe inside a cell is written `\|`.

## Packets

Size is estimated changed lines including tests. "Verify" is the one primary command; each brief lists the regression modules to run as well. The `unittest discover` form is used everywhere because most test modules import siblings bare (`from test_scripts import ...`), so `python3 -m unittest tests.<module>` fails for them; the discover form was run against the current tree for every existing module named here and passes.

| ID | Packet | Depends | Wave | Agent / model / effort | Risk | Size (est. lines) | Primary verify |
|---|---|---|---|---|---|---|---|
| 01 | [Flow event writer](briefs/01-flow-event.md) | none | A | codex-engineer / Terra high | high | 300 | `python3 -m unittest discover -s tests -p 'test_packet_event.py' -v` |
| 02 | [Experiment checker and ledger columns](briefs/02-experiment-check.md) | none | A | codex-engineer / Terra medium | normal | 420, split trigger | `python3 -m unittest discover -s tests -p 'test_experiment_check.py' -v` |
| 03 | [Brief lint](briefs/03-brief-lint.md) | none | A | codex-engineer / Terra medium | normal | 400, split trigger | `python3 -m unittest discover -s tests -p 'test_brief_lint.py' -v` |
| 04 | [Packet data quality](briefs/04-packet-quality.md) | none | A | codex-engineer / Terra medium | normal | 350 | `python3 -m unittest discover -s tests -p 'test_packet_report.py' -v` |
| 05 | [Flow report](briefs/05-flow-report.md) | 01 | B | codex-engineer / Terra high | normal | 400, split trigger | `python3 -m unittest discover -s tests -p 'test_flow_report.py' -v` |
| 06 | [Experiment notices: schedule, hook, config key](briefs/06-experiment-notice.md) | 02 | B | codex-engineer / Terra high | normal | 300 | `python3 -m unittest discover -s tests -p 'test_schedule_steps.py' -v` |
| 07 | [Opt-in dispatch preflight](briefs/07-dispatch-preflight.md) | 03 | B | codex-engineer / Terra medium | normal | 150 | `python3 -m unittest discover -s tests -p 'test_dispatch_guards.py' -v` |
| 08 | [Review economics and calibration HOLD](briefs/08-review-economics.md) | 04 | B | codex-engineer / Terra medium | normal | 380 | `python3 -m unittest discover -s tests -p 'test_packet_report.py' -v` |
| 09 | [Due checks: report, record, notices](briefs/09-due-checks.md) | 02, 06 | C | codex-engineer / Terra medium | normal | 480, declared split | `python3 -m unittest discover -s tests -p 'test_experiment_check.py' -v` |
| 10 | [Flow skill and README row](briefs/10-flow-skill.md) | 01, 05 | C | codex-engineer / Terra medium | low | 120 | `python3 -m unittest discover -s tests -p 'test_flow_skill.py' -v` |
| 11 | [Register new scripts](briefs/11-register-scripts.md) | 01, 02, 03, 05 | C | codex-engineer / Terra medium | normal | 250 | `python3 -m unittest discover -s tests -p 'test_kaizen_link.py' -v` |
| 12 | [Release 0.10.0 and end-to-end gate](briefs/12-release.md) | 01 to 11 | D | codex-engineer / Terra medium | normal | 150 | `python3 -m unittest discover -s tests -v` |

Three of twelve packets use Terra `high` (01 concurrency, 05 ordering and WIP invariants, 06 a session hook that must always succeed). No packet uses Sol or `haiku-engineer`: none is a pure data-row change.

Risk: 01 is `high` (concurrency contract), reviewed before merge and checked by the concurrency test in its brief (N subprocesses appending, assert line count and that every line is valid JSON). The others get batch review per wave. A final audit covers the landed range.

Regression modules for batch reviewers: A: `test_packet_report`, `test_session_notes`, `test_project_report`, `test_rules_lint`, `test_repo`. B: `test_schedule_steps`, `test_hooks`, `test_config_keys`, `test_dispatch_guards`, `test_packet_report`, `test_project_report`. C: `test_kaizen_link`, `test_install_schedule`, `test_schedule_steps`, `test_hooks`, `test_process_rules`, `test_repo`.

### Integration

All packets merge into one unpublished branch `release-0.10`, created from `main` after the separate CI change (which adds `tools/ci-local` and a `## Unreleased` heading with a usage-db fix line) has landed. The orchestrator rebases or recreates the branch if the CI change lands later. Nothing is pushed or opened as a PR until packet 12 is done. The single release PR (skill, README row, version bump, changelog) goes from that branch; the orchestrator merges and tags.

The repo's version gate runs only on pull requests (`.github/workflows/ci.yml`, job `version`), so intermediate merges to the integration branch are not gated. A full-suite run (`python3 -m unittest discover -s tests`) is valid at every wave boundary: the only repo test tied to the version is `tests/test_repo.py` (`## <version>` must exist in CHANGELOG.md, unchanged until 12), and the README skill-list test is satisfied by packet 10's own README row.

### Waves and files each packet owns

Each packet branches from the tip of `release-0.10` at its wave start.

- **A** (01, 02, 03, 04; disjoint):
  - 01: `scripts/packet-event`, `tests/test_packet_event.py`, `docs/flow.md` (all new).
  - 02: `scripts/experiment-check` and `tests/test_experiment_check.py` (new); `tests/test_session_notes.py`, `tests/test_project_report.py` (one test each); `skills/start/SKILL.md`, `skills/models/SKILL.md`, `skills/roster/SKILL.md`; `skills/cycle/SKILL.md` (the ledger-row step at :37 only); `docs/autonomy.md` (the ledger-row step at :81 only).
  - 03: `scripts/brief-lint`, `tests/test_brief_lint.py` (new); `templates/plan/briefs/01-example.md`.
  - 04: `scripts/packet-report`, `tests/test_packet_report.py`, `docs/outcome-log.md`, `scripts/README.md` (packet-report section), `scripts/rules-lint.patterns`, `tests/test_rules_lint.py`.
- **B** (05, 06, 07, 08; disjoint):
  - 05: `scripts/flow-report`, `tests/test_flow_report.py` (new); `docs/flow.md` (append a `## Report` section; the schema section is frozen).
  - 06: `scripts/kaizen-scheduled` (SCHEMA key, `run_checks` step), `hooks/audit-notice.sh`, `tests/test_schedule_steps.py`, `tests/test_hooks.py`, `tests/test_config_keys.py`, `docs/scheduling.md` (config table row).
  - 07: `scripts/codex-dispatch`, `tests/test_dispatch_guards.py`.
  - 08: `scripts/packet-report`, `tests/test_packet_report.py`, `tests/test_project_report.py`, `docs/outcome-log.md`, `scripts/README.md` (packet-report section), `skills/cycle/SKILL.md` (:24 only), `scripts/rules-lint.patterns`, `tests/test_rules_lint.py`.
- **C** (09, 10, 11; disjoint):
  - 09: `scripts/experiment-check`, `tests/test_experiment_check.py`, `scripts/kaizen-scheduled` (`checks` verbs, step arguments), `hooks/audit-notice.sh`, `tests/test_schedule_steps.py`, `tests/test_hooks.py`, `tests/test_checks_record.py` (new), `skills/models/SKILL.md`, `skills/roster/SKILL.md`, `skills/whats-new/SKILL.md`, `skills/cycle/SKILL.md`, `docs/autonomy.md`, `docs/scheduling.md`, `scripts/rules-lint.patterns`, `tests/test_rules_lint.py`.
  - 10: `skills/flow/SKILL.md`, `tests/test_flow_skill.py` (new); `README.md` (one skill-table row).
  - 11: `scripts/install-schedule`, `scripts/kaizen-link`, `scripts/README.md`, `tests/test_kaizen_link.py`, `tests/test_schedule.py` (the installed-name tuple), `tests/test_install_schedule.py` (only if needed).
- **D** (12): `.claude-plugin/plugin.json`, `CHANGELOG.md`, `README.md`, this plan's Results section.

Collisions to watch: `scripts/rules-lint.patterns` and `tests/test_rules_lint.py` are edited by 04 (A), 08 (B) and 09 (C), never in the same wave. `scripts/README.md` by 04 and 08 (packet-report section), then 11. `skills/cycle/SKILL.md` by 02 (:37), 08 (:24), 09 (:25-29), one per wave. CHANGELOG.md by 12 only.

### CHANGELOG ownership

Packets 01 to 11 never edit CHANGELOG.md. Each puts one proposed bullet (under 40 words, plain, naming the script or flag) in its final report. The orchestrator pastes them into `docs/plans/2026-11-17-release-0.10/changelog-bullets.md`, which packet 12 reads. Packet 12 writes the `## 0.10.0 (2026-11-17)` entry from those bullets and folds the `## Unreleased` section the CI change added into it.

### Script registration

One owner: packet 11 adds `packet-event`, `flow-report`, `experiment-check` and `brief-lint` to `MANAGED_NAMES` (`scripts/install-schedule:50-56`), `SCRIPTS` (`scripts/kaizen-link:28-39`) and `scripts/README.md`, with a test that installs into a temp directory and finds each. No other packet edits those lists. No scheduled step needs registration to be testable earlier: the scheduler tests run from the repo `scripts/` folder, where `sibling()` finds the new checker without it.

### Stale wording (`rules-lint` list; rule 8 at `skills/planning/SKILL.md:44`)

Assigned once each: `scripts/README.md:545` ("normalised against the calibration ladder") to 04; `skills/cycle/SKILL.md:24` ("up or down one rung only") to 08; `skills/cycle/SKILL.md:26` (check dates inferred from "the last `models-*.md` audit or ledger entry") to 09. Each adds a pattern to `scripts/rules-lint.patterns`, a new test method in `tests/test_rules_lint.py` that writes the old wording to a temp repo file and expects a hit (do not edit the shared fixtures under `tests/fixtures/rules_lint/`: `test_sources_allow_and_dropped` counts exact hits), and fixes every hit from `rg -n` on the old string outside `docs/plans/`. The six-column ledger wording (packet 02) is replaced where it is a writer instruction; it gets no stale pattern because old tables stay valid.

## Traceability

| Requirement | Packets |
|---|---|
| Event helper, format, report, skill (flow) | 01, 05, 10 |
| Experiment register: ledger columns, stale and pending checks, `pendingDays`, schedule and startup notices | 02, 06 |
| packet-report honesty: aliases, unknown, missing tokens and cost, failing landed packets | 04 |
| Review economics and conditional calibration | 08 |
| Brief lint and the opt-in dispatch flag | 03, 07 |
| Due-check nag and recording completions | 09 (reads 02, 06) |
| Installed-copy registration of the new scripts | 11 |
| Release, README, version, end-to-end proof | 12 (README skill row in 10) |

## End-to-end verification

Packet 12 runs, on the `release-0.10` integration branch with `tools/ci-local` present: event to flow report; `brief-lint` on `templates/plan/briefs/01-example.md` and on one of this plan's own briefs; `experiment-check` on a temporary enrolled project with a legacy ledger and a current-format ledger, an overdue row, a pending row and never-run checks; `kaizen-scheduled checks record` from a linked worktree; `packet-report` before and after on `tests/fixtures/packets.jsonl`; a `codex-dispatch --brief-lint` smoke with a stub runner; a copied install finding every new script; then `tools/ci-local --python 3.9`, `python3 -m unittest discover -s tests`, `shellcheck -S warning hooks/*.sh` and `claude plugin validate .`. It pastes trimmed output and exit statuses into the Results section below. The plan is not done until that run is clean.

### Results

Pending packet 12.

## Risks and mitigations

1. Event ordering or truncated lines bias timings: the report sorts by timestamp with stable source order; malformed lines are counted; open intervals are excluded, not extended to "now".
2. Missing severity, tokens or cost mislead calibration: unknown is reported separately; HOLD needs complete evidence, otherwise the original proposal stands with the reason.
3. Hook regression: the audit-notice SessionStart hook must keep emitting one JSON object and exit 0 on every path. Packet 06 (Terra high) adds failure-path tests and a once-per-day marker so the notice does not repeat each session.
4. Concurrent `checks.json` writers lose updates: lock plus write-to-temp plus `os.replace`; tested with two simultaneous writers.
5. Packets 02, 03 and 05 are near the line limit and 09 is over it (merged by decision). Each brief has a split trigger; the orchestrator replans a packet that reports it exceeded 400 lines instead of letting scope be dropped.
6. Intermediate states fail the repo's version rule: only the integration branch carries them; nothing is published before 12.
7. The due-check nag fires everywhere until the first recorded completion: stated in the changelog and the skills; the hook shows it at most once a day.

## Rollout / rollback

Existing outcome logs, ledgers and configs stay valid. Event logging, `--brief-lint` and the metric and review-date columns are opt-in or additive. The experiment and due-check notices appear automatically for enrolled projects (at most once a day in the hook); `schedule=off` or `"enabled": false` silences them. Roll back by reverting the release merge; `checks.json` and `checks.json.bak` are per-machine files that can be deleted. User ledgers are never rewritten except by a skill appending two header columns to a legacy table on its first new row (revert by deleting the two columns). The orchestrator tags and pushes.

## Open questions

None for the owner. Cuts: automatic discovery of experiments outside the ledger; recovery of past check dates; automatic orchestrator integration; running metric commands.
