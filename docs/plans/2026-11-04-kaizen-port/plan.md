# Plan: make agent-kaizen the single home for self-improvement tooling

Plan dir: `docs/plans/2026-11-04-kaizen-port/` (context in `context.md`, briefs in `briefs/`). Written 2026-11-04.

## Summary

Port the owner's `~/.claude`-only audit tooling into the plugin in generic form, link `~/.claude/bin` to the plugin so copies cannot drift, add a drift check, define an outcome-log contract that any enrolled project can feed, run all of it from the scheduled cycle, record applied changes in a configurable notes ledger and propose measured effects, put the process rules in the skills, and release 0.7.0. Then migrate the owner's setup and run the scheduled cycle once for real. 15 packets in 7 groups (revised after plan review; see `review-findings.md`).

## Goal / non-goals

Goals: the six numbered goals in `input.md` (one source of truth + drift check; project data contract; periodic run; change recording and measurement; process rules in skills; docs and release).
Non-goals: editing New World; porting the owner-only Codex features (family aliases, lean overrides, Unity/Blender, 3d preamble) in this plan (see Decision 2); auto-applying ledger measurements (proposals only); Windows support.

## Context

See `context.md` (verified file:line map, check commands, discrepancies). Key correction: the live `token-audit` is an old fork and the plugin's is far ahead; only sections 9-11 and the section 7 Codex durations exist in `kaizen-token-audit`, and the calibration logic lives in New World's `tools/packet_report.py`. So packets re-implement generically; they do not copy from bin.

Review corrections folded in: the plugin is NOT installed from this directory. `~/.claude/settings.json` points the marketplace `agent-kaizen-tools` at this repo (a directory source), but `~/.claude/plugins/installed_plugins.json` shows the installed copy is a stale cache of 0.2.0, so `/agent-kaizen:cycle` runs the old skill until the plugin is updated (packet 12 step 6). Symlinks from `~/.claude/bin` still point at this repo path and stay stable. `~/.claude/audits/projects/index.json` does not exist yet; packet 09 makes `audit` create it.

## Approach

1. Plugin scripts stay canonical. `kaizen-link` creates symlinks (or copies when the plugin lives under a plugin cache, whose path changes per version) from `~/.claude/bin` and `~/.claude/hooks` to the plugin, and `kaizen-link --check` reports drift. Intentional differences are listed in the global setting `localScripts`; they are reported as LOCAL and every mutating action skips them. Copy mode also installs the runtime dependencies (`token-audit`, `pricing.json`, `rules-lint.patterns`) under their canonical names. Rollback unlinks first, then runs `kaizen-backup undo`, because undo copies through symlinks.
2. A project feeds the audit by writing `out/packets.jsonl` (documented keys and trailers). The plugin's own `packet-report` computes outcomes and calibration proposals from that file, so no project script is required. Optional project commands (shadow status, slow tests, speed report) are named in the owner's global config, never in a committed file.
3. `kaizen-project-report` assembles one Markdown file per enrolled project; `kaizen-scheduled audit|review` runs it plus `kaizen-link --check`, `rules-lint` and `notes-ledger due`, writing files the `cycle` skill reads. Failures of one step never fail the audit.
4. `notes-ledger add` appends a row to the owner's CSV and timeline (paths from global config), under a file lock and recoverable after a partial failure; `notes-ledger due` proposes measured effects from before/after data of the same scope; `notes-ledger set` is the owner-approved write. Unattended runs may `add` only, and deny rules block direct Edit/Write of the ledger files.
5. Skills, agent and templates carry the three planning rules and the Kaizen rule.

Rejected: wrapper scripts (same path problem as symlinks, plus a layer); project commands in `docs/kaizen/config.json` (an unattended job would run repo-supplied commands); folding project sections into token-audit's 80-line report (budget pressure, couples the scan to project tooling); touching New World.

## Decisions needed (none blocks the plan; proceeding on the recommendation)

