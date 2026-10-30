---
name: planning
description: "Set up plan directories, standalone briefs, right-sized planners and an exploration budget."
disable-model-invocation: true
argument-hint: "[propose|safe|auto|yolo]"
---

# A planning pipeline with right-sized planners

Multi-step work is planned once, in files that every agent can read, by the cheapest planner that fits. Engineers get standalone briefs instead of reconstructing context from the conversation.

**Changes:** templates, planner agent definitions and instruction rules, after you approve.

**Autonomy:** follow `${CLAUDE_PLUGIN_ROOT}/docs/autonomy.md`. The mode comes from the skill argument (`propose`, `safe`, `auto` or `yolo`), else `docs/kaizen/config.json`, else `agent-kaizen.json` in your Claude config dir (`$CLAUDE_CONFIG_DIR` or `~/.claude`), else `propose`. In `safe` and `auto`, read every "wait for my OK" below as: apply it yourself if the mode allows (backup, verify, roll back on failure, ledger row), otherwise list it as a proposal. Hard stops always ask. At most `maxChangesPerRun` changes (default 3). End with a summary of what was applied, skipped and rolled back.

## Task

Set up a planning pipeline for work bigger than one change.

1. Plan directory pattern: docs/plans/<yyyy-mm-dd>-<slug>/plan.md with a packet table
   (id | title | depends on | agent/model/effort | verify commands | status), and
   briefs/NN-<slug>.md, one per packet. The main session keeps the status column current.
2. Brief template. Each brief stands alone:
   - goal and why;
   - files and functions (from the code map, if there is one);
   - what is known;
   - acceptance criteria;
   - exact verify commands;
   - scope limits and what not to touch;
   - "don't commit".
3. Planner routing:
   - small plans (~4 packets that follow an existing pattern): the cheapest capable planner;
   - routine plans (~4–12 packets): mid tier;
   - the top tier only for data model, save format, networking or protocol, security,
     a new system, or more than ~12 packets.
4. Planner budget: tell planners to start from the code map (codemap brief on their input
   file), finish exploring in about 60 tool calls, then write the plan and list
   "Research needed" items instead of exploring forever.
5. One plan-review pass (a different model from the planner, if possible) before any
   coding starts. Its findings go back to the planner once.

Update or create the planner and plan-reviewer agent definitions and the routing rows in
CLAUDE.md. Show the diffs, wait for my OK. Then write a sample plan for my next real
feature so we can try it. Add a ledger row.

## Bundled resources

Templates: `${CLAUDE_PLUGIN_ROOT}/templates/plan/plan.md`, `${CLAUDE_PLUGIN_ROOT}/templates/plan/briefs/01-example.md`, `${CLAUDE_PLUGIN_ROOT}/templates/agents/planner.md`, `${CLAUDE_PLUGIN_ROOT}/templates/agent-context/planning.md`.

## Done when

planners that finish in tens of tool calls, not hundreds, and engineers who rarely need to come back and ask.
