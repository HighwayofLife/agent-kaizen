---
name: scan
description: "Show a first no-write scorecard of recent local agent usage."
disable-model-invocation: true
argument-hint: "[--demo]"
---

# Scan recent usage

Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/kaizen-scan"` with `--demo` if requested.
Show the scorecard and suggest starting with a warning's named skill. Skipped
checks need more data or a separate inspection. This scan does not enroll a
project, write reports, or require a model audit.
