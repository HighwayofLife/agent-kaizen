---
name: cycle
description: "Run one full self-improvement cycle: audit, review the ledger, check new models and releases when due, and propose the next changes."
disable-model-invocation: true
argument-hint: "[propose-only]"
---

# One self-improvement cycle

This is the entry point when you don't know which skill to run. It runs the loop once. With `propose-only` (used by the scheduled headless run) it changes nothing and prints the proposal as Markdown. The scheduler saves the output to `~/.claude/audits/cycle-<yyyy-mm-dd>.md`; run interactively, write it there yourself.

## Task

1. **Find the state.** Read `docs/kaizen/LEDGER.md` and the newest audits in `docs/kaizen/` and `~/.claude/audits/`. If there is no ledger, run the steps of `/agent-kaizen:start` first (not in propose-only mode: just say it is missing).
2. **Measure.** If the newest audit is older than 3 days and you can run commands, run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/token-audit --project <this project folder> --days 14`. In propose-only runs the scheduler has already run it; use the newest file in `~/.claude/audits/`.
3. **Review.** Follow `${CLAUDE_PLUGIN_ROOT}/skills/review/SKILL.md`: fill in the measured effects, then keep, tune or revert.
4. **Due checks.** Check the dates of the last runs:
   - models: if the last `models-*.md` audit or ledger entry is more than 30 days old, follow `${CLAUDE_PLUGIN_ROOT}/skills/models/SKILL.md`;
   - releases and tools: if the last whats-new run is more than 30 days old, follow `${CLAUDE_PLUGIN_ROOT}/skills/whats-new/SKILL.md`;
   - roster: if `docs/kaizen/model-roster.md` is missing or more than 60 days old, or the audit shows a pool hitting its limits, suggest `/agent-kaizen:roster re-evaluate`;
   - context surface: if the last trim is more than 60 days old, or the audit shows a jump in fixed context, suggest `/agent-kaizen:trim-context`.
5. **Propose.** At most 5 next changes across everything above, ranked by expected saving per unit of effort. For each: the skill that implements it, the risk, and how the next audit will measure it.
6. **Act.** In normal mode, wait for my OK and then run the approved changes one at a time, each with a ledger row. In propose-only mode, print the proposal and stop.

## Done when

The ledger is up to date and a short, ranked proposal exists, either applied with your OK or written to the proposal file.
