---
name: autonomy
description: "Show or set how autonomously Agent Kaizen skills apply changes: propose (default), safe, or auto (alias yolo)."
disable-model-invocation: true
argument-hint: "[propose|safe|auto|yolo] [--project] [--max N] [--allow-installs]"
---

# Set the autonomy mode

The rules for each mode are in `${CLAUDE_PLUGIN_ROOT}/docs/autonomy.md`. Read it before answering.

## Task

1. **No arguments:** show the effective mode and where it comes from, checking in order the project `docs/kaizen/config.json`, then the global `~/.claude/agent-kaizen.json`, then the default. Then show the three modes in one line each, and stop.
2. **A mode given** (`yolo` means `auto`): write it to `~/.claude/agent-kaizen.json`, or to `docs/kaizen/config.json` with `--project`. Merge with the keys already there:
   `{"autonomy": "<mode>", "maxChangesPerRun": <N, default 3>, "allowInstalls": <bool, default false>}`.
   Validate the file with `jq . <file>`.
3. **When the mode is `safe` or `auto`:** tell me plainly, in at most 6 lines, what that means:
   - what will be applied without asking;
   - the hard stops that still ask;
   - that every change is backed up, verified, rolled back if a check fails, and logged in the ledger;
   - `/agent-kaizen:undo`.
4. **Claude Code permissions:** say that tool prompts still apply. Offer, but don't do it without my explicit yes, to help me run with edits auto-accepted:
   - for this session, the acceptEdits permission mode;
   - for the weekly run, `install-schedule --apply --review --auto`.

   Never set `bypassPermissions` and never add broad allow rules.

This skill is the only place the autonomy setting changes. Other skills never change it, in any mode.
