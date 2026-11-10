# 02: Bash burst hook

Repo: agent-kaizen (cwd). Do not commit. Do not edit `.claude-plugin/plugin.json` or `CHANGELOG.md`.

## Why
In one week the main session made 5,780 Bash calls returning 6.9M characters; tool results are 79% of its turns. The rule is: a shell investigation over about 5 calls goes to a cheap subagent. A gentle nudge in the moment should cut this.

## Change
1. New `hooks/bash-burst.sh` (bash, needs only `jq`; follow the style of `hooks/block-image-read.sh`, which reads the hook JSON from stdin and tells main from subagent with `.agent_type // "main"`).
   - On `UserPromptSubmit`: reset the counter for this `session_id`.
   - On `PostToolUse` with tool `Bash` and agent_type main: increment a counter in a file under `${TMPDIR:-/tmp}/agent-kaizen-bash-burst/<session_id>` (sanitize the id to `[A-Za-z0-9_-]`). Subagent calls (agent_type set) are ignored.
   - When the count reaches the threshold (env `KAIZEN_BASH_BURST`, default 8) and every further multiple of it, print JSON `{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"..."}}` with a one-sentence message: N Bash calls this turn; hand the rest of the investigation to haiku-scout or haiku-check-runner, or chain steps into one call and print only a summary. Otherwise print nothing.
   - Always exit 0. Never block. Fail open on bad input.
2. Register both events in `hooks/hooks.json` using `${CLAUDE_PLUGIN_ROOT}` like the existing entry.
3. Add tests in `tests/test_hooks.py` following its existing pattern: counts only main Bash calls, warns at the threshold and at 2x, resets on UserPromptSubmit, ignores subagents, bad JSON exits 0 with no output, env threshold honoured.
4. Document the hook in one short paragraph where the other hooks are documented (`rg -n "block-image-read" README.md docs`).

## Verify
`python3 -m unittest tests.test_hooks && shellcheck -S warning hooks/*.sh`
