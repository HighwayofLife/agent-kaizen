# Changelog

Versions follow `version` in `.claude-plugin/plugin.json`. A GitHub marketplace install only picks up a release when that number changes.

## 0.9.1 (2026-11-10)

Follow-up fixes to 0.9.0. Each fix has a regression test.

`kaizen-backup`:

- New `kaizen-backup prune --older-than DAYS [--apply]` removes finished changes created more than DAYS days ago (DAYS 1 or more). It is a dry run unless `--apply` is given. It never removes unfinished changes, changes with a corrupt manifest, changes without a usable `created_at`, or anything newer than the cutoff; each is reported as `skipped`. Pruning an older change does not affect `undo` of a newer change to the same file.
- `kaizen-backup undo run` now undoes only the newest group of consecutive changes that share one run id and session. Older changes that reused the id are left open, and stderr names them. Undo those with `kaizen-backup undo CHANGE_DIR`.

`install-schedule`:

- `--apply` without `--review` still removes the review job of the backend it writes to. A review job in another backend (launchd, systemd, cron) is left alone, and a warning on stderr gives the command that removes it.

`codex-dispatch`:

- The resume prompt sent after a failed require-change check no longer mentions `--allow-no-change`. The report and `--help` still name the flag.
- When `-C` is a subdirectory of a Git repository, the require-change snapshot covers only that subdirectory. Changes elsewhere in the repo no longer count as Codex's change. With `-C` at the repo root nothing changes.

`packet-report`:

- An escalation is also counted when only the effort rises between rounds (same model). Such pairs are labelled with model and effort, for example `terra:medium->terra:high`. Model-only changes keep the model path label.

`usage-db`, `usage-series`, `usage-compare`:

- New `usage-db prune --older-than DAYS [--apply] [--db PATH]` deletes old calls and vacuums the file when `--apply` is given. It is otherwise a dry run. Nothing is pruned automatically. A transcript that still exists and later changes is read again in full, which stores its pruned calls again.
- The usage database schema is now version 2. Codex call ids start with the session id stored inside the session file, so a session file that is copied or moved to a new name is no longer counted twice.
- New `usage-series --from-db` reads calls, tokens and cost from the usage database instead of transcripts. Columns the database does not store (wake-ups, images, reads, spawns, Codex database counts, `command_*`, and `runs` in `daily-agents.csv`) are written as `n/a`.
- New `usage-compare --from-db` (with `--clean-split`) computes the clean-split metrics from the usage database, Claude calls only. `wake-ups/day` and `images/day` print `n/a`. Calls without an id that share the same second and usage count once in the database.

`kaizen-scheduled`:

- A run creates a protected `<backup-root>/.active-run.json` before each model run. Reviews lock the backup root, and a watchdog stops the model process group after runner death before recovery takes the lock. Unresolved markers are retained and retried across audits folders; later runs use `.active-run.<32-lowercase-hex-uuid>.json`. The scan also accepts older hyphenated UUID markers and only reads regular files with mode 0600.
- Hard-kill recovery matches both run and session ids. It undoes finished failed changes only when their after hashes match, without `--force`; unfinished changes require manual resolution. Ledger snapshots are authenticated before verification or restoration. A restored violation makes that cycle propose-only. A marker is removed only after rollback and ledger verification or restoration succeed; restored ledgers are verified again. Unresolved cleanup retains the marker and snapshots, and every retry remains propose-only. Housekeeping protects referenced snapshots, or all ledger snapshots if a marker is unreadable. The status reports the problem, a non-forced undo command when available, and a command to discard the record after manual resolution. Legacy audit-local markers are untrusted and require inspection.
- Every step the runner starts (model run, token audit, usage-db ingest, git, rollback) runs in its own session. On timeout or error the whole process group is killed, even if its leader has exited. The model group is also stopped before normal rollback.
- SIGTERM, SIGHUP or SIGINT during a model run stops the model group, runs rollback and the ledger check, and exits 143, 129 or 130.
- Auto-mode Read rules now scope Read, Grep and Glob to the project, config homes, plugin root, default audits folder and actual `--audits` folder. Propose mode retains bare Read, Grep and Glob.
- The live permission probe covers the newer write denies and scoped reads. It skips the Codex `AGENTS.md` deny when the Codex home is missing or the file already exists.
- `config set` (global and `--for`) takes a lock file, `agent-kaizen.json.lock`, beside the global config.

