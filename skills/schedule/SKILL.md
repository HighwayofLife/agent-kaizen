---
name: schedule
description: "Schedule the usage audit (and optionally a propose-only review) to run locally every few days, with a session-start notice."
disable-model-invocation: true
---

# Schedule the audit

The audit from `/agent-kaizen:audit` runs by itself every few days, and Claude Code tells you when there's a new one to review. This keeps the loop going without you having to remember it.

**Changes:** a scheduled job and a SessionStart hook, after you approve.

## Task

Turn the usage audit into a scheduled, self-reporting job.

1. Install the bundled token-audit script as ~/.claude/bin/token-audit (copy it, so plugin
   updates don't move it) and confirm that it:
   - it covers all my projects, with a --project filter;
   - it compares against the previous report and prints the change in each headline
     number;
   - it writes ~/.claude/audits/<yyyy-mm-dd>.md;
   - it flags any metric that got worse by more than 20%.
2. Schedule it every 3 days: a launchd agent on macOS (~/Library/LaunchAgents), or cron
   or a systemd user timer on Linux. Log stdout and stderr to ~/.claude/audits/run.log.
   Show me the job file before loading it.
3. The plugin's SessionStart hook (audit-notice.sh) already reports an audit with no
   .reviewed marker. Confirm it fires (start a new session after the first run).
4. Optional, ask me first: a weekly propose-only review run headless
   (install-schedule --review), which writes its proposals to a file and changes nothing.

Test the script once by hand, test the hook with sample input, then install. Add a
ledger row.

## Bundled resources

Bundled: `${CLAUDE_PLUGIN_ROOT}/scripts/token-audit`, `${CLAUDE_PLUGIN_ROOT}/scripts/install-schedule` (launchd on macOS, cron on Linux) and the notice hook `${CLAUDE_PLUGIN_ROOT}/hooks/audit-notice.sh`, which this plugin already enables. See `${CLAUDE_PLUGIN_ROOT}/docs/scheduling.md`.

## Done when

a short notice at the start of a session every few days, with a diff against the last audit.
