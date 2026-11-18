# Research for the merged multi-host plan

Checked 2026-11-17 by the planner, to settle conflicts between `design.md` (Fable) and `design-astra.md` (Astra). Plain facts only; the plan uses them.

## Local probes (codex-cli 0.167.0, isolated `HOME` and `CODEX_HOME` in a temp dir, no sign-in)

| Check | Result |
|---|---|
| `codex plugin marketplace add <local checkout>` then `codex plugin add agent-kaizen@agent-kaizen-tools` | Works. Installs version 0.11.0 from `.claude-plugin/`. |
| Same, with `CODEX_HOME` inside the repo's `out/` | Fails: `failed to create plugin target directory: File name too long (os error 63)`. Codex copies the whole working tree, so a home under the tree recurses. |
| What a local-path install copies | Everything in the working tree, including git-ignored `out/` (287 MB here), `.git` (26 MB) and `.claude/`. A tool that probes a checkout must install from a clean export (`git archive HEAD` into a temp dir outside the tree). |
| `codex plugin marketplace add HighwayofLife/agent-kaizen` then `codex plugin add ...` | Works without sign-in. Cache 25 MB. |
| `codex debug prompt-input` | 22 distinct `agent-kaizen:<name>` skills listed, each with `(file: <root>/<name>/SKILL.md)`. The model is given the skill file's path, so "two levels above this file" resolves the plugin root. |

## Docs and changelog re-read

| Source | Fact |
|---|---|
| https://learn.chatgpt.com/docs/plugins | "The IDE extension doesn't support plugins." Plugins work in Codex CLI and in Codex in the ChatGPT desktop app. |
| https://docs.github.com/en/copilot/reference/hooks-reference | `sessionStart`: "Only `additionalContext` is consumed", top-level. Config-file `userPromptSubmitted` output is dropped. Command `preToolUse` hooks are fail-closed on errors; timeouts are fail-open; default `timeoutSec` 30. Runtime shell tool is `bash`; PascalCase `PreToolUse` payloads report Claude names (`Bash`). |
| https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference | Legacy manifest order `.plugin/`, `plugin.json`, `.github/plugin/`, `.claude-plugin/`; an Agent Plugins root manifest takes precedence. Hooks at `hooks.json` or `hooks/hooks.json`. Install: `copilot plugin install SPEC` (alias `add`); `/plugin` is a dashboard. Installs go to `~/.copilot/installed-plugins/MARKETPLACE/PLUGIN`. Agents shown as `.agent.md`; plain `.md` not stated. |
| Copilot CLI changelog (raw `github/copilot-cli` `changelog.md`, top entry 1.0.113, 2026-11-17) | "Hook config files now support Claude Code's nested matcher/hooks structure and optional type field". "Plugin hooks receive PLUGIN_ROOT, COPILOT_PLUGIN_ROOT, and CLAUDE_PLUGIN_ROOT env vars with the plugin's installation directory". "Fully honor the skill disable-model-invocation flag". "sessionStart hook additionalContext is now injected into the conversation". "Add postToolUseFailure hooks for tool errors". "Improved parsing of VS Code-formatted custom agents with the `.agent.md` suffix". |
| https://code.visualstudio.com/docs/agent-customization/hooks | "The Local harness is deprecated and will be removed in February 2027." Select Copilot in the Session Target control for the Copilot harness. |

## Repo facts

- `.github/workflows/ci.yml:3-6` triggers on `push` of `v*` tags and `workflow_dispatch` only. There is no `pull_request` trigger, so AGENTS.md:19 "CI enforces this on PRs" is not true today. `tools/ci-local` checks that the current version has a CHANGELOG heading; it does not compare against a base.
- `tools/context-budget.json` pins a `sha256` and the literal text of each wired hook (`audit-notice.sh`, `bash-burst.sh`, `session-audit.sh`). Any edit to those hooks must update that file.
- `tests/test_repo.py:60-71` checks every `${CLAUDE_PLUGIN_ROOT}/<path>` reference exists. A preamble that writes `${CLAUDE_PLUGIN_ROOT}` with no `/` after it is not matched.

## Still open (owner checklist in plan.md)

Copilot live behaviour (signed in), Codex live hook run (`agent_id` in subagent tool hooks, quiet `{}` output), Codex IDE session storage, Copilot `async: true` handling, whether Copilot loads `agents/kaizen-auditor.md`.
