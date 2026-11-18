# Brief P03: `docs/hosts.md` runtime host map and the autonomy rule for other hosts

Suggested agent: Terra, low effort. Risk: normal. Size: M. Group A (runs in parallel with P01, P02, P05, P06; you own only docs files listed below).

## Goal and why

Agent Kaizen is a Claude Code plugin (22 Markdown skills, hooks, scripts). Codex CLI and the GitHub Copilot runtime (Copilot CLI, and VS Code with the Copilot harness, which is the same runtime) load the same plugin tree. A later packet (P04) adds a line to every skill: "Not in Claude Code? Read `docs/hosts.md` in the plugin root first." This packet writes that file: one place that says, per host, how to tell you are in it, where its config lives, how skills are invoked, and which Agent Kaizen features work, are degraded, or are unavailable. It also adds the safety rule that on non-Claude hosts the loop only proposes changes to that host's configuration.

Skills read this file at runtime, like `docs/autonomy.md`. Write for a model that must act on it and a human who skims it: short lines, plain words, no marketing language. Every claim not measured must be labelled `unverified` (or `documented, not probed`).

## Plugin root paragraph (goes between the intro and the first `##` section)

Skills tell non-Claude models to read this file first (P04 preamble). So the file must say, in a short paragraph headed in bold `Plugin root`: Claude Code substitutes `CLAUDE_PLUGIN_ROOT` in skill text; on Codex the model is given each skill file's path and the plugin root is the folder that contains `skills/`; on Copilot whether the model is told the skill file's path is unverified, so if the plugin root cannot be resolved, say so in one line and stop that step instead of guessing a path. In every host, wherever a skill uses `CLAUDE_PLUGIN_ROOT` in a command, substitute the resolved plugin root path in quotes.

## Evidence levels (use these words in the file)

- **probed**: run locally on 2026-11-17 against the 0.11.0 tree with `codex-cli 0.167.0`, isolated home, no sign-in.
- **documented**: read in the vendor's current docs or changelog, not run.
- **unverified**: neither. Settled later by the owner's live checks.
Copilot CLI was not installed where the research was done: nothing about Copilot is probed.

## Facts to use (copy these; do not add others without a source)

### Claude Code (as-is, everything works)
- Plugin root is in `CLAUDE_PLUGIN_ROOT` (hooks) and substituted into skill text. Neither `PLUGIN_ROOT` nor `COPILOT_PLUGIN_ROOT` is set. Config dir `${CLAUDE_CONFIG_DIR:-~/.claude}`. Skills `/agent-kaizen:<name>`. Instruction file `CLAUDE.md`. Headless `claude -p`. Session logs `~/.claude/projects/**/*.jsonl` (measured by `token-audit`). Agents in the plugin `agents/` folder.

### Codex CLI (probed unless stated)
- Install: `codex plugin marketplace add HighwayofLife/agent-kaizen`, then `codex plugin add agent-kaizen@agent-kaizen-tools` (probed; no sign-in). Cached at `$CODEX_HOME/plugins/cache/agent-kaizen-tools/agent-kaizen/<version>/` (default `CODEX_HOME` is `~/.codex`).
- Detect: skills are listed as `agent-kaizen:<name>`, invoked `$agent-kaizen:<name>` (or `/skills`). Scripts print skill names as `/agent-kaizen:<name>` in their messages: on Codex, type `$agent-kaizen:<name>` instead. Plugin hooks get `PLUGIN_ROOT` and, for compatibility, `CLAUDE_PLUGIN_ROOT` (documented). The model is handed each skill file's path, so the plugin root is the folder that holds `skills/` (from `skills/<name>/SKILL.md`, go up past `<name>` and `skills`).
- Instruction file `AGENTS.md`. Agents are TOML files in `~/.codex/agents/` or `.codex/agents/` (documented); `agents/kaizen-auditor.md` is NOT loaded (probed). Headless `codex exec`. Session logs `$CODEX_HOME/sessions/YYYY/MM/DD/rollout-*.jsonl` (what `token-audit` reads today; measured). A `codex migrate-rollouts` command may move sessions to "paginated thread history" (documented): the format canary would flag it.
- Skill visibility: Codex ignores `disable-model-invocation`; each skill ships `agents/openai.yaml` with `allow_implicit_invocation: false` so none is listed every turn (probed).
- Hooks: plugin hooks from `hooks/hooks.json` are discovered (4 of 5: `PostToolUseFailure` is not a Codex event and is dropped; probed) and do nothing until the user trusts them in `/hooks`; a release that changes a hook script asks again (documented). `"async": true` is kept (probed). There is no `Read` tool (files are read through the shell), so read guards do not apply.
- `codex-dispatch` has no use inside Codex (Codex handing work to Codex); do the work in the current session.
- Hook output shape: `hookSpecificOutput.additionalContext`, same as Claude Code (documented). Live run: unverified.

