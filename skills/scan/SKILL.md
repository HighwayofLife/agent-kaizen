---
name: scan
description: "Show a first no-write scorecard of recent local agent usage."
disable-model-invocation: true
argument-hint: "[--demo]"
---

# Scan recent usage

**Plugin root:** `${CLAUDE_PLUGIN_ROOT}`. If that is still a `${...}` placeholder, use the folder that contains `skills/` (this file is `skills/<name>/SKILL.md`), and substitute that path, in quotes, wherever this skill uses `CLAUDE_PLUGIN_ROOT`.
**Not in Claude Code?** Read `docs/hosts.md` in the plugin root first. Skip steps that only work in Claude Code, and follow its propose-only rule before changing any host configuration.

Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/kaizen-scan"` with `--demo` if requested.
Show the scorecard and suggest starting with a warning's named skill. Skipped
checks need more data or a separate inspection. This scan does not enroll a
project, write reports, or require a model audit.