Other:

- `scripts/pricing.json`: added `claude-fable-5-2` from the vendor pricing page and pointed the `fable` alias at it. All other rows were re-checked against both vendors' pricing pages on 2026-11-10, with no changes.
- CI: `docs/autonomy.md` and `docs/outcome-log.md` now count for the version-bump check, because skills read them at runtime.
- Docs: `docs/autonomy.md` no longer repeats the scheduled-runner permission detail from `docs/scheduling.md`. The README environment table lists `KAIZEN_SESSION_ID` and `XDG_CONFIG_HOME`.

Upgrade notes:

- The usage database upgrades from version 1 to 2 in place on the next `usage-db ingest`, with no flag or prompt. Codex rows whose session file still exists are re-keyed, and rows stored twice under two file names collapse to one. Rows whose file was deleted before the upgrade keep their old ids, so a copied session can stay counted twice. `status`, `report` and `sql` read a version 1 database without migrating it.
- Behaviour change: `kaizen-backup undo run` no longer undoes older changes that reused a run id.
- Behaviour change: with `codex-dispatch -C` set to a subdirectory of a repo, only changes inside that subdirectory satisfy the require-change check.
- Behaviour change: `packet-report` counts effort-only rises as escalations, so escalation counts can go up.
- After a hard kill, a restored ledger violation makes the recovery cycle propose-only. Unresolved recovery keeps every retry propose-only until resolved. Inspect the reported recovery command and retained marker.

## 0.9.0 (2026-11-10)

From a full review of the plugin. Each fix has a regression test.

Upgrade notes:

- A project file can no longer switch on scheduled auto mode by itself. `scheduledAutonomy: auto` in `docs/kaizen/config.json` counts only when the project is listed in the new global-only `autoProjects` setting. Run `kaizen-scheduled config set --for DIR scheduledAutonomy=auto` (or `install-schedule --auto DIR`) once per project; until then the project runs as propose.
- `install-schedule --apply` without `--review` now removes an installed review job. The audit job is never removed this way.
- `token-audit` prices a model only on an exact key or alias match (a `-YYYYMMDD` or bracket suffix is allowed). A newer sibling model shows as Unpriced until `pricing.json` lists it.
- The three project-specific patterns added to the bundled `rules-lint.patterns` in 0.8.0 are removed. Keep personal patterns in `kaizen-rules-lint.txt` under the Claude config dir.

New:

- `usage-db`: a SQLite store of per-call token usage (`ingest`, `status`, `report`, `sql`). Ingest is incremental, so history survives after Claude Code deletes old transcripts. It stores ids, times, models, working directories and token counts, never message text. Cost is computed at report time. The scheduled audit job runs the ingest.
- `codex-dispatch --check-timeout` (default 1800 s) and `--codex-timeout` (default off).
- `CODEX_DISPATCH_REASON_MODELS` sets which model names need a reason line in the brief. The default is `sol`; an empty value turns the guard off. `Model reason:` is accepted as well as `Sol reason:`.
- `KAIZEN_BASH_BURST=0` or `"enabled": false` turns the bash-burst hook off.

Scheduled runs:

- More credential files are denied in both modes (kube, npm, pypi, gcloud, azure and others, plus `*.pem`, `*.key`, `id_rsa*`, `.envrc` in projects). Auto mode can no longer edit project hooks, agents, commands, skills, `.mcp.json`, CI workflows, the `agents/` folder in the Claude config dir or the Codex `AGENTS.md`.
- `config set --for DIR scheduledAutonomy=auto` is refused when `DIR` is a subdirectory or linked worktree of the project that runs use. The message names that project.
- A path that the permission rules cannot express gives the status `unsupported-path` instead of a line only in `run.log`.
- SIGTERM and SIGHUP run the rollback and the ledger check before exit. The model run has a time limit (`KAIZEN_REVIEW_TIMEOUT`, default 3600 s) and every other step has 600 s.
- Audit, review and housekeeping take a run lock. A second run waits up to `KAIZEN_LOCK_WAIT` seconds (default 1800), then skips.
- The ledger guard saves the rejected content before it restores its snapshot. A ledger that cannot be read is `ledger-config-error`, not a violation, and housekeeping still runs.
- A second proposal on the same day is written as `cycle-<date>-2.md`. `run.log` rotates at 1 MiB.
- A `docs/kaizen/` folder in a subdirectory of a larger repository is its own project.
- `install-schedule` never rewrites a crontab after `crontab -l` fails for a reason other than "no crontab", and prints one-line errors instead of tracebacks.

