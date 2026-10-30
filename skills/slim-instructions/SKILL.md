---
name: slim-instructions
description: "Shrink CLAUDE.md, AGENTS.md and their imports, which are re-sent every turn, without losing a rule."
disable-model-invocation: true
---

# Slim the always-loaded instructions

`CLAUDE.md`, `AGENTS.md` and everything they import are sent with every turn of every session. Shrinking them saves tokens on every turn, so even a small cut adds up across a whole session.

**Changes:** edits instruction files, after you approve.

## Task

Review the instructions that load automatically: CLAUDE.md (project and ~/.claude/),
any @-imported files, AGENTS.md and ~/.codex/AGENTS.md. First measure each one
(lines, characters / 4 ≈ tokens).

Then propose a restructure:
- A short core file with only what nearly every task needs: purpose, architecture
  invariants, build and test commands, hard "never" rules.
- Topic docs (for example engine, assets, UI text, networking, release) that agents read
  only when the task matches. List them in the core file with a one-line "read this
  when …" each.
- Orchestration-only process (worktrees, review rules, merge and release steps) in a file
  imported only by the main session, so subagents and Codex don't carry it.
- Remove duplicates, rules contradicted by later rules, dated stories (move rationale to
  a rationale doc), and anything the code or tooling already enforces.
- Keep every rule's meaning. List each rule you dropped or merged and why.

Show a before/after token estimate per file and the full diff. Wait for my OK before
writing. After applying, add a row to docs/kaizen/LEDGER.md.

## Bundled resources

Starting templates: `${CLAUDE_PLUGIN_ROOT}/templates/global-CLAUDE.md`, `${CLAUDE_PLUGIN_ROOT}/templates/project-CLAUDE.md`, `${CLAUDE_PLUGIN_ROOT}/templates/orchestrator.md`, `${CLAUDE_PLUGIN_ROOT}/templates/codex-AGENTS.md`. Background: `${CLAUDE_PLUGIN_ROOT}/docs/what-we-learned.md`.

## Done when

the core files usually shrink by 40–70%, with no rule lost.
