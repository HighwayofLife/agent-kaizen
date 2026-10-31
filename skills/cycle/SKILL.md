---
name: cycle
description: "Run one full self-improvement cycle: audit, review the ledger, check new models and releases when due, and propose the next changes."
disable-model-invocation: true
argument-hint: "[propose|safe|auto|yolo|propose-only]"
---

# One self-improvement cycle

This is the entry point when you don't know which skill to run. It runs the loop once. With `propose-only` it changes nothing and prints the proposal as Markdown. The scheduler saves it as `cycle-<yyyy-mm-dd>.md` in this project's report folder, printed as `reports` by `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kaizen-scheduled config show --for .`. Run interactively, write it to `docs/kaizen/`.


**Autonomy:** follow `${CLAUDE_PLUGIN_ROOT}/docs/autonomy.md`. The mode comes from the skill argument (`propose`, `safe`, `auto` or `yolo`), else `docs/kaizen/config.json`, else `agent-kaizen.json` in your Claude config dir (`$CLAUDE_CONFIG_DIR` or `~/.claude`), else `propose`. In `safe` and `auto`, read every "wait for my OK" below as: apply it yourself if the mode allows (backup, verify, roll back on failure, ledger row), otherwise list it as a proposal. Hard stops always ask. At most `maxChangesPerRun` changes (default 3). End with a summary of what was applied, skipped and rolled back.

## Task

1. **Find the state.** Read `docs/kaizen/LEDGER.md`. If there is no ledger, run `/agent-kaizen:start` first (in propose-only mode, just say it is missing). In a scheduled `propose-only` or `auto` run, read the report path given after the mode. Otherwise use the newest `token-audit-*.md` in `docs/kaizen/`, then in the folder printed as `reports` by `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kaizen-scheduled config show --for .`. Never use another project's report folder.
2. **Measure.** Outside scheduled runs, if the newest report is older than 3 days and you can run commands, run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/token-audit --cwd . --days 14 --out docs/kaizen/`. Reports with different windows or scopes are not comparable; use the comparison the report itself prints.
3. **Review.** Follow `${CLAUDE_PLUGIN_ROOT}/skills/review/SKILL.md`: fill in the measured effects, then keep, tune or revert. A project-scoped `usage-series` and `usage-compare --cutoff <change date>` may supply the measured rates instead of two audit windows.
4. **Due checks.** Check the dates of the last runs:
   - models: if the last `models-*.md` audit or ledger entry is more than 30 days old, follow `${CLAUDE_PLUGIN_ROOT}/skills/models/SKILL.md`;
   - releases and tools: if the last whats-new run is more than 30 days old, follow `${CLAUDE_PLUGIN_ROOT}/skills/whats-new/SKILL.md`;
   - roster: if `docs/kaizen/model-roster.md` is missing or more than 60 days old, or the audit shows a pool hitting its limits, suggest `/agent-kaizen:roster re-evaluate`;
   - context surface: if the last trim is more than 60 days old, or the audit shows a jump in fixed context, suggest `/agent-kaizen:trim-context`.
5. **Propose.** At most 5 next changes across everything above, ranked by expected saving per unit of effort. For each: the skill that implements it, the risk, and how the next audit will measure it.
6. **Act.**
   - **`propose` mode:** wait for my OK, then run the approved changes one at a time, each with a ledger row.
   - **`safe` and `auto` modes:** don't stop at a proposal list. Take the top proposals the mode allows, up to `maxChangesPerRun`, and carry each one out now. Follow the implementing skill's `SKILL.md` in `${CLAUDE_PLUGIN_ROOT}/skills/<skill>/` in the same mode, with backup, verify, roll back on failure, and a ledger row. "Needs the user's decision" is a reason to skip only for a hard stop, or for a change you can't verify in this run. Pick a smaller, verifiable version of the change when one exists. For example, trim one instruction file rather than all of them.
   - Read "In `auto`, these are NOT reasons to skip a change" in `${CLAUDE_PLUGIN_ROOT}/docs/autonomy.md` before deciding to skip anything.
   - **`propose-only`:** print the proposal and stop.

7. **Tidy.** Outside scheduled runs, run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kaizen-scheduled housekeep` once. Mention in the summary how many of the plugin's own old files it removed. In a scheduled run the runner does this; skip it. Use `--dry-run` first if the user asked to see what would go.

## Done when

The ledger is up to date and a short, ranked proposal exists, either applied with your OK or written to the proposal file.
