---
name: start
description: "Set up the self-improvement loop in this project: an efficiency ledger, a baseline of what loads every turn, and which skills to run next."
disable-model-invocation: true
argument-hint: "[propose|safe|auto|yolo]"
---

# Start the loop

Set up the files that turn one-off tune-ups into a loop that keeps improving: an improvements ledger and a baseline.

**Changes:** creates `docs/kaizen/` and writes `schedule` and `scheduledAutonomy` to `docs/kaizen/config.json` when you answer.

**Autonomy:** follow `${CLAUDE_PLUGIN_ROOT}/docs/autonomy.md`. The mode comes from the skill argument (`propose`, `safe`, `auto` or `yolo`), else `docs/kaizen/config.json`, else `agent-kaizen.json` in your Claude config dir (`$CLAUDE_CONFIG_DIR` or `~/.claude`), else `propose`. In `safe` and `auto`, read every "wait for my OK" below as: apply it yourself if the mode allows (backup, verify, roll back on failure, ledger row), otherwise list it as a proposal. Hard stops always ask. At most `maxChangesPerRun` changes (default 3). End with a summary of what was applied, skipped and rolled back.

## Task

I want to set up a self-improving workflow for this project: we regularly measure how
Claude Code (and Codex, if I use it) spends time, tokens and money here, make targeted
changes, and check whether each change paid off.

Set up the scaffolding and ask about scheduled settings below. In safe or auto mode,
back up every existing file you touch (for example .gitignore) and write a manifest that
lists the files you create, including `docs/kaizen/config.json`, as docs/autonomy.md requires, so /agent-kaizen:undo works:
1. Create docs/kaizen/LEDGER.md with a table:
   date | change | why (which audit finding) | expected effect | measured effect | keep/revert.
   Add a short header explaining that every efficiency change gets a row, and that the
   "measured effect" column is filled in by the next audit, not by guessing.
2. Create docs/kaizen/README.md describing the loop in five lines:
   measure (audit) → propose → implement one change at a time → re-measure → keep or revert.
3. Tell me which of these exist, with their size in lines and a rough token count
   (characters / 4): CLAUDE.md, AGENTS.md, files they import, <Claude config dir>/CLAUDE.md,
   <Claude config dir>/settings.json hooks, <Claude config dir>/agents/*.md, .claude/agents/*.md,
   <Codex home>/AGENTS.md, <Codex home>/config.toml. The Claude config dir is `$CLAUDE_CONFIG_DIR` or `~/.claude`; the Codex home is `$CODEX_HOME` or `~/.codex`. Write that list to
   docs/kaizen/baseline-config.md.
4. Add `docs/kaizen/audit-*.md` and `docs/kaizen/token-audit-*.md` to .gitignore (audit
   reports contain paths and prompt fragments; the ledger and README stay tracked).
5. Ask whether to include this project in the weekly review (`schedule=active` or `schedule=off`; default `active`), then whether the weekly run may apply changes here (`scheduledAutonomy=auto` or `scheduledAutonomy=propose`; default `propose`). Wait for each answer. `docs/kaizen/config.json` may be committed, so `auto` applies to teammates' schedules too. A personal choice belongs in the global setting via `/agent-kaizen:schedule`. Write both answers explicitly, even when they match the defaults, because global settings may override unwritten keys: `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kaizen-scheduled config set --for . schedule=<v> scheduledAutonomy=<v>`. If the Claude config dir's `bin/` has no scheduled runner, suggest `/agent-kaizen:schedule`.
6. Suggest which of the skills I should run next, based on what you found.
Don't commit; I'll review first.

## Done when

two small docs plus a baseline of what your agents load on every turn.
