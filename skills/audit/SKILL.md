---
name: audit
description: "Measure where Claude Code and Codex tokens, turns and time go for this project, and rank the biggest savings."
disable-model-invocation: true
argument-hint: "[propose|safe|auto|yolo]"
---

# Usage audit

Measure where tokens, turns and time actually go, so the changes you make target real costs and not guesses.

**Changes:** writes a report and an audit script. Changes no configuration.

**Autonomy:** follow `${CLAUDE_PLUGIN_ROOT}/docs/autonomy.md`. The mode comes from the skill argument (`propose`, `safe`, `auto` or `yolo`), else `docs/kaizen/config.json`, else `~/.claude/agent-kaizen.json`, else `propose`. In `safe` and `auto`, read every "wait for my OK" below as: apply it yourself if the mode allows (backup, verify, roll back on failure, ledger row), otherwise list it as a proposal. Hard stops always ask. At most `maxChangesPerRun` changes (default 3). End with a summary of what was applied, skipped and rolled back.

## Task

Audit my Claude Code and Codex usage for this project. Don't change any configuration.

Data sources (check which exist):
- Claude Code transcripts: ~/.claude/projects/<this project's folder>/*.jsonl, plus
  subagent transcripts in ~/.claude/projects/<folder>/<session-id>/subagents/*.jsonl.
- Codex sessions: ~/.codex/sessions/**/*.jsonl (tool calls may be logged as
  function_call or custom_tool_call).

Rules:
- Parse with the bundled token-audit script (see Bundled resources), extended if needed,
  never by reading transcripts yourself; they are huge.
- Token usage lives in assistant messages (message.usage: input_tokens,
  cache_creation_input_tokens, cache_read_input_tokens, output_tokens). One message can
  appear on several lines; de-duplicate by message id before summing.
- Cost is roughly context size × number of turns, so report both.

Report, for the last 14 days:
1. Main sessions: turns, peak and median context, total tokens by kind.
2. Per subagent type: spawns, median and p90 tool calls, median context, total tokens.
3. Per tool: call counts; top 20 Bash commands by first word; the largest files read
   whole; images read (count and who read them); URLs fetched more than once.
4. Patterns that waste tokens, each with numbers:
   - long sessions that never compact;
   - wrapper agents that only relay another tool's output;
   - grep → read → grep exploration loops;
   - whole-file reads of big files;
   - planners or reviewers that run far longer than the median;
   - many small agent spawns, each of which wakes the main session.

Write docs/kaizen/audit-<yyyy-mm-dd>.md: a headline (3 lines), the tables above,
and a ranked list of the 10 biggest savings, each with estimated tokens saved per week,
effort (S/M/L), risk, and which prompt or change addresses it. If
docs/kaizen/LEDGER.md exists, fill in "measured effect" for earlier rows that this
audit can now measure.
Finish by recommending the first 3 changes.

## Bundled resources

Start from the bundled audit script instead of writing one: `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/token-audit --project <this project folder name> --days 14 --out docs/kaizen/`. Extend it only if a section below is missing.

## Done when

a dated audit with numbers. For us, the largest items were:
- main-session context of 450k–560k tokens;
- about 150 relay-agent spawns at roughly 80k tokens each;
- planners making 150–200 tool calls each;
- the same history sources fetched hundreds of times.
