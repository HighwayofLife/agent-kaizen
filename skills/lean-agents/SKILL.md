---
name: lean-agents
description: "Make subagents load only the context they need and run on the cheapest model that fits, with a routing table for the main session."
disable-model-invocation: true
---

# Lean subagents and model routing

Each subagent loads only the context its job needs and runs on the cheapest model that does that job well. The main session routes work to it on purpose, not by habit.

**Changes:** edits agent definitions, settings and hooks, after you approve. Back up `~/.claude/agents/` and `~/.claude/settings.json` first.

## Task

Look at my custom agents (~/.claude/agents/*.md and .claude/agents/*.md) and how the main
session uses them (the usage audit in docs/kaizen/ shows spawn counts and cost per type).

For each agent report: model, effort, tools allowlist (or none), what instructions it
loads, and median cost per spawn. Then propose:

1. Model tiers by job:
   - cheapest model: reading code, running commands, judging one specific claim;
   - mid tier: routine coding, tests, routine plans and reviews;
   - top tier: hard debugging, architecture trade-offs, escalations.
   Use "retry once with more effort before moving to a bigger model" as the escalation rule.
2. A tools allowlist for every agent: read-only agents get no Edit or Write.
3. Smaller context. Check the current Claude Code documentation for:
   (a) an agent frontmatter option that stops a subagent loading CLAUDE.md;
   (b) a SubagentStart hook that can add context to a subagent.
   If both exist, propose .claude/agent-context/common.md (the few project rules every
   agent needs) plus one short role file per agent type (coding, planning, review,
   research), injected by a hook script keyed on the agent type. Note that built-in
   general-purpose agents still load everything, so the main session should prefer the
   custom ones.
4. A routing table for the main CLAUDE.md: task shape → agent → model → effort. Keep it
   to about 20 rows.

Back up the files you will touch to a dated folder first. Show every change as a diff and
wait for my OK. Add a ledger row per change.

## Bundled resources

Templates: `${CLAUDE_PLUGIN_ROOT}/templates/agents/*.md` (frontmatter with `omitClaudeMd: true`, tools allowlists), `${CLAUDE_PLUGIN_ROOT}/templates/agent-context/` (common.md, role files, roles.conf) and the hook `${CLAUDE_PLUGIN_ROOT}/hooks/subagent-context.sh`.

## Done when

cheaper spawns and fewer escalations to the top model. The audit shows the effect per agent type.