Dispatch and review:

- A run or review is no longer reported as failed because its tool output contains an overload message.
- The `require-change` check compares the tree right before and after each Codex run. Files written by checks do not count, a commit by Codex does, and the output directory is excluded wherever it lies in the repository.
- Codex runs and checks run in their own process group. SIGINT, SIGTERM or SIGHUP to `codex-dispatch` stops them before it exits.
- A refused dispatch prints `Reason:` and `STATUS: CODEX FAILED` on stdout. A Codex failure shows the last stderr lines as its reason.
- `packet-report` labels an escalation by its full model path (`terra->sol->terra`).

Backups, ledger and linker:

- `kaizen-backup undo run` no longer reports a conflict when two changes in one run edit the same file. Undo of an unfinished change that created a file is a conflict unless `--force` is given. The newest change is chosen by creation time. A corrupt manifest is skipped with a warning. Backup folders are mode 700 and the root follows `CLAUDE_CONFIG_DIR`.
- `notes-ledger set` can no longer update the wrong row when a change text contains an unusual line separator. `add` no longer skips the timeline row for a change whose text starts with an existing one. Errors name the row. A BOM, blank lines, CRLF files and symlinked ledgers are handled.
- `kaizen-link --apply` leaves a live symlink that points outside the plugin alone unless `--replace` is given, and then backs it up. `--unlink` removes copies that are identical to the plugin's files.

Usage audit:

- Codex numbers in `token-audit` are in-window deltas. A session that started before the window is no longer charged its whole total. `token-audit` and `usage-series` share the delta code.
- `token-audit` skips the tool-universe rescan when every main session has tool definitions. `usage-series` skips files older than the window.
- Zero-usage synthetic rows are not counted as calls. A malformed timestamp no longer stops `usage-series`. The Cost section warns when `pricing.json` was last checked more than 60 days ago.

Hooks, templates and CI:

- bash-burst also counts failed Bash calls, detects the main session by the absence of `agent_id`, counts safely under parallel calls and keeps its state in a private per-user folder. Its message no longer names agents the plugin does not ship.
- `after-compact` is silent without jq. The image guard follows symlinks. The big-read hint quotes the path, and an offset-only read near the end of a file is allowed.
- The settings template uses the Claude config dir for hook paths and sets hook timeouts. Verdict-style agents get their own context file.
- The project and orchestrator templates no longer carry game-specific content. The global template gains a rule to split a mixed fix batch by tier before by file.
- CI runs `--help` on every script and requires the version to increase.

Docs: an Uninstall section in the README, sections for `install-schedule`, `kaizen-backup` and `usage-db` in `scripts/README.md`, and skills that no longer hard-code `~/.claude`.

## 0.8.0 (2026-11-06)

From the 2026-11-06 weekly review:

- `codex-dispatch` snapshots the Git tree before Codex runs and adds a built-in `require-change` check for engineer runs. A run that changes nothing fails and resumes. `--allow-no-change` turns the check off. A tree that is already dirty gets a WARNING line, because a status-based check could not fail there.
- `codex-dispatch` refuses a Sol model unless the brief has a `Sol reason:` line. Resumed threads are exempt. The report shows the reason.
- New `bash-burst` hook (UserPromptSubmit + PostToolUse on Bash, main session only). It warns after `KAIZEN_BASH_BURST` Bash calls in one turn (default 8) and at each multiple. It fails open.
- `packet-report` reads an optional `dispatch_models` list (model, effort, rounds per dispatch) from the outcome log. It reports `escalations` and `dispatch_models_coverage`.

## 0.7.2 (2026-11-04)

- The planner and verifier templates gain reading and diff budgets: locate with `rg -n` or the code map and read only printed line ranges, and run `git diff --stat` before per-file diffs.

## 0.7.1 (2026-11-04)

Security hardening for scheduled (unattended) runs, from the port's final audit and a live permission probe:

