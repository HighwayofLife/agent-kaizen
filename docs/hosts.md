# Runtime hosts

This map tells models and people how Agent Kaizen runs on each host. **Probed** means run locally on 2026-11-17 against the 0.11.0 tree with `codex-cli 0.167.0`, an isolated home and no sign-in. **Documented** means read in current vendor docs or a changelog, not run. **Unverified** means neither; the owner will check later. Copilot CLI was not installed for the research, so no Copilot claim is probed. `KAIZEN_HOST=claude|codex|copilot` overrides host detection in the hooks.

**Plugin root:** Claude Code substitutes `CLAUDE_PLUGIN_ROOT` in skill text. Codex gives the model each skill file's path; the plugin root is the folder containing `skills/`. Whether Copilot gives the model the skill file's path is unverified. If the root cannot be resolved, say so in one line and stop that step; do not guess. On every host, substitute the resolved plugin root path in quotes wherever a skill uses `CLAUDE_PLUGIN_ROOT` in a command.

## Claude Code

All Agent Kaizen features work on Claude Code.

- Detect: Claude Code; hooks receive `CLAUDE_PLUGIN_ROOT`, not `PLUGIN_ROOT` or `COPILOT_PLUGIN_ROOT`.
- Install: the Claude Code plugin tree.
- Config directory: `${CLAUDE_CONFIG_DIR:-~/.claude}`.
- Instruction file: `CLAUDE.md`.
- Agents and hooks: agents are in the plugin's `agents/` folder; hooks use `CLAUDE_PLUGIN_ROOT`.
- Skills: `/agent-kaizen:<name>`.
- Headless: `claude -p`.
- Session logs: `~/.claude/projects/**/*.jsonl`, measured by `token-audit`.
- Notes: `CLAUDE_PLUGIN_ROOT` is substituted into skill text.

## Codex CLI

Unless marked documented or unverified, these facts were probed as described above.

- Detect: skills are listed as `agent-kaizen:<name>`. Plugin hooks receive `PLUGIN_ROOT` and, for compatibility, `CLAUDE_PLUGIN_ROOT` (documented).
- Install: `codex plugin marketplace add HighwayofLife/agent-kaizen`, then `codex plugin add agent-kaizen@agent-kaizen-tools`. The cache is `$CODEX_HOME/plugins/cache/agent-kaizen-tools/agent-kaizen/<version>/`; default `CODEX_HOME` is `~/.codex`.
- Config directory: `~/.codex` by default; `CODEX_HOME` sets it.
- Instruction file: `AGENTS.md`.
- Agents and hooks: agents are TOML files in `~/.codex/agents/` or `.codex/agents/` (documented). `agents/kaizen-auditor.md` is not loaded. Four of five plugin hooks in `hooks/hooks.json` are discovered; `PostToolUseFailure` is not a Codex event and is dropped. Hooks do nothing until trusted in `/hooks`; a release that changes a hook script asks again (documented). `"async": true` is kept. There is no `Read` tool: files are read through the shell, so read guards do not apply. Hook output uses `hookSpecificOutput.additionalContext` (documented); a live run is unverified.
- Skills: invoke `$agent-kaizen:<name>` or use `/skills`. Scripts print `/agent-kaizen:<name>`; type `$agent-kaizen:<name>` on Codex instead. Codex ignores `disable-model-invocation`; each skill ships `agents/openai.yaml` with `allow_implicit_invocation: false`, so none is listed every turn.
- Headless: `codex exec`.
- Session logs: `$CODEX_HOME/sessions/YYYY/MM/DD/rollout-*.jsonl`, measured by `token-audit` today. `codex migrate-rollouts` may move sessions to paginated thread history (documented); the format canary would flag it.
- Notes: the model receives each skill file's path. From `skills/<name>/SKILL.md`, go up past `<name>` and `skills` to find the plugin root. `codex-dispatch` has no use inside Codex; do the work in the current session.

## Copilot runtime (Copilot CLI and VS Code Copilot harness)

These facts are documented, not probed, unless marked unverified.

- Detect: skills use `/agent-kaizen:<name>`. Plugin hooks receive `PLUGIN_ROOT`, `COPILOT_PLUGIN_ROOT` and `CLAUDE_PLUGIN_ROOT`.
- Install: `copilot plugin marketplace add HighwayofLife/agent-kaizen`, then `copilot plugin install agent-kaizen@agent-kaizen-tools`. The install is under `~/.copilot/installed-plugins/<marketplace>/<plugin>` or `$COPILOT_HOME`. VS Code Agents app sessions use this Copilot CLI install and need the CLI installed and signed in. VS Code chat can instead enable `chat.plugins.enabled`, choose the Copilot session target, and run “Chat: Install Plugin from Source”; that install is for editor chat only.
- Config directory: `~/.copilot` or `$COPILOT_HOME`.
- Instruction files: `AGENTS.md`, `.github/copilot-instructions.md`, `.github/instructions/*.instructions.md`, and `~/.copilot/copilot-instructions.md`.
- Agents and hooks: agents use `.agent.md` files; whether plain `agents/kaizen-auditor.md` loads is unverified. Hooks use the plugin's `hooks/hooks.json`, `~/.copilot/hooks/*.json`, and `.github/hooks/*.json`. Claude's nested `matcher`/`hooks` layout is accepted. `sessionStart` uses only top-level `additionalContext`. Handling of `"async": true` is unverified. The Bash tool name may be `bash`; the hook accepts `bash` and `Bash`.
- Skills: `/agent-kaizen:<name>`. `disable-model-invocation` is honoured.
- Headless: `copilot -p`.
- Session logs: `~/.copilot/session-state/<id>/events.jsonl`; not measured in this version, and the schema is undocumented.
- Notes: whether the model receives the skill file's path is unverified (owner check O1). If the plugin root cannot be resolved, say so and stop that step. `codex-dispatch` works if the `codex` CLI is installed and signed in (unverified).