1. **Symlink vs wrapper vs copy for `~/.claude/bin`.** Recommend symlinks when the plugin path is stable (this owner: marketplace `source.path` is the repo clone), copies when it is under a plugin cache, no wrappers. `kaizen-link --mode auto` picks by path; the drift check handles both. Owner only needs to say no if they prefer copies.
2. **Codex family.** The live `codex-dispatch`, `codex-run`, `codex_common.py`, `codex-review`, `dispatch-status` hold owner-only features the plugin versions lack, so linking them now would regress dispatch. Recommend: this plan ports only the listed improvements (`codex-review --paths`, generic dirty-worktree rows in `dispatch-status`, the section 7 table) into the plugin, and declares the five live files in `localScripts` until a follow-up plan ports `resolve_model`, `lean_overrides` and the MCP preflight generically. If the owner wants those five linked in this plan, add two packets (about 300 lines each) before packet 12.
3. **Launchd jobs (hard stop in autonomy.md, still pending the owner's OK).** The three current jobs (`com.highwayoflife.token-audit`, `com.agent-kaizen.audit`, `com.agent-kaizen.review`) run old copies. Recommend replacing all three with `install-schedule --apply --review` in propose mode. The old review job ran `cycle auto` in New World; keeping auto means global `--auto all` or a `docs/kaizen/config.json` inside New World (outside this plan), so packet 12 does neither and reports it. Until the OK, packet 12 runs its deferred branch B: `kaizen-token-audit` stays in `localScripts`, the registry file stays, the old jobs are untouched, and the backup is still finished.
3b. **Plugin update (asks the caller first).** Packet 12 updates the installed plugin from the stale 0.2.0 cache to 0.7.0 so the new skills actually run.
4. **Notes repo writes in unattended runs.** Recommend: scheduled `auto` runs may `notes-ledger add` (append-only) and never `set`.

## Assumptions

- Version 0.7.0 dated 2026-11-04.
- Default `calibrationLadder` is generic (haiku, sonnet medium, sonnet high, opus high); the owner's config sets terra/sol rungs.
- Packets 01-10 touch only the plugin repo; packet 12 touches `~/.claude` (with `kaizen-backup begin/finish`) and the notes repo; New World is read-only.
- `claude` is on PATH for the final scheduled-cycle run and one headless Sonnet run is acceptable spend.
- Sol is used once: packet 09 (unattended permission allow and deny lists, orchestrator decision) at high effort. 1 of 15 packets uses Sol; all other plugin packets are Terra medium, the two `~/.claude` packets are Sonnet.
- Every Codex packet runs in its own git worktree of this repo (`git worktree add ~/github/highwayoflife/agent-kaizen-wt-<id> -b kz-<id>`), so groups can run in parallel; the orchestrator merges group by group.

## Packets

| id | title | depends on | group | agent / model / effort | risk | size | verify |
|---|---|---|---|---|---|---|---|
| 01 | `kaizen-link`: link/copy to `~/.claude/bin` + `hooks`, `--check` drift, LOCAL-safe, rollback-safe | - | A | codex-engineer / Terra / medium | normal | M | `python3 -m unittest tests.test_kaizen_link -v`; full suite |
| 02 | `packet-report` + outcome-log contract doc | - | A | codex-engineer / Terra / medium | normal | M | `python3 -m unittest tests.test_packet_report -v`; parity diff vs New World `--json` |
| 03 | Generic `rules-lint` + built-in stale list | - | A | codex-engineer / Terra / medium | normal | S | `python3 -m unittest tests.test_rules_lint -v` |
| 04 | Config keys: `projectCommands`, `notesLedger`, `calibrationLadder`, `rulesLintFiles`, `localScripts` | - | A | codex-engineer / Terra / medium | normal | S | `python3 -m unittest tests.test_config_keys tests.test_schedule -v` |
| 05a | token-audit section 7: Codex kind/duration table (changes `scan_codex`) | - | B | codex-engineer / Terra / medium | normal | S | `tests.test_codex_kinds`; token-audit timing vs HEAD |
| 05b | `codex-review --paths` + `dispatch-status` dirty worktrees | - | B | codex-engineer / Terra / medium | normal | S | `tests.test_review_paths tests.test_dispatch_status` |
| 06 | `kaizen-project-report` (outcomes, calibration, shadow, slow tests, speed) | 02, 04 | B | codex-engineer / Terra / medium | normal | M | `python3 -m unittest tests.test_project_report -v` |
| 07a | `notes-ledger add` / `set` (lock, partial-failure recovery) | 04 | B | codex-engineer / Terra / medium | normal | M | `python3 -m unittest tests.test_notes_ledger -v` |
| 07b | `notes-ledger due` (scope-matched measurement proposals) | 07a, 02, 04 | C | codex-engineer / Terra / medium | normal | S | `python3 -m unittest tests.test_notes_ledger -v` |
| 08 | `session-notes.sh` hook + settings example | - (soft: 03, 05b) | C | codex-engineer / Terra / medium | normal | S | `shellcheck -S warning hooks/*.sh`; `tests.test_session_notes` |
| 09 | Scheduled wiring: index discovery, project reports, checks file, ledger deny rules, `--propose-only/--force`, install via `kaizen-link` | 01, 03, 06, 07a, 07b | D | codex-engineer / **Sol / high** (security: unattended permissions) | high | M | `tests.test_schedule_steps`; full suite |
| 10 | Skills, auditor agent, templates: workflow + process rules | 01, 02, 03, 06, 07a | D | codex-engineer / Terra / medium | normal | M | `tests.test_repo tests.test_process_rules`; `claude plugin validate .` |
| 11 | Docs and release 0.7.0 | 05a, 05b, 08, 09, 10 | E | codex-engineer / Terra / medium | low | S | full suite; `claude plugin validate .` |
| 12 | Owner migration: backup, plugin update, links, config, notes rows; branch A (launchd approved) or B (deferred) | 11 | F | sonnet-engineer / Sonnet / medium | high | M | `kaizen-link --check` exit 0 (drift before/after); plugin sources untouched |
| 13 | End-to-end gate: audit, propose-only review, ledger due, timings | 12 | G | sonnet-engineer / Sonnet / medium | normal | S | pasted redacted output, below |

Groups: A = 01-04, B = 05a 05b 06 07a, C = 07b 08, D = 09 10, E = 11, F = 12, G = 13 (all parallel within a group, each Codex packet in its own worktree; groups are serial because later packets edit files earlier ones created, or need merged scripts). Review batches: A, B, C+D (packet 09 gets a per-packet review before merge), E+F (packet 12 gets a per-packet review), G is the gate.

File ownership per group:
- A: 01 `scripts/kaizen-link`, `tests/test_kaizen_link.py`; 02 `scripts/packet-report`, `docs/outcome-log.md`, `tests/test_packet_report.py`, `tests/fixtures/packets.jsonl`; 03 `scripts/rules-lint`, `scripts/rules-lint.patterns`, `tests/test_rules_lint.py`, `tests/fixtures/rules_lint/`; 04 `scripts/kaizen-scheduled`, `docs/scheduling.md`, `tests/test_config_keys.py`.
- B: 05a `scripts/token-audit`, `tests/test_codex_kinds.py`; 05b `scripts/codex-review`, `scripts/dispatch-status`, `tests/test_review_paths.py`, `tests/test_dispatch_status.py`; 06 `scripts/kaizen-project-report`, `tests/test_project_report.py`; 07a `scripts/notes-ledger` (new), `tests/test_notes_ledger.py` (new).
- C: 07b `scripts/notes-ledger` (adds `due`), `tests/test_notes_ledger.py` (adds a class); 08 `hooks/session-notes.sh`, `templates/settings.example.json`, `tests/test_session_notes.py`.
- D: 09 `scripts/kaizen-scheduled`, `scripts/install-schedule`, `docs/scheduling.md` (the `--apply` sentence and file list), `scripts/rules-lint.patterns` + `tests/fixtures/rules_lint/` + `tests/test_rules_lint.py` (one added pattern), `tests/test_schedule.py`, `tests/test_schedule_steps.py`; 10 `skills/*/SKILL.md`, `agents/kaizen-auditor.md`, `templates/global-CLAUDE.md`, `templates/agents/planner.md`, `templates/agent-context/planning.md`, `tests/test_process_rules.py`.
- E: 11 `README.md`, `CHANGELOG.md`, `.claude-plugin/plugin.json`, `scripts/README.md`, `docs/what-we-learned.md`, `docs/scheduling.md` (section only).
- F: 12 `~/.claude/**`, notes repo, plugin cache update (no plugin repo files).
- G: 13 `docs/plans/2026-11-04-kaizen-port/plan.md` (Result line only).

## Traceability

| requirement | packets |
|---|---|
| G1 plugin scripts canonical, bin links, installer/start story, backup, drift check run by audit | 01, 09 (installer + audit step), 10 (start skill text), 12 (links, backup, plugin update), 13 |
| G1 port: token-audit 9-11 (as project report), section 7, registry replaced | 05a (section 7), 06 (9-11 equivalent), 09 (enrolment + index replace registry), 12 branch A (rename registry) |
| G1 port: rules-lint | 03, 09 |
| G1 port: codex-review --paths, dispatch-status | 05b |
| G1 port: hooks session-notes (after-compact, limit-big-read already in plugin) | 08 |
| G2 contract: packets.jsonl keys, trailers, shadow-status command | 02 (doc + report), 04 (config), 06 (commands) |
| G3 periodic run + auditor knows | 09, 10 |
| G4 record + measure, owner paths in user config | 04, 07a, 07b, 09 (unattended add + ledger deny rules), 10 (cycle step), 12 |
| G5 process rules in skills | 10 |
| G6 docs, release | 11 |
| Rules: before/after measurement | 05a (token-audit timing), 12 (drift counts), 13 (scheduled audit with/without new steps) |
| Rules: end-to-end gate | 13 |
| Rules: superseded wording into rules-lint | 03 (built-in list incl. `project-repos.txt`), 09 (`copies the runner, token-audit`), 12 (owner patterns incl. old CLAUDE.md item 7 wording) |

## End-to-end verification

Packet 13 runs on the owner's machine after packet 12 (installed plugin at 0.7.0): `kaizen-link --check`, `rules-lint`, `kaizen-scheduled audit` with and without `KAIZEN_SKIP_CHECKS` (timing) and for real (must create `projects/index.json`), a permission rehearsal for the auto-mode lists, `kaizen-scheduled review --project-dir <New World> --propose-only --force` (one headless Sonnet run, restricted by the runner), `notes-ledger due`. Output is redacted to `~` paths, pasted below, and the repository tests are re-run. The plan is not done until that run is clean.

Result: (to be filled by packet 13)

## Risks and mitigations

- Linking regresses the owner's dispatch: codex family stays local via `localScripts` (Decision 2); `kaizen-link` skips LOCAL names in every mutating action (tested byte-identical), refuses to replace a differing regular file without `--replace`, and renames instead of deleting.
- Rollback through symlinks overwrites plugin sources (`kaizen-backup undo` uses `copy2`): rollback order is `kaizen-link --unlink --restore-replaced` first, then undo (rehearsed in packet 01's test, checked by `git status` in packet 12).
- Appending to the notes ledger is not append-only if the unattended agent can Edit it: packet 09 adds Edit/Write deny rules for both ledger files, and `notes-ledger` locks and recovers from partial writes.
- The skills the owner runs are the stale 0.2.0 cache until the plugin is updated: packet 12 step 6, and packet 13 refuses to start otherwise.
- Unattended job runs project commands: commands come only from global config, as argv, with timeout; packet 09 is high risk with per-packet review.
- `shadowStatus` in New World writes `review/shadow.json` on STOP: documented in the contract; the project report prints it as "may write state".
- Old launchd jobs keep running old copies: packet 12 replaces them only with the owner's OK. Until then (branch B) `kaizen-token-audit` stays in `localScripts` and the registry stays, so they keep working; `bin/token-audit` is linked and the old `com.highwayoflife.token-audit` job runs the plugin script with the same flags.
- `install-schedule --apply` could rename another tool's generically named file: it applies `--replace-prefixed`, so only `kaizen-` names are replaced.
- Calibration proposals on tiny n: `n>=8` rule and an explicit "too few" row are kept from the original.
- Token-audit must stay fast: packet 05a times it against `git show HEAD:scripts/token-audit`.

## Rollout / rollback

Plugin work lands on a branch in group order, each Codex packet from its own worktree branch `kz-<id>`; the owner migration happens only after packet 11 is merged. Rollback of the owner side, in this order: (1) `kaizen-link --unlink --restore-replaced`, (2) `kaizen-backup undo last` (never before step 1: undo copies through symlinks into the plugin sources), (3) run the reverse `launchctl bootstrap` commands that packet 12 recorded with `kaizen-backup action`, after moving the retired plists back from `~/.claude/audits/retired-launchagents/`. Then confirm `git status --porcelain` in the plugin repo is empty. The plugin update can be reverted by reinstalling 0.2.0 only if the owner wants that; the cache copy is not touched by rollback.

## Open questions

- Whether to port the Codex owner-only features next (Decision 2 follow-up).
- Whether New World should later shrink `tools/packet_report.py` to call `packet-report` (not needed for this plan).
