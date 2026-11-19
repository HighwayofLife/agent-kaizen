---
name: cycle
description: "Run one full self-improvement cycle: audit, review the ledger, check new models and releases when due, and propose the next changes."
disable-model-invocation: true
argument-hint: "[propose|safe|auto|yolo|propose-only]"
---

# One self-improvement cycle

**Plugin root:** `${CLAUDE_PLUGIN_ROOT}`. If that is still a `${...}` placeholder, use the folder that contains `skills/` (this file is `skills/<name>/SKILL.md`), and substitute that path, in quotes, wherever this skill uses `CLAUDE_PLUGIN_ROOT`.
**Not in Claude Code?** Read `docs/hosts.md` in the plugin root first. Skip steps that only work in Claude Code, and follow its propose-only rule before changing any host configuration.

This is the entry point when you don't know which skill to run. It runs the loop once. With `propose-only` it changes nothing and prints the proposal as Markdown. The scheduler saves it as `cycle-<yyyy-mm-dd>.md` (`-2` suffix for a second one that day) in this project's report folder, printed as `reports` by `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kaizen-scheduled config show --for .`. Run interactively, write it to `docs/kaizen/`.


**Autonomy:** follow `${CLAUDE_PLUGIN_ROOT}/docs/autonomy.md`. The mode comes from the skill argument (`propose`, `safe`, `auto` or `yolo`), else `docs/kaizen/config.json`, else `agent-kaizen.json` in your Claude config dir (`$CLAUDE_CONFIG_DIR` or `~/.claude`), else `propose`. In `safe` and `auto`, read every "wait for my OK" below as: apply it yourself if the mode allows (backup, verify, roll back on failure, ledger row), otherwise list it as a proposal. Hard stops always ask. At most `maxChangesPerRun` changes (default 3). End with a summary of what was applied, skipped and rolled back.

Scheduled runs search with Grep and locate/read files with Glob and Read. Use the supplied reports for git state and measurements. Do not use Bash rg, git, wc, diff, cd, mkdir, token-audit, arbitrary scripts or shell redirection. Auto runs may use only the supplied backup begin/finish/list and notes-ledger add helpers. The runner handles rollback; report a failed check and leave its backup unfinished or finish it with `--verification failed`.

## Task

Add every new self-improvement tool or process to the plugin so it runs on the plugin schedule. Record each change in the notes ledger with what changed, why and how to measure it; re-measure later.

