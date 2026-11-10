---
name: audit
description: "Measure where Claude Code and Codex tokens, turns and time go for this project, and rank the biggest savings."
disable-model-invocation: true
argument-hint: "[propose|safe|auto|yolo]"
---

# Usage audit

Measure where tokens, turns and time actually go, so the changes you make target real costs and not guesses.

**Changes:** writes a report under docs/kaizen/. Changes no configuration.

**Autonomy:** follow `${CLAUDE_PLUGIN_ROOT}/docs/autonomy.md`. The mode comes from the skill argument (`propose`, `safe`, `auto` or `yolo`), else `docs/kaizen/config.json`, else `agent-kaizen.json` in your Claude config dir (`$CLAUDE_CONFIG_DIR` or `~/.claude`), else `propose`. In `safe` and `auto`, read every "wait for my OK" below as: apply it yourself if the mode allows (backup, verify, roll back on failure, ledger row), otherwise list it as a proposal. Hard stops always ask. At most `maxChangesPerRun` changes (default 3). End with a summary of what was applied, skipped and rolled back.

## Task

Audit my Claude Code and Codex usage for this project. Don't change any configuration.

Data sources (check which exist):
- Claude Code transcripts: <Claude config dir>/projects/<this project's folder>/*.jsonl, plus
  subagent transcripts in <Claude config dir>/projects/<folder>/<session-id>/subagents/*.jsonl.
- Codex sessions: <Codex home>/sessions/**/*.jsonl.

Rules:
- Parse with the bundled token-audit script (see Bundled resources), never by reading
  transcripts yourself; they are huge.
- Token usage lives in assistant messages (message.usage: input_tokens,
  cache_creation_input_tokens, cache_read_input_tokens, output_tokens). One message can
  appear on several lines; de-duplicate by message id before summing.
- Cost is roughly context size × number of turns, so report both.

Use the token-audit report for usage and cost sections. When present, use this project's `project-report-*.md` for outcomes, calibration proposals, shadow reviews, slow tests, speed and pending project-ledger rows. Use the global audits folder's `checks-*.md` for drift, stale rules and notes-ledger measurements due.

Report, for the last 14 days, the sections token-audit prints:
1. Totals by model (calls, context, cache-read share, output) and main sessions (calls,
   average and peak context; flagged sessions).
2. By agent type: spawns, median and max tool calls, context, minutes, brief sizes (Claude
   and Codex), cost share, models and effort. Orchestrator turns by trigger.
3. Main-session tool results (count and characters per tool) and image blocks read in the
   main session; top Bash command heads per heavy agent.
4. Codex by model, and by kind, model and effort (sessions, minutes, tokens).
   Changes since the last audit with the same scope, and flagged regressions.
5. `Cost (API-equivalent)`: cache-aware cost by agent type and model, using published
   prices in `scripts/pricing.json`, with shares for cache reads, writes, uncached input
   and output. This is a comparison weight, not a bill; most users have subscriptions.
6. `Stuck turns`: repeated failures (same tool, command or file, and first error line)
   at least 3 times in a turn, with count, share, tool calls, cost and top signatures.
7. `Repeated failures across sessions`: failures in at least 3 sessions per project,
   with a "worked instead" hint when a later command variant succeeded; these are
   repo-fact candidates.
8. `Unused tools and MCP servers`: per project, unused over at least 10 prompts across
   2 sessions, or at least 5 sessions; mark deferred or loaded in full when known.

Not measured by the script: Bash commands of the main session, files read whole, URLs
fetched more than once, who read each image, and the waste patterns (sessions that never
compact, relay wrappers, grep-read loops, many small spawns). Say so in the report where
it matters; rank only what the numbers show.

Write docs/kaizen/audit-<yyyy-mm-dd>.md: a headline (3 lines), the tables above,
and a ranked list of the 10 biggest savings, each with estimated tokens saved per week,
effort (S/M/L), risk, and which prompt or change addresses it. If
docs/kaizen/LEDGER.md exists, fill in "measured effect" for earlier rows that this
audit can now measure. Rank findings from all sections by API-equivalent dollars where
available, and tokens otherwise.
Finish by recommending the first 3 changes.

## Bundled resources

Start from the bundled audit script instead of writing one: `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/token-audit --cwd . --days 14 --out docs/kaizen/`. `--cwd` matches this project's exact path, so it never mixes in similarly named projects; `--project` is a loose substring filter.

## Done when

a dated audit with numbers. For us, the largest items were:
- main-session context of 450k–560k tokens;
- about 150 relay-agent spawns at roughly 80k tokens each;
- planners making 150–200 tool calls each;
- the same history sources fetched hundreds of times.
