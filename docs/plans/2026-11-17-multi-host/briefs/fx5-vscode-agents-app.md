# FX5: VS Code findings from the first live acceptance run

Agent: Terra, effort medium. Risk: normal. Do not commit or push.

## What the live run showed (macOS, VS Code Insiders, no `copilot` CLI on PATH)

The owner ran the acceptance test from the **VS Code Agents app** with Copilot. `tools/host-acceptance install --host vscode` found no `copilot` CLI and printed the manual steps. The plugin was then installed with "Chat: Install Plugin from Source", which:

- added `"chat.pluginLocations": {"<export dir>": true}` to the VS Code user `settings.json`, and
- copied the plugin to `~/Library/Application Support/Code - Insiders/agentPlugins/file-<path-slug>/<hash>/` (the slug comes from the source path, for example `file-Users-<name>-cache-agent-kaizen-acceptance-source`).

`check` then failed: `installed`, `files`, `scripts` and `hooks-offline` looked only in `~/.copilot/installed-plugins/...`; the trace stayed empty (no hooks fired); the agent could not invoke the skill.

Cause: the Agents app does not run the agent in VS Code. It runs a Copilot runtime agent host (log lines in `~/.copilot/logs/process-*.log` say `copilot_runtime`, `standalone_host`, and "retaining host-global plugins"). That runtime loads plugins from `~/.copilot` (`installed-plugins/` plus `enabledPlugins` in `~/.copilot/settings.json`). VS Code syncs only MCP servers into it (`agentPlugins/vscode-synced-customization-agent-host-copilotcli-*/` hold just `.plugin/plugin.json` and `.mcp.json`). So a plugin installed through VS Code reaches VS Code's own chat, not Agents-app sessions. VS Code ships `bin/copilot-shim/copilot`, but it only says "GitHub Copilot CLI was not found" until the real Copilot CLI is installed.

## Changes

1. **Split the VS Code host in two in the docs and tool output.** "VS Code chat" (the Chat view in the editor) and "VS Code Agents app" (Copilot runtime agent host). Keep the single `--host vscode` value.
   - `install --host vscode` without the `copilot` CLI: print both paths. For the Agents app: "The Agents app loads plugins only from the Copilot CLI install (~/.copilot). Install GitHub Copilot CLI (see https://docs.github.com/en/copilot/how-tos/copilot-cli/set-up-copilot-cli/install-copilot-cli), then run install again." For VS Code chat: the existing manual steps. Record `install: manual` as today.
   - With the `copilot` CLI present, behaviour is unchanged (it installs into `~/.copilot`, which both the CLI and the Agents app use).
2. **`check --host vscode` finds a VS Code install by itself.** When `--install-dir` is not given and the Copilot CLI location has no install, look for `agentPlugins/*/*/.claude-plugin/plugin.json` with `"name": "agent-kaizen"` under the VS Code user-data folders for stable and Insiders: macOS `~/Library/Application Support/Code` and `Code - Insiders`; Linux `${XDG_CONFIG_HOME:-~/.config}/Code` and `Code - Insiders`; Windows `%APPDATA%/Code` and `Code - Insiders`. Pick the most recently modified match. Say in the `installed` detail which location was used (redacted). If both a `~/.copilot` install and a VS Code install exist, prefer `~/.copilot` and mention the other.
   - If the install found is a VS Code chat install (agentPlugins) and no hook trace lines exist, add to the `hooks-live:*` hint: `plugin is installed for VS Code chat only; Agents-app sessions load plugins from ~/.copilot (install the Copilot CLI)`.
3. **The installed copy contained the whole export** (`tests/`, `tools/`, `docs/plans/`, etc.) because "Install Plugin from Source" copies the folder. Not a failure; no change, but the `files` check must still pass for that layout.
4. **Docs** (`docs/testing/host-acceptance.md`, and the VS Code row/section in `docs/hosts.md`):
   - Prerequisites: VS Code Agents app needs the GitHub Copilot CLI installed and signed in; VS Code chat does not.
   - Phase 1 for VS Code: which path to take, and that the agent should ask the human which surface they are using if unclear.
   - Phase 2 restart step: Agents app: start a new agent session; VS Code chat: Developer: Reload Window, then a new chat.
   - Troubleshooting entry with the cause above in two or three plain sentences.
   - Keep docs plain and short. In `docs/hosts.md` only adjust the VS Code text; do not restructure the file.
5. **Tests** in `tests/test_host_acceptance.py`: a fake VS Code user-data dir with an `agentPlugins/file-x/<hash>/` install is found by `check` (use an env override for the VS Code data roots, for example `KAIZEN_VSCODE_DATA_DIRS` with os.pathsep-separated paths, so tests never touch the real folders); the `~/.copilot` install wins when both exist; the Agents-app hint appears when the install is agentPlugins and the trace is empty; `install --host vscode` without a CLI prints the Copilot CLI instruction.

## Scope

Allowed files: `tools/host-acceptance`, `tests/test_host_acceptance.py`, `docs/testing/host-acceptance.md`, `docs/testing/prompts.md` (only if the VS Code prompt needs a word changed), `docs/hosts.md`. `docs/hosts.md` is read at runtime by skills, so add one bullet to the `## 0.12.0` CHANGELOG entry under the existing `docs/hosts.md` group describing the VS Code Agents app note; do not bump the version (0.12.0 is unreleased). Do not touch hooks, skills, scripts or manifests.

## Verify

```
PYTHONPATH=tests python3 -m unittest tests.test_host_acceptance tests.test_repo tests.test_host_probe
python3 tools/host-acceptance --help
shellcheck -S warning hooks/*.sh hooks/lib/*.sh
```

Sandbox note: do not read or write the real VS Code or `~/.copilot` folders; use temp dirs and the env override.