## Not supported

- Codex IDE extension: plugins are not supported (documented). Its sessions may still land in `$CODEX_HOME/sessions` and be measured (unverified).
- Copilot cloud agent: no installed plugins and no local logs (documented, not probed).
- VS Code Local harness: deprecated and removed in February 2027 (documented, not probed).

## Feature table

Copilot values are documented, not probed, unless marked unverified. A skill that needs a Claude-only action on another host should say in one line what is unavailable and continue with the rest.

| Feature | Codex CLI | Copilot runtime |
|---|---|---|
| Skills `start scan review cycle autonomy undo flow planning code-map tools-before-tokens test-loop models whats-new roster` | works after the plugin-root preamble (P04) | works (unverified) |
| `audit` skill | works, full Codex data | degraded: runs, reports no Copilot sessions |
| `slim-instructions trim-context lean-agents batch-wakeups schedule` | degraded: text is written for Claude Code settings; use the path map here; config changes are propose-only | degraded: same |
| `guardrails` skill | degraded: read guards do not apply; no `Read` tool | degraded: guard hooks not wired for Copilot yet |
| `codex-dispatch` | not available inside Codex | works if `codex` CLI is present (unverified) |
| `audit-notice.sh` (SessionStart notice) | works after `/hooks` trust; wording uses `$agent-kaizen:review` | works (unverified): top-level `additionalContext` |
| `session-audit.sh` (background audit at start) | works after trust (`async` kept, probed) | works (unverified): the script detaches itself |
| `bash-burst.sh` (Bash-call nudge) | degraded: failed-call event dropped (probed); subagent filter unverified | works (unverified): accepts `bash` and `Bash` |
| `limit-big-read.sh`, `block-image-read.sh`, `tier-guard.sh`, `after-compact.sh`, `subagent-context.sh`, `session-notes.sh` | not available: not wired on this host in this version | not available: not wired on this host in this version |
| `token-audit`, `usage-db`, `usage-series`, `usage-compare` | works | degraded: Claude and Codex data only |
| `kaizen-scan`, `kaizen-doctor` | works; host-aware messages | works; host-aware messages |
| `kaizen-scheduled` audit job, `install-schedule` | works | works; measures only Claude and Codex |
| Scheduled review (`claude -p`) | not available: run the cycle skill by hand when the notice appears | not available: run the cycle skill by hand when the notice appears |
| `kaizen-backup`, `notes-ledger`, `packet-*`, `flow-report`, `brief-lint`, `rules-lint`, `experiment-check` | works | works |
| `agents/kaizen-auditor.md` | not available: not loaded (probed); use `cycle` with `propose-only` | unverified |
| `templates/` | degraded: Claude and Codex templates only | degraded: reference only |

## State location

For now, Kaizen state stays in `${CLAUDE_CONFIG_DIR:-~/.claude}` on every host. This includes `agent-kaizen.json`, audits, backups and the usage database. Users of two hosts get one ledger. A Codex-only or Copilot-only user gets a `~/.claude/` folder holding only Agent Kaizen files.

## Safety rule

On hosts other than Claude Code, changes to that host's settings, hooks and agent files are proposals only in every autonomy mode (`propose`, `safe`, `auto`), until this file marks the file as verified. No file is marked verified in this version. `kaizen-backup` and `undo` know only Claude paths and cannot restore the covered files.

Covered files include those in the host's user config directory, such as `~/.codex/config.toml`, `~/.codex/hooks.json`, `~/.codex/agents/`, `~/.copilot/hooks/`, and `~/.copilot/copilot-instructions.md`. They also include the host's own project settings, hooks and agent folders, such as `.codex/agents/` and `.github/hooks/`.

The project's git-tracked instruction files, including `AGENTS.md`, `.github/copilot-instructions.md` and `.github/instructions/`, and `docs/kaizen/` are not covered. Normal autonomy rules apply; git can restore them.

On other hosts, also skip Claude Code settings edits, `claude ...` commands, `claude plugin ...`, and `kaizen-link`. Say in one line what you skipped, then continue with the rest of the skill. Read this section before acting.

For live host checks, see [host acceptance](testing/host-acceptance.md).
