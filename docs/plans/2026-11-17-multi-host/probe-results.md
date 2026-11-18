## Automated run

2026-11-17; `codex-cli 0.167.0`.

Command: `TMPDIR=/private/tmp tools/host-probe --host codex --timeout 15`

```text
PASS codex cli version: codex-cli 0.167.0
PASS codex marketplace add: Added marketplace agent-kaizen-tools
PASS codex plugin add: Installed plugin root: <tmp>/codex/plugins/cache/agent-kaizen-tools/agent-kaizen/0.11.0
PASS codex installed version: 0.11.0
FAIL codex skills hidden: 22 listed
PASS codex hooks discovered: 4 hooks: postToolUse, sessionStart, sessionStart, userPromptSubmit
```

The CLI also warned that it could not create PATH aliases under the temporary directory.

## Owner checks

| Check | Result | Date and version | Notes |
| --- | --- | --- | --- |
| O1 Copilot CLI and VS Code: Check `/skills` lists `agent-kaizen:*` without unprompted invocation; confirm hooks load, `SessionStart` matcher `startup\|resume` fires and shows the audit notice; record how `async: true` behaves; call `Bash` eight times in one turn and record the nudge and `tool_name`; check auditor agent loading and `model: sonnet`; check whether the model receives the skill folder path. Capture raw hook payload keys, event names and `tool_name` casing for every wired hook; check whether matcher `Bash` receives `bash` events (otherwise C1 applies). After P04, invoke a skill from an unrelated project and check plugin path resolution and bundled script execution. Repeat the install in VS Code with the Copilot session target. | | | |
| O2 Codex CLI live session: Trust hooks in `/hooks`; check the start notice and quiet `{}` output; check whether subagent tool hooks carry `agent_id`; run `$agent-kaizen:scan` from the cached plugin root; capture raw hook payload keys and event names. After P04, invoke a skill from an unrelated project and check plugin path resolution. | | | |
| O3 Codex IDE extension: Check whether IDE sessions land in `$CODEX_HOME/sessions` for `token-audit`. | | | |
| O5 Before release, outside the sandbox: Run `tools/host-probe --host all --worktree` and `tools/ci-local --python 3.9` with network, Python 3.9 and real CLIs; paste output. | | | |