- Scheduled runs have no network tools (WebFetch and WebSearch are removed) and no plain Bash commands. The only Bash rules left are the exact `notes-ledger add` and `kaizen-backup begin|finish|list` helpers, in auto mode only. Read, Grep and Glob cover reading. Model and release web checks run only in interactive cycles.
- Auto mode uses the default permission mode with scoped Edit/Write allow rules instead of `acceptEdits`, and denies file-writing and read-through Bash commands, credential files, `.env` files and `.git` trees, including in the config homes.
- Failed auto changes are rolled back by the runner, never the model. The runner only rolls back backups created during the run. The backup root cannot be edited or read by the model, entries are validated, and restores never write through symlinks. `kaizen-backup begin` refuses credential paths.
- The ledger guard detects symlink swaps of the ledger file and its parents. Projects are iterated once per canonical repo, not per worktree.
- Unattended runs cannot edit `.claude` instruction files, because Claude Code protects them in `-p` mode. Proposals for those files go into the report.
- `kaizen-link --check` reports `STALE-CACHE` when the installed plugin cache differs from the plugin root. `claude plugin update` does nothing while the version is unchanged, so bump the version or reinstall. Installed `kaizen-link` copies find their plugin root, the installer refreshes managed copies, and `kaizen-project-report` rejects relative `projectCommands` keys.
- `notes-ledger due` tolerates non-object config and malformed dates. The session-notes hook has a timeout fallback for systems without `timeout`.
- `tests/test_schedule_live_probe.py` (opt-in, `KAIZEN_LIVE_PROBE=1`) checks these permissions against the real Claude CLI.

## 0.7.0 (2026-11-04)

- `kaizen-link` links or copies managed scripts and hooks; `--check` reports drift, `localScripts` marks intended differences, and `--apply --replace` saves differing files with a `.replaced-<date>` suffix. Plugin cache installs use copies.
- `packet-report` reads project outcomes from `out/packets.jsonl`; the contract and `Risk`, `Fix-Origin`, and `Fixes` trailers are in `docs/outcome-log.md`. For groups of at least 8, it proposes UP below 70% first-pass or above 30% fix rate, and DOWN at 95% first-pass or higher with no audit fixes. Proposals are not applied automatically.
- `kaizen-project-report` combines packet outcomes, calibration proposals, configured command output and pending ledger rows. Global `projectCommands` configures argv lists with a 120-second timeout.
- `rules-lint` uses bundled, user and project pattern files and the global `rulesLintFiles` setting to find stale wording.
- `notes-ledger` adds and updates changes and proposes due measurements through `add`, `set` and `due`. Global `notesLedger` configures it; unattended runs may only use `add`.
- `token-audit` section 7b groups Codex sessions by kind, model and effort with durations. `codex-review diff --paths` limits review paths, `dispatch-status` reports dirty worktrees, and `hooks/session-notes.sh` is opt-in via `templates/settings.example.json`.
- Scheduled runs write `checks-*.md` and project reports; `KAIZEN_SKIP_CHECKS=1` skips checks. Project enrolment uses `docs/kaizen/` in place of the older private project registry.
- The global-only settings `projectCommands`, `notesLedger`, `calibrationLadder`, `rulesLintFiles` and `localScripts` configure these tools.
- `install-schedule --apply` prints the link plan and saves differing `kaizen-` files with a `.replaced-<date>` suffix; other differing files are reported and left alone. `review --propose-only --force` supports restricted reviews of selected projects; `audit` discovers enrolled projects and writes `projects/index.json`.
- Skills and templates add the Kaizen rule and planning rules A, B and C.
- Upgrade notes: re-run `install-schedule --apply` to install the new scripts, then run `kaizen-link --check`. Owners of private script copies in the config directory should compare them with `kaizen-link --check` before replacing them. Use `localScripts` to keep intended differences quiet.

## 0.6.0 (2026-10-31)

- New `usage-series` writes daily UTC usage and agent measurements from local Claude and Codex logs. It supports project selection, command counts, and optional git activity.
- Codex state database totals provide thread and token volumes when session logs are gone. They are not used to calculate prices.
- New `usage-compare` compares rates before and after a change on active days. It flags missing Codex log costs. Optional `--clean-split` excludes before transcripts last written after the cutoff.
- Daily exports include Claude token totals and unpriced call counts. Comparison cost rates exclude days with missing Codex logs and report the excluded dates. Clean split uses all main calls and warns on empty windows.
- Review and cycle can use these comparisons for ledger measured effects.
- Upgrade notes: none required.

## 0.5.0 (2026-10-30)

