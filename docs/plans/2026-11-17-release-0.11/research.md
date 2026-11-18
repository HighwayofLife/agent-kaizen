# Research for 0.11.0

## R2. Always-on context (settled 2026-11-17, Claude Code 2.1.327)

- `claude plugin details agent-kaizen` (0.10.0) reports "Always-on: ~1,200 tok": about 40-70 tokens per skill for 21 skills, plus about 110 for the `kaizen-auditor` agent. It lists the four hooks as "harness-only — no model context cost".
- All 21 `skills/*/SKILL.md` set `disable-model-invocation: true` (`rg -l "disable-model-invocation: true" skills/*/SKILL.md | wc -l` = 21).
- In a live 2.1.327 session with the plugin enabled, the model-visible skill list contains none of the plugin's skills; the agent-type list contains `agent-kaizen:kaizen-auditor` with its description.
- Conclusion: the estimator counts descriptions the model never sees. The real always-on cost is the auditor agent's description (about 110 tokens), plus any SessionStart hook output on the days it prints. The README claim ("skills don't cost context on every turn") is true for skills; it should name the agent's ~110 tokens and say that `plugin details` overcounts skills hidden with `disable-model-invocation`.
- Packet 01's budget check therefore counts: agent descriptions, plus descriptions of any skill without `disable-model-invocation: true`, plus the maximum literal output of each file registered in `hooks/hooks.json`; fail when a skill drops the flag, inventory misses a registered file, or the total exceeds budget. This is a repo-text estimate, not a runtime token measurement.

## R1. Hook payloads (done; Claude Code 2.1.327 documentation)

- Synthetic placeholder fixtures are `tests/fixtures/hooks/pretooluse_agent.json` and `tests/fixtures/hooks/sessionstart.json`. The former has common fields `session_id`, `transcript_path`, `cwd`, `permission_mode`, `hook_event_name`, plus `tool_name`, `tool_use_id`, `tool_input` with `prompt`, `description`, `subagent_type`, optional `model`. Matcher `Agent|Task` is conservative; docs identify `Agent`.
- SessionStart adds `source`: `startup`, `resume`, `clear`, `compact`, or `fork`. No SessionEnd hook is planned.
- PreToolUse denial is exit 0 JSON with `hookSpecificOutput` containing `hookEventName: PreToolUse`, `permissionDecision: deny`, and `permissionDecisionReason`. Do not use `onFailure: block`.
- `"async": true` runs a command hook in the background. Timeout values are seconds, but the CLI does not enforce timeout on an async worker; the worker must enforce its own deadline and clean up its child. Async hooks may be cancelled at teardown in print mode.
- Plugin hooks receive `CLAUDE_PLUGIN_ROOT`, `CLAUDE_PLUGIN_DATA`, and `CLAUDE_PROJECT_DIR`. Source: https://code.claude.com/docs/en/hooks.md

## R3. Backtest

Release follow-up; needs the owner's local database.