### Copilot runtime (Copilot CLI and VS Code Copilot harness) (documented, not probed)
- Install: `copilot plugin marketplace add HighwayofLife/agent-kaizen`, then `copilot plugin install agent-kaizen@agent-kaizen-tools`. Installs to `~/.copilot/installed-plugins/<marketplace>/<plugin>` (or under `$COPILOT_HOME`). VS Code: setting `chat.plugins.enabled`, choose the Copilot session target, run "Chat: Install Plugin from Source" (it also finds the Copilot CLI install).
- Detect: skills `/agent-kaizen:<name>`. Plugin hooks get `PLUGIN_ROOT`, `COPILOT_PLUGIN_ROOT` and `CLAUDE_PLUGIN_ROOT`.
- Instruction files: `AGENTS.md`, `.github/copilot-instructions.md`, `.github/instructions/*.instructions.md`, `~/.copilot/copilot-instructions.md`. Hooks: the plugin's `hooks/hooks.json`, `~/.copilot/hooks/*.json`, `.github/hooks/*.json`. Agents: `.agent.md` files; whether plain `agents/kaizen-auditor.md` loads is unverified. Headless `copilot -p`. Session logs `~/.copilot/session-state/<id>/events.jsonl`: NOT measured in this version (schema undocumented).
- Whether the model is told the skill file's path is unverified (owner check O1); until then, if the plugin root cannot be resolved, stop that step and say so.
- `disable-model-invocation` is honoured (documented changelog entry). Claude's nested `matcher`/`hooks` layout in `hooks/hooks.json` is accepted (documented). `sessionStart` hook output: only top-level `additionalContext` is used (documented). `"async": true` handling: unverified. Hook tool name for Bash may be `bash` (documented); the hook accepts both.
- `codex-dispatch` works if the `codex` CLI is installed (needs sign-in there).

### Not supported
- Codex IDE extension: "The IDE extension doesn't support plugins" (documented). Its sessions may still land in `$CODEX_HOME/sessions` and be measured (unverified).
- Copilot cloud agent: no installed plugins, no local logs.
- VS Code Local harness: deprecated, removed February 2027.

## Per-feature table (put it in the file as `## Feature table`: one row per feature, columns Codex CLI and Copilot runtime, values `works`, `degraded: <reason>`, `not available`, with `(unverified)` where the evidence is not probed; Claude Code needs no column, its section says everything works)

| Feature | Codex CLI | Copilot runtime |
|---|---|---|
| Skills `start scan review cycle autonomy undo flow planning code-map tools-before-tokens test-loop models whats-new roster` | works after the plugin-root preamble (P04) | works (unverified) |
| `audit` skill | works, full Codex data | degraded: runs, reports no Copilot sessions |
| `slim-instructions trim-context lean-agents batch-wakeups schedule` | degraded: text is written for Claude Code settings; use the path map in this file; config changes are propose-only | degraded, same |
| `guardrails` skill | degraded: read guards do not apply (no `Read` tool) | degraded: guard hooks not wired for Copilot yet |
| `codex-dispatch` | not available inside Codex | works if `codex` CLI present (unverified) |
| `audit-notice.sh` (SessionStart notice) | works after `/hooks` trust; wording uses `$agent-kaizen:review` | works (unverified): top-level `additionalContext` |
| `session-audit.sh` (background audit at start) | works after trust (`async` kept, probed) | works (unverified): the script detaches itself |
| `bash-burst.sh` (Bash-call nudge) | degraded: failed-call event dropped (probed); subagent filter unverified | works (unverified): accepts `bash` and `Bash` |
| `limit-big-read.sh`, `block-image-read.sh`, `tier-guard.sh`, `after-compact.sh`, `subagent-context.sh`, `session-notes.sh` | not wired on this host in this version | not wired on this host in this version |
| `token-audit`, `usage-db`, `usage-series`, `usage-compare` | works | degraded: Claude and Codex data only |
| `kaizen-scan`, `kaizen-doctor` | works; host-aware messages | works; host-aware messages |
| `kaizen-scheduled` audit job, `install-schedule` | works | works (measures only Claude and Codex) |
| Scheduled review (`claude -p`) | not available: run the cycle skill by hand when the notice appears | same |
| `kaizen-backup`, `notes-ledger`, `packet-*`, `flow-report`, `brief-lint`, `rules-lint`, `experiment-check` | works | works |
| `agents/kaizen-auditor.md` | not loaded (probed): use `cycle` with `propose-only` | unverified |
| `templates/` | degraded: Claude and Codex templates only | reference only |

Where a skill needs a Claude-only action on another host, the model should say in one line what is not available and continue with the rest.

## State location (decision D1 default, say "for now")

Kaizen state (config `agent-kaizen.json`, audits, backups, the usage database) stays in `${CLAUDE_CONFIG_DIR:-~/.claude}` on every host, so a user of two hosts gets one ledger. A Codex-only or Copilot-only user gets a `~/.claude/` folder that holds only Agent Kaizen files.

## The safety rule

On a host other than Claude Code, changes to that host's settings, hooks and agent files are proposals only, in every autonomy mode (`propose`, `safe`, `auto`), until this file marks the file as verified. Covered files:
- in the host's user config directory: for example `~/.codex/config.toml`, `~/.codex/hooks.json`, `~/.codex/agents/`, `~/.copilot/hooks/`, and the user-level instruction file `~/.copilot/copilot-instructions.md`;
- in the user's project: the host's own settings, hooks and agent folders, for example `.codex/agents/` and `.github/hooks/`.