- token-audit: the by-agent table shows each subagent type's cost share, models and effort mix. A new extract file per report holds the same numbers per agent type, plus a hint for types that might run on a cheaper model. New `--extract-out` defaults to the audits folder's `extracts/`, never `--out`.
- New `kaizen-scheduled housekeep` runs after every scheduled audit and review and at the end of an interactive cycle. It deletes the plugin's own old generated files: extracts and probe output after 30 days (200 MB cap), failed proposals and notice markers after 30 days, and reports and proposals after 365 days (newest 5 per folder and family kept). Settings `retention` (`auto`/`off`) and `retentionOverrides` are global only.
- Scheduled auto runs can edit Markdown instruction files under the Claude and Codex config homes. Deny rules block settings, hooks, plugins, skills, commands, bin, credentials and every `.json`, `.toml`, `.sh`, `.py` and `.js` file under both homes, the Claude user config file, and the project's `.claude/settings*.json`. The rules cover Edit, Write and recognised file commands, not `cp` or scripts. (replaced in 0.7.1)
- `docs/autonomy.md` adds exceptions to "Deleting things" for own generated data and files kaizen created earlier through `kaizen-backup undo`, and adds Markdown instruction files to the safe list.
- Scheduled auto runs no longer allow `cp` or `touch`, which the deny rules don't cover. Deny rules are not built for paths that contain `,`, `(`, `)`, `*`, `?`, `[`, `]` or `\`; the review fails closed instead.
- Config values are validated by type (integers, enums, objects, relative-path lists); invalid values fall back to the default with a warning.
- Upgrade notes: re-run `install-schedule --apply` to refresh the installed runner. Housekeeping starts on the next scheduled run after that. Set `retention=off` to keep every file. Scheduled auto runs that previously could not touch the config homes can now edit the Markdown files listed above.

## 0.4.0 (2026-10-30)