1. **Find the state.** Scheduled runs use the supplied report. Otherwise get `localAudits` and `reports` from `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/kaizen-scheduled" config show --for .`. Read `LEDGER.md` in `docs/kaizen/` or `localAudits`. If missing, ask for `/agent-kaizen:start` (propose-only: report it missing). Interactively, use the newest `token-audit-*.md` across `docs/kaizen/` and `localAudits`, then fall back to `reports`. Read the newest global `checks-*.md` and scoped `project-report-*.md` when present.
2. **Measure.** Interactively, if the newest report is older than 3 days and commands are available, run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kaizen-scheduled review --dry-run --project-dir <project>` with `docs/kaizen` stripped from `localAudits`. Use its canonical `project:` and complete `paths:`. Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/token-audit --cwd <path> --days 14 --out <canonical-project>/docs/kaizen/`, repeating `--cwd <path>` for every listed path. Do not use `--cwd . --days 14 --out docs/kaizen/` alone. Use scoped settings: append `--no-friction` when friction is off, otherwise append `--friction-slow-seconds` and `--friction-heavy-seconds` with the configured thresholds. Use the refreshed report, including on exit 4, and relay the extract warning; on other failures use the original. Do this freshness check even when friction is off or its gate is empty. Use the report's comparison for matching windows and scopes.
3. **Review.** Use the selected report and ledger with `${CLAUDE_PLUGIN_ROOT}/skills/review/SKILL.md`: fill in measured effects, then keep, tune or revert. A project-scoped `usage-series` and `usage-compare --cutoff <change date>` may supply rates instead of two audit windows.
4. **Outcomes and checks.** Scheduled runs read the precomputed checks and project report; do not run `notes-ledger due`, `rules-lint`, `kaizen-link --check` or `kaizen-project-report`. Those commands are for interactive runs. Follow the project report's calibration proposals; UP or DOWN moves one rung, HOLD keeps the tier and carries its reason. For `DRIFT` or `BROKEN` lines, propose `kaizen-backup begin --skill cycle --ledger <text> <listed-paths>`, then `kaizen-link --apply --replace --only <listed-names>`, then `kaizen-backup finish <change-dir>`; or add intended local names to `localScripts`. For `STALE-CACHE`, scheduled runs propose reinstalling the named plugin or bumping its version. In interactive runs, uninstall and reinstall it with `claude plugin uninstall <plugin> && claude plugin install <plugin>`, or bump its version. Fix stale-rule wording or its pattern. Propose measurements; never run `notes-ledger set` without the owner's OK.
5. **Due checks.** Scheduled runs skip model and release web checks; interactive runs keep them. Scheduled runs read the `## Due checks` lines in this project's `## Experiments: ...` section of the newest `checks-*.md`. Interactive runs use these two separate commands, substituting the path printed by the first into the second:
   - `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kaizen-scheduled checks path --for .`
   - `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/experiment-check --project . --checks --state-file <that path>`
   - For a never-run or overdue check, follow the corresponding models, roster or whats-new skill. Investigate unknown checks.
   - context surface: if the last trim is more than 60 days old, or the audit shows a jump in fixed context, suggest `/agent-kaizen:trim-context`.
   - Friction: interactively, after the freshness check, follow the probe refresh step in `${CLAUDE_PLUGIN_ROOT}/skills/friction/SKILL.md`, then run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/kaizen-scheduled" friction prepare --for . --report <selected-report>`. A failed, disabled or empty preparation skips only friction analysis. Scheduled runs use only the supplied report and optional prepared view. If a view exists, follow the friction skill in the same mode and include its findings in the ranking; do not prepare twice.
6. **Propose.** At most 5 next changes across everything above, ranked by expected saving per unit of effort. For each: the skill that implements it, the risk, and how the next audit will measure it.
7. **Act.**
   - **`propose` mode:** wait for my OK, then run the approved changes one at a time, each with a ledger row.
   - **`safe` and `auto` modes:** don't stop at a proposal list. Take the top proposals the mode allows, up to `maxChangesPerRun`, and carry each one out now. Follow the implementing skill's `SKILL.md` in `${CLAUDE_PLUGIN_ROOT}/skills/<skill>/` in the same mode, with backup, verify, roll back on failure, and a ledger row. "Needs the user's decision" is a reason to skip only for a hard stop, or for a change you can't verify in this run. Pick a smaller, verifiable version of the change when one exists. For example, trim one instruction file rather than all of them.
   - Read "In `auto`, these are NOT reasons to skip a change" in `${CLAUDE_PLUGIN_ROOT}/docs/autonomy.md` before deciding to skip anything.
   - **`propose-only`:** print the proposal and stop.

8. **Record.** After each applied change, add a project ledger row with metric command and review date using `${CLAUDE_PLUGIN_ROOT}/skills/start/SKILL.md`, and run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/notes-ledger add --date <date> --category <category> --change <change> --why <why> --measure <measurement> --source <source>` when `notesLedger` is configured. In scheduled runs, use the given `notes-ledger-path` in place of `${CLAUDE_PLUGIN_ROOT}/scripts/notes-ledger`. Exit 3 means not configured; skip it.

9. **Tidy.** Outside scheduled runs, run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kaizen-scheduled housekeep` once. Mention in the summary how many of the plugin's own old files it removed. In a scheduled run the runner does this; skip it. Use `--dry-run` first if the user asked to see what would go.

## Done when

The ledger is up to date and a short, ranked proposal exists, either applied with your OK or written to the proposal file.
