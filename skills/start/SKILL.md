---
name: start
description: "Set up the self-improvement loop in this project: an efficiency ledger, a baseline of what loads every turn, and which skills to run next."
disable-model-invocation: true
---

# Start the loop

Set up the files that turn one-off tune-ups into a loop that keeps improving: an improvements ledger and a baseline.

**Changes:** creates `docs/kaizen/` in your repo. Nothing else.

## Task

I want to set up a self-improving workflow for this project: we regularly measure how
Claude Code (and Codex, if I use it) spends time, tokens and money here, make targeted
changes, and check whether each change paid off.

Set up the scaffolding only, don't change any configuration yet:
1. Create docs/kaizen/LEDGER.md with a table:
   date | change | why (which audit finding) | expected effect | measured effect | keep/revert.
   Add a short header explaining that every efficiency change gets a row, and that the
   "measured effect" column is filled in by the next audit, not by guessing.
2. Create docs/kaizen/README.md describing the loop in five lines:
   measure (audit) → propose → implement one change at a time → re-measure → keep or revert.
3. Tell me which of these exist, with their size in lines and a rough token count
   (characters / 4): CLAUDE.md, AGENTS.md, files they import, ~/.claude/CLAUDE.md,
   ~/.claude/settings.json hooks, ~/.claude/agents/*.md, .claude/agents/*.md,
   ~/.codex/AGENTS.md, ~/.codex/config.toml. Write that list to
   docs/kaizen/baseline-config.md.
4. Add `docs/kaizen/audit-*.md` and `docs/kaizen/token-audit-*.md` to .gitignore (audit
   reports contain paths and prompt fragments; the ledger and README stay tracked).
5. Suggest which of the skills I should run next, based on what you found.
Don't commit; I'll review first.

## Done when

two small docs plus a baseline of what your agents load on every turn.