- The optional weekly review runs only for enrolled projects (those with `docs/kaizen/`) that had a session or a commit since their last review. It finds projects from recent Claude Code and Codex sessions, treats a repository's worktrees as one project, and has no project cap. Activity during a successful review does not make the project due again.
- New settings: global `enabled`, and global or project `schedule` (`active`, `always`, `off`) and `scheduledAutonomy` (`propose`, `auto`). A project value overrides the global one. `scheduledAutonomy` is separate from the interactive `autonomy` setting. `install-schedule --auto all|none|DIR...` sets it, and the `schedule` and `start` skills ask before writing it.
- New `scripts/kaizen-scheduled` runner: `audit`, `review [--dry-run]` and `config show|set`. `install-schedule --apply` installs it, and the jobs call it. One project's failure no longer stops the others, and a failed retry keeps the day's earlier proposal.
- token-audit: `--cwd` selects sessions by their recorded project path, including Codex sessions. Reports carry a scope line and are compared only with earlier reports of the same scope. The scan skips files older than the window. Built-in tools are no longer prune candidates.
- Scripts, hooks and skills honor `CLAUDE_CONFIG_DIR` and `CODEX_HOME`, including in scheduled jobs. Jobs use absolute paths and leave other crontab lines alone. On Linux, systemd user timers are used when cron is not available.
- `codex-review` defaults to `origin/HEAD`. `codex-review` and `codex-dispatch` keep `out/` out of git. The image and big-read guards degrade when the image agent or `jq` is missing. The audit notice uses the config directory, per-project reports, `enabled` and `schedule`.
- codex-dispatch: a repo may route check commands through an executable `tools/rewrite_check` (argv[1] is the command, stdout its replacement, empty means unchanged; worktrees fall back to the main checkout's copy). The docs now say to give `-k` the narrowest check.
- `templates/settings.example.json` no longer registers the audit-notice hook, because the plugin already does. If you copied that entry into your settings, delete it to avoid duplicate notices.
- Upgrading from 0.3.x: re-run `install-schedule --apply` (add `--review` for the weekly review). Existing launchd and cron jobs are replaced in place. Before moving to systemd, run `install-schedule --remove`. Three behaviour changes:
  - `--project-dir` no longer defaults to the current directory. Without it, every enrolled project with activity is reviewed, and a `--project-dir` without `docs/kaizen/` is skipped.
  - Auto mode is now the `scheduledAutonomy` setting. Re-installing without `--auto` makes the review propose-only.
  - Proposals are written per project in `audits/projects/<key>/`. Old reports are not compared with new ones.

## 0.3.2 (2026-10-29)

- token-audit: report Claude and Codex brief sizes and flag median growth between audits.
- codex-dispatch: checks that were not re-run in the final round are marked as such in the report.

## 0.3.1 (2026-10-29)

- codex-dispatch: resume rounds re-run only the failing checks, then confirm the checks that were skipped, once. Checks see `DISPATCH_ROUND` and `DISPATCH_PASS` (`initial`, `retry`, `final`) so project tooling can run cheaper checks while iterating.

## 0.3.0 (2026-10-29)

Four new audit measurements, inspired by Microsoft's [TokenEconomizer](https://github.com/microsoft/TokenEconomizer), which acts on the same signals live inside each session. Agent Kaizen measures them offline at zero token cost and turns them into proposals:
- **API-equivalent cost:** every message priced cache-aware (cache reads, 5-minute and 1-hour cache writes, uncached input, output) from published prices in `scripts/pricing.json`, including Haiku 5.5's higher rate above 100k prompt tokens. It is a weighting for comparing changes, not a bill.
- **Stuck turns:** the same failure (tool, command or file, and first error line) repeated three or more times in one turn.
- **Repeated failures across sessions:** candidates for one-line repo facts in CLAUDE.md, with a "worked instead" hint when a different launcher, environment variable or directory fixed it.
- **Unused tools and MCP servers** per project, one row per server. Deferred tools are summarised, since only their names are sent.

Also:
- Error lines in the report are normalised and secret-like strings redacted. The scan is faster than 0.2.1, despite the extra measurements.
- The audit, review, trim-context and guardrails skills and docs/autonomy.md use the new sections: repo facts apply in `safe` mode, deny rules only in `auto`.
- README: an animated teaser, the loop redrawn as a light/dark SVG, a new banner, tested versions, and a comparison with TokenEconomizer. The graphics are drawn by `assets/src/*.py`.
- AGENTS.md (also imported by CLAUDE.md and used as the subagent role context): commands and rules for coding agents working on this repo.

## 0.2.1 (2026-10-29)

Fixes from five end-to-end `yolo` test runs on a real project:
- **`kaizen-backup` script** (begin / finish / action / list / undo): backups, manifests, after-hashes and undo are now done by a tested script instead of model-followed steps. Undo refuses conflicts unless `--force`, and prints reverse commands without running them.
- **Scheduled runs:**
  - they can read `~/.claude` and `~/.codex` (`--add-dir`) and run read-only commands (ls, wc, head, tail, rg, git status/diff/log, jq); (replaced in 0.7.1)
  - every change in a run shares a `KAIZEN_RUN_ID`;
  - the audit copy is installed as `kaizen-token-audit`, so it never replaces another `token-audit`.
- **`auto` mode applies changes.** The cycle carries out its top proposals instead of stopping at a list, and docs/autonomy.md lists the reasons that don't justify skipping a change. Headless runs leave protected `~/.claude` files as "do interactively".
- README: the story behind the project.

## 0.2.0 (2026-10-29)

- **Autonomy modes**: `propose` (default), `safe` and `auto` (alias `yolo`), set per run (`/agent-kaizen:cycle yolo`), per project or globally (`/agent-kaizen:autonomy`). Every applied change is backed up, verified, rolled back if verification fails, capped at 3 per run, and logged. The hard stops (secrets, spending, permissions, deletions, pushes, installs) always ask. See docs/autonomy.md.
- New skills: `autonomy` and `undo`.
- `install-schedule --auto`: the weekly cycle applies changes with `acceptEdits` and a narrow tool list (never `bypassPermissions`). (replaced in 0.7.1)
- CI: tests on Linux and macOS (Python 3.9 and 3.13), hook smoke tests, repo-consistency and privacy checks, shellcheck, JSON lint, `claude plugin validate`, and a version and changelog check on PRs.

## 0.1.0 (2026-10-29)

First public release:
- 18 skills: start, audit, cycle, review, roster, models, whats-new, trim-context, slim-instructions, lean-agents, codex-dispatch, tools-before-tokens, code-map, guardrails, batch-wakeups, planning, test-loop, schedule.
- The `kaizen-auditor` agent (propose-only).
- The SessionStart audit notice, plus opt-in guardrail hooks.
- Scripts: token-audit, codex-dispatch, codex-review, codex-run, dispatch-status, install-schedule.
- Templates for CLAUDE.md, the orchestrator file, Codex AGENTS.md and config, settings, agents, role context, plans and briefs.
