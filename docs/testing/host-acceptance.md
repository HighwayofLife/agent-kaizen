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
  - VS Code Agents app: GitHub Copilot CLI installed and signed in (`copilot --version`).
  - VS Code chat: Copilot Chat signed in; the Copilot CLI is not required.

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
   - If it removes an existing `agent-kaizen-tools` marketplace first, it also uninstalls the plugin first; that is expected.
   - `--source github` installs from `HighwayofLife/agent-kaizen` instead. Use it only if the human asks.
   - It also turns on the hook trace by creating `~/.claude/agent-kaizen/host-trace/on`. While that file exists, each Agent Kaizen hook appends one line to `trace.jsonl` in the same folder. The line holds only the event name, the tool name, the payload's key names, and which plugin-root variables are set. It never holds payload values.
2. For VS Code, ask the human whether they use the Agents app or the editor Chat view if unclear. The Agents app needs the signed-in Copilot CLI; install it and run `install` again if it is missing. For VS Code chat without the CLI, `install` registers the local plugin in each existing VS Code user settings directory and backs up any settings file it changes. Follow any printed instructions for settings that need manual attention, and choose Copilot as the chat session target. Use `--print-only` to print the manual install steps instead. If no VS Code data directory exists, or the source is GitHub, the command prints those steps.
3. Stop and tell the human the next step `install` printed. Then end your turn. The human will:
   - Codex: quit Codex, start a new Codex session in this folder, run `/hooks`, and trust the Agent Kaizen hooks. Codex hooks do nothing until they are trusted.
   - Copilot CLI: quit and start a new Copilot CLI session in this folder.
   - VS Code Agents app: start a new agent session.
   - VS Code chat: run **Developer: Reload Window**, then open a new chat.

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
3. **Invoke a skill (`skill_invoked`).** Invoke the scan skill in demo mode:
   - Codex: `$agent-kaizen:scan --demo`.
   - Copilot CLI and VS Code: `/agent-kaizen:scan --demo`. Type it in an interactive session: headless `copilot -p` does not run slash commands, and `/scan` without the prefix is unknown. Copilot hides user-only skills from the model.

   `pass` if the skill loaded and ran `scripts/kaizen-scan` and printed a demo scorecard, `fail` if the host did not find the skill or it errored. Put a short reason after a colon, for example `fail:skill-not-found`. This observation is required and cannot be skipped. If the host cannot invoke it, report `fail:<reason>`.
4. **Trigger the shell hook.** Run one command through your host's shell tool, for example `git status`. This fires the after-tool hook. The prompt you were given has already fired the prompt-submit hook.
5. **Run the check:**

   ```sh
   python3 tools/host-acceptance check --host HOST \
     --observe skill_invoked=VALUE \
     --observe notice_seen=VALUE \
     --observe skills_not_preloaded=VALUE
   ```

   Each `VALUE` is `pass`, `fail` or `fail:<reason>`. The optional observations also accept `skip:<reason>`. The reason uses no spaces, for example `skip:no-audit-due`.
   - If `installed` fails because the plugin is somewhere else (possible with a VS Code chat install), find the folder that holds `.claude-plugin/plugin.json` with `"name": "agent-kaizen"`. Re-run `check` with `--install-dir PATH`.
6. **Turn the trace off:** `python3 tools/host-acceptance cleanup --host HOST`. This removes the trace switch only. It prints the uninstall command but does not run it. Leave the plugin installed unless the human asks.

## What the checks mean

| Check | What it proves | Common cause of FAIL |
|---|---|---|
| `cli` | The host CLI is on PATH (version shown) | CLI missing or not on PATH |
| `installed` | The installed copy exists and its version equals this checkout's | Install failed, an older install is active, or it lives elsewhere (`--install-dir`) |
| `files` | Every skill, hook, `hooks/hooks.json` and, on Codex, every `skills/*/agents/openai.yaml` was installed | The host copied only part of the plugin |
| `scripts` | `kaizen-doctor`, `kaizen-scan` and `token-audit` from the installed copy run | Python missing or too old |
| `doctor` | `kaizen-doctor` sees the install for this host; VS Code chat installs may skip this check | Install in an unexpected folder |
| `hooks-offline` | The installed hooks give valid output for this host's sample payloads | A hook bug on this host |
| `hooks-live:sessionStart` | This host ran the session-start hook; the report counts session starts | Codex: hooks not trusted in `/hooks`. Any host: the session started before the install. |
| `hooks-live:userPromptSubmit` | This host ran the prompt-submit hook | Same as above |
| `hooks-live:postToolUse` | This host ran the after-tool hook for a shell command | The hook's `Bash` matcher does not match your host's shell tool name (see the trace) |
| `skill_invoked`, `notice_seen`, `skills_not_preloaded` | Your observations | |

Only trace lines from this host count. Multiple session starts mean several sessions contributed.

The "Trace combinations" part of the report lists each distinct event, tool name and key set your host sent. Keep it even when everything passes: it records how your host shapes hook payloads.

## Troubleshooting VS Code

For VS Code chat, `install` registers the local source in user settings and backs up changed settings files. Run **Developer: Reload Window**, then open a new chat. Use `--print-only` for manual install instructions. Cleanup prints how to remove the registration or restore a backup.

Local-directory marketplace installs are live: Copilot loads the plugin in place, and `check` reports that location.

The Agents app runs a Copilot runtime agent host that loads plugins from `~/.copilot`, while an install from source in VS Code reaches editor chat. VS Code syncs MCP servers to the agent host, not plugins. Install and sign in to the GitHub Copilot CLI, then run the install again for Agents-app sessions.

## What to send back

Reply to the human with:

1. The last line of `check`: `RESULT: PASS|FAIL (n pass, n fail, n skip) report: <path>`.
2. The full Markdown report from that path. It replaces your home folder with `~`.
3. One or two sentences on anything odd that the report does not show: a prompt you had to approve, a step the human did by hand, an error message.
