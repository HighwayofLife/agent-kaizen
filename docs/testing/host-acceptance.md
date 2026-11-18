# Host acceptance test

You are a coding agent running inside Codex CLI, GitHub Copilot CLI, or VS Code with GitHub Copilot. A human asked you to test whether the Agent Kaizen plugin works on your host. This page is all you need. Follow it step by step and report what happened, PASS or FAIL.

## What this tests

- The plugin installs on your host, and the installed version matches this checkout.
- The installed copy has every skill, hook and script, and the bundled scripts run.
- Agent Kaizen's hooks really fire in a live session on your host: session start, prompt submit, and after a shell command.
- A skill can be invoked by name.
- On Codex, skill descriptions are not loaded into every turn.

`tools/host-acceptance` runs the checks and writes the report. Your part is to install, make three observations, and pass them to `check`.

## Rules

- Run every command from the root of this checkout (the folder that contains `tools/` and `skills/`).
- Do not edit, commit or push any file in this repository.
- Do not change host configuration beyond what `tools/host-acceptance install` does.
- Do not run hook scripts by hand. The live checks must come from your host firing them.
- Report failures as they are. Do not work around a FAIL or retry until it passes. The detail of a failure is the result we need.
- If a command is blocked (sandbox, permission prompt, sign-in, missing CLI), ask the human to approve it, or to run the exact command in a terminal and paste the output back. If it still can't run, record it as `skip:<reason>` where an observation fits, or stop and report what blocked you.

## Prerequisites

- `git`, `python3` 3.9 or newer, and `jq` on PATH. Check with `git --version; python3 --version; jq --version`.
- The host CLI, signed in if your host needs it:
  - Codex: `codex --version`.
  - Copilot CLI: `copilot --version`.
  - VS Code: Copilot Chat signed in. The `copilot` CLI is optional. With it, `install` uses it. Without it, the human installs the plugin by hand (see VS Code below).

## Step 0: find your phase

The test takes two sessions, because a host loads plugin hooks only when a session starts. The human pastes the same prompt both times. Always start with:

```sh
python3 tools/host-acceptance status --host HOST
```

`HOST` is `codex`, `copilot-cli` or `vscode`. The output tells you the phase:

- ``Phase 1: run `install` ``: go to Phase 1.
- ``Phase 2: start a new session, then run `check` ``: go to Phase 2. If you are still in the session that ran `install`, stop and ask the human to start a new session (see the end of Phase 1).
- `Done: report at ...`: the test already ran. Send the report again, or ask the human whether to start over with `install`.

## Phase 1: install (first session)

1. Run `python3 tools/host-acceptance install --host HOST`.
   - By default it copies this checkout to `~/.cache/agent-kaizen-acceptance/source` and installs from there. It never installs from the checkout itself, because Codex copies the whole folder it installs from.
   - If it removes an existing `agent-kaizen-tools` marketplace first, that is expected.
   - `--source github` installs from `HighwayofLife/agent-kaizen` instead. Use it only if the human asks.
   - It also turns on the hook trace by creating `~/.claude/agent-kaizen/host-trace/on`. While that file exists, each Agent Kaizen hook appends one line to `trace.jsonl` in the same folder. The line holds only the event name, the tool name, the payload's key names, and which plugin-root variables are set. It never holds payload values.
2. VS Code without the `copilot` CLI: the command prints manual steps. Ask the human to do them:
   1. Set `chat.plugins.enabled` to true.
   2. Choose Copilot as the chat session target.
   3. Run **Chat: Install Plugin from Source** with the folder or URL that was printed.
3. Stop and tell the human the next step `install` printed. Then end your turn. The human will:
   - Codex: quit Codex, start a new Codex session in this folder, run `/hooks`, and trust the Agent Kaizen hooks. Codex hooks do nothing until they are trusted.
   - Copilot CLI: quit and start a new Copilot CLI session in this folder.
   - VS Code: run **Developer: Reload Window**, then open a new Copilot chat session.

   Then they paste the same prompt again.

