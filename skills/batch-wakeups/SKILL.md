---
name: batch-wakeups
description: "Cut main-session turns by batching agent completions through a swarm lead and merged reviews."
disable-model-invocation: true
---

# Batch the wake-ups

Each time a subagent finishes, the main session takes a full turn with its whole context. Ten small agents mean ten expensive turns. A lead agent can gather the results first and wake the main session once.

**Changes:** agent definitions and routing rows, after you approve.

## Task

Use the usage audit (docs/kaizen/) to find where the main session spawns many small
agents: one per finding to verify, one per file to read, one per URL, and so on. Also find
pairs of agents that always run back to back, such as a code verifier followed by a
second-model review.

Propose:
1. A "swarm lead" agent: it takes N items plus the per-item question and output shape,
   spawns one cheap worker per item in parallel, does no item itself, waits for all of
   them, writes full results to a file, and returns ONE merged table.
2. Merged reviews: the verifier starts the second review (for example a Codex diff review
   script) in the background itself and merges its findings, so the main session wakes once.
3. A rule in CLAUDE.md: "handle each completion in one response: integrate, update the
   plan, launch every next task", and "wait for notifications, never poll".

Estimate main-session turns saved per week from the audit numbers. Show diffs, wait for
my OK. Add a ledger row.

## Bundled resources

Templates: `${CLAUDE_PLUGIN_ROOT}/templates/agents/swarm-lead.md`, `${CLAUDE_PLUGIN_ROOT}/templates/agents/judge.md`, `${CLAUDE_PLUGIN_ROOT}/templates/agents/scout.md`, `${CLAUDE_PLUGIN_ROOT}/templates/agents/verifier.md`.

## Done when

fewer main-session turns per unit of work. The next audit shows this as a lower turn count at a similar context size.