Not covered (normal autonomy rules apply, git can restore them): the project's git-tracked instruction files (`AGENTS.md`, `.github/copilot-instructions.md`, `.github/instructions/`) and `docs/kaizen/`. Reason for the rule: `kaizen-backup` and `undo` only know Claude paths, so they cannot restore the covered files. No file is marked verified in this version.

Also skip, on other hosts, the steps that only work in Claude Code: edits to Claude Code settings files, `claude ...` commands, `claude plugin ...`, and `kaizen-link`. Say in one line what you skipped, and continue with the rest of the skill. The skill preamble points here; read this section before acting.

## Files

Create: `docs/hosts.md` (target under 200 lines), `docs/plans/2026-11-17-multi-host/changelog/P03.md` (`mkdir -p`).
Edit: `docs/autonomy.md` (one added paragraph only, see below).

`docs/hosts.md` structure: a one-paragraph intro, then exactly these `##` sections, with these exact words in the heading text: `## Claude Code`, `## Codex CLI`, `## Copilot runtime (Copilot CLI and VS Code Copilot harness)`, `## Not supported`, then `## Feature table`, `## State location`, `## Safety rule`. Each host section: a short bullet list in this order: how to tell you are in it; install; config directory; instruction files; agents and hooks; skill invocation; headless command; session logs; notes. Add one line near the top: `KAIZEN_HOST=claude|codex|copilot` overrides host detection in the hooks.

`docs/autonomy.md`: add ONE paragraph at the end of the `## Hard stops (always need a human, in every mode)` list's section (or directly under that list), say: "On hosts other than Claude Code (Codex CLI, Copilot runtime), changes to that host's settings, hooks and agent files (in its user config directory or in the project, for example `.codex/agents/` and `.github/hooks/`) are proposals only in every mode, until docs/hosts.md marks the file as verified. Project instruction files tracked in git, such as `AGENTS.md`, follow the normal rules." The diff to this file must be that one paragraph.

Changelog fragment `changelog/P03.md`, exactly: `- New docs/hosts.md maps Claude Code, Codex CLI and the Copilot runtime (install, invocation, which features work); on non-Claude hosts, changes to the host's own settings, hooks and agent files stay proposals in every autonomy mode.`

Do NOT touch: `.claude-plugin/plugin.json` (version), `CHANGELOG.md` (only P09 edits them), `README.md` (P07), any `SKILL.md` (P04), tests, scripts, hooks. Do not create a test: P04 adds the test that `docs/hosts.md` has the three host headings.

## Acceptance criteria

1. `docs/hosts.md` exists, under 200 lines, with the four host-related `##` sections named above (`rg -c '^## ' docs/hosts.md` is 7).
2. No home-directory absolute paths: only `~` forms (repo privacy test fails on `/Users/<name>` and `/home/<name>/`). No emails.
3. Every claim not probed is labelled `documented` or `unverified` as in the facts above; no claim beyond them.
4. The Codex section states: hooks do nothing until trusted in `/hooks` and a release that changes a hook script asks again; `PostToolUseFailure` is not a Codex event; there is no `Read` tool so read guards do not apply; `codex-dispatch` has no use inside Codex; scripts print `/agent-kaizen:<name>` but on Codex you type `$agent-kaizen:<name>`.
4a. The Safety rule section names which project-scoped host files are covered and which are not (as above), and lists the Claude-only steps to skip. The Plugin root paragraph exists before the first `##`.
5. `git diff -- docs/autonomy.md` is a single added paragraph.
6. Language: plain, short sentences, no marketing words.

## Sandbox and environment (read before running any command)

- Writable temp dir: `mkdir -p out/tmp && export TMPDIR="$PWD/out/tmp"` (`out/` is git-ignored; keep the path short). If `out/` is not writable, use any writable directory outside the repo. Use it for every scratch file and temp directory you create.
- Record every command the environment blocks (read-only file system, no network, no sign-in, missing CLI) as `not run: <reason>`, separately from product failures (a failed assertion, or a non-zero exit from product code). Stop and report only for product failures. Never report a blocked run as a pass.
- Check changed files with `git status --short --untracked-files=all` together with `git diff --stat`: the diff alone omits new files.
- Run narrow unit tests as `PYTHONPATH=tests python3 -m unittest tests.test_x ...` (some test modules import their siblings as top-level modules and fail without it).

## Verification (narrowest first)

```
rg -c '^## ' docs/hosts.md
wc -l docs/hosts.md
rg -n '/Users/|/home/' docs/hosts.md docs/autonomy.md          # no output
PYTHONPATH=tests python3 -m unittest tests.test_repo
git diff --stat -- docs/autonomy.md
git status --short --untracked-files=all
python3 -m unittest discover -s tests
shellcheck -S warning hooks/*.sh
claude plugin validate .
```

## Reporting

Report the files, line counts, and the verify output (trimmed). Note any feature row you could not state from the facts above. Do not commit or push. If a fact here contradicts something you find in the repo, stop and report instead of choosing.