## Phase 2: check (second session)

Run `status` first (Step 0). If it says Phase 2, make these observations in order.

1. **Session notice (`notice_seen`).** Look at what your host gave you at session start. Is there text from Agent Kaizen, for example a line about an audit or a review being due?
   - Yes: `pass`.
   - No: `skip:no-audit-due`. The notice only appears when an audit or review is due, so its absence is not a failure. The live hook check below proves the hook ran.
2. **Skills not preloaded (`skills_not_preloaded`).** Look at the skill list your host gave you before you invoked anything.
   - Agent Kaizen skills (names like `agent-kaizen:scan`, `agent-kaizen:audit`) are not listed with their descriptions: `pass`.
   - They are listed: `fail`.
   - You can't see your skill list: `skip:cannot-tell`.
3. **Invoke a skill (`skill_invoked`).** Invoke the doctor skill by name:
   - Codex: `$agent-kaizen:doctor`.
   - Copilot CLI and VS Code: `/agent-kaizen:doctor`. If the host only lets the human type slash commands, ask the human to type it.

   `pass` if the skill loaded and ran `kaizen-doctor`, `fail` if the host did not find the skill or it errored. Put a short reason after a colon, for example `fail:skill-not-found`. This observation is required.
4. **Trigger the shell hook.** Run one command through your host's shell tool, for example `git status`. This fires the after-tool hook. The prompt you were given has already fired the prompt-submit hook.
5. **Run the check:**

   ```sh
   python3 tools/host-acceptance check --host HOST \
     --observe skill_invoked=VALUE \
     --observe notice_seen=VALUE \
     --observe skills_not_preloaded=VALUE
   ```

   Each `VALUE` is `pass`, `fail`, `skip:<reason>` or `fail:<reason>`. The reason uses no spaces, for example `skip:no-audit-due`.
   - If `installed` fails because the plugin is somewhere else (possible with a manual VS Code install), find the folder that holds `.claude-plugin/plugin.json` with `"name": "agent-kaizen"`. Re-run `check` with `--install-dir PATH`.
6. **Turn the trace off:** `python3 tools/host-acceptance cleanup --host HOST`. This removes the trace switch only. It prints the uninstall command but does not run it. Leave the plugin installed unless the human asks.

## What the checks mean

| Check | What it proves | Common cause of FAIL |
|---|---|---|
| `cli` | The host CLI is on PATH (version shown) | CLI missing or not on PATH |
| `installed` | The installed copy exists and its version equals this checkout's | Install failed, an older install is active, or it lives elsewhere (`--install-dir`) |
| `files` | Every skill, hook, `hooks/hooks.json` and, on Codex, every `skills/*/agents/openai.yaml` was installed | The host copied only part of the plugin |
| `scripts` | `kaizen-doctor`, `kaizen-scan` and `token-audit` from the installed copy run | Python missing or too old |
| `doctor` | `kaizen-doctor` sees the install for this host | Install in an unexpected folder |
| `hooks-offline` | The installed hooks give valid output for this host's sample payloads | A hook bug on this host |
| `hooks-live:sessionStart` | Your host ran the session-start hook in this session | Codex: hooks not trusted in `/hooks`. Any host: the session started before the install. |
| `hooks-live:userPromptSubmit` | Your host ran the prompt-submit hook | Same as above |
| `hooks-live:postToolUse` | Your host ran the after-tool hook for a shell command | The hook's `Bash` matcher does not match your host's shell tool name (see the trace) |
| `skill_invoked`, `notice_seen`, `skills_not_preloaded` | Your observations | |

The "Trace combinations" part of the report lists each distinct event, tool name and key set your host sent. Keep it even when everything passes: it records how your host shapes hook payloads.

## What to send back

Reply to the human with:

1. The last line of `check`: `RESULT: PASS|FAIL (n pass, n fail, n skip) report: <path>`.
2. The full Markdown report from that path. It replaces your home folder with `~`.
3. One or two sentences on anything odd that the report does not show: a prompt you had to approve, a step the human did by hand, an error message.
