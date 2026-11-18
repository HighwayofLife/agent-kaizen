# T1: host acceptance test kit (Codex CLI, Copilot CLI, VS Code Copilot)

Agent: Terra, effort medium. Risk: normal. Do not commit or push.

## Goal

The owner will hand a short prompt to a coding agent running inside Codex CLI, Copilot CLI or VS Code (Copilot harness). That agent must find everything it needs in this repo: install the plugin on its own host, run the checks, and report one clear PASS or FAIL with a report file. This covers owner checks O1 (Copilot CLI and VS Code: install, skill invocation, hook event names and payload keys) and O2 (live Codex hook run) from `docs/plans/2026-11-17-multi-host/plan.md`.

Hooks load only when a session starts, so the test runs in two sessions of the host. One prompt is used both times: the agent runs `tools/host-acceptance status`, which says which phase is next.

## Deliverables

### 1. Opt-in hook trace (hooks/audit-notice.sh, hooks/bash-burst.sh, hooks/session-audit.sh)

- Trace is on only while the file `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/agent-kaizen/host-trace/on` exists. When it does not exist, each hook must behave exactly as now: same stdout, stderr, exit code, and no extra reads of stdin beyond what the hook already does. The only added cost is one file-existence test.
- When trace is on, append one JSON line to `.../host-trace/trace.jsonl`: `ts` (UTC ISO), `hook` (script basename), `host` (the hook's existing detected `kaizen_host`), `event` (from the payload: `hook_event_name`, or whatever event field the host's payload has, else null), `tool` (tool name if present, else null), `keys` (sorted top-level payload keys), `env` (sorted names, not values, of which of `PLUGIN_ROOT`, `COPILOT_PLUGIN_ROOT`, `CLAUDE_PLUGIN_ROOT`, `KAIZEN_HOST`, `CODEX_HOME`, `COPILOT_HOME` are set). Never write payload values other than event and tool name (privacy).
- If a hook does not read stdin today, read it only when trace is on. If it does, reuse the value it already read. Use jq when present; without jq write the line with `keys: null` and `"note": "jq missing"`. Any trace error is ignored: the hook's own output and exit code never change.
- Factor the trace code into one small shared bash file sourced by the three hooks (for example `hooks/lib/trace.sh`), if sourcing works with how hooks locate themselves; otherwise duplicate a short block. `shellcheck -S warning hooks/*.sh` (and the lib file) must stay clean. `hooks/hooks.json` must stay byte-identical (`git diff --exit-code d1accc4 -- hooks/hooks.json`).
- Tests: extend the existing hook tests (see `tests/test_hooks.py` and the fixtures in `tests/fixtures/hooks/{codex,copilot}_*.json`) so that (a) with trace off, Claude, Codex and Copilot output is unchanged and no trace file appears; (b) with trace on, each fixture gives one trace line with the right `event`, `tool`, `host` and `keys`, and stdout is identical to trace off. Run hook tests with `CLAUDE_CONFIG_DIR` pointed at a temp dir.
- If `tools/context-budget.json` pins hook hashes, update it with the existing tool (`tools/context_budget.py`) the way P05 did, and keep the byte budget unchanged.

### 2. `tools/host-acceptance` (Python 3.9, stdlib only, executable, answers `--help`)

Subcommands, all taking `--host codex|copilot-cli|vscode`:

- `status`: reads the state file and prints the next step in plain words ("Phase 1: run `install`", "Phase 2: start a new session, then run `check`", "Done: report at ..."). State lives in `${CLAUDE_CONFIG_DIR:-~/.claude}/agent-kaizen/host-acceptance/<host>.json`.
- `install [--source local|github]`: default `local`. `local` exports the current checkout's tracked and untracked-not-ignored files (same approach as `tools/host-probe --worktree`, including its symlink rule; reuse its code by import or copy) into a stable folder `${XDG_CACHE_HOME:-~/.cache}/agent-kaizen-acceptance/source` (replace it each run). Never install from the checkout itself: Codex copies the whole tree and fails on `out/`. Then run the host's install commands against that folder: Codex `codex plugin marketplace add <dir>` and `codex plugin add agent-kaizen@agent-kaizen-tools`; Copilot CLI `copilot plugin marketplace add <dir>` and `copilot plugin install agent-kaizen@agent-kaizen-tools`. `github` uses `HighwayofLife/agent-kaizen` instead of the folder. For `vscode`: if the `copilot` CLI exists, install with it (VS Code finds Copilot CLI installs, see docs/hosts.md); otherwise print the manual steps from docs/hosts.md for the owner and record `install: manual`. If a marketplace with that name already exists, remove or update it first so the new source is used (check `--help` of both CLIs for the right subcommand; do not guess flags; if unsure, print the command for the human). Then create the trace switch file, empty the old trace, record the install time in state, and print the phase-2 instructions, including for Codex: "run /hooks in the new session and trust the Agent Kaizen hooks".
- `check [--install-dir PATH] [--observe NAME=pass|fail|skip[:note]]...`: runs all checks below and writes the report. Exit 0 when no check FAILs, 1 otherwise.
- `cleanup`: removes the trace switch file (keeps trace and reports), and prints the uninstall commands for the host without running them.

Checks in `check` (each a row: id, PASS/FAIL/SKIP, detail):

1. `cli`: the host CLI is on PATH and its version (SKIP for vscode when no copilot CLI).
2. `installed`: the installed copy is found (Codex: `${CODEX_HOME:-~/.codex}/plugins/cache/agent-kaizen-tools/agent-kaizen/<version>`; Copilot: `${COPILOT_HOME:-~/.copilot}/installed-plugins/agent-kaizen-tools/agent-kaizen`; `--install-dir` overrides) and its `.claude-plugin/plugin.json` version equals the checkout's.
3. `files`: the installed copy has every `skills/*/SKILL.md` the checkout has, the hooks, `hooks/hooks.json` identical to the checkout's, and (Codex) every `skills/*/agents/openai.yaml`.
4. `scripts`: `kaizen-doctor`, `kaizen-scan` and `token-audit` from the installed copy answer `--help` with exit 0.
5. `doctor`: `scripts/kaizen-doctor` from the installed copy runs, and its output has a PASS line for this host's install (match the strings kaizen-doctor prints today).
6. `hooks-offline`: each wired hook script from the installed copy, run with this host's fixture payloads from the checkout (`tests/fixtures/hooks/<codex|copilot>_*.json`) and an isolated `CLAUDE_CONFIG_DIR`, exits 0 and prints the shape the hook tests expect (empty or valid JSON with the host's field names). Use the same env vars the host sets (`PLUGIN_ROOT` for Codex; `PLUGIN_ROOT`, `COPILOT_PLUGIN_ROOT`, `CLAUDE_PLUGIN_ROOT` for Copilot).
7. `hooks-live`: read `trace.jsonl` lines newer than the install time. PASS rows for: a sessionStart event, a userPromptSubmit event, and a postToolUse event whose tool is Bash/bash or the host's shell tool. If none at all: FAIL with the hint (Codex: hooks not trusted in /hooks, or session started before install; Copilot/VS Code: hooks not loaded). If some are missing, FAIL that row and list the events and tool names that were seen (this is the data for the Copilot `Bash` vs `bash` matcher question). Copy the distinct (event, tool, keys, env) combinations into the report.
8. Agent observations from `--observe`: `skill_invoked` (the agent invoked `agent-kaizen:doctor` as a skill: `$agent-kaizen:doctor` on Codex, `/agent-kaizen:doctor` on Copilot, and it ran), `notice_seen` (the agent saw Agent Kaizen text injected at session start; may be skip when there was no audit due), `skills_not_preloaded` (the agent's context does not list all Agent Kaizen skill descriptions by default; skip if it cannot tell). A missing required observation (`skill_invoked`) is FAIL with "not reported".

Report: write `out/host-acceptance/<host>-<UTC timestamp>.md` and `.json` in the checkout (git-ignored), replacing the home path with `~` everywhere. The Markdown starts with `RESULT: PASS` or `RESULT: FAIL`, host, CLI version, plugin version, git commit of the checkout, then the check table, then the trace combinations. The last stdout line is `RESULT: PASS|FAIL (<n> pass, <n> fail, <n> skip) report: <path>`.

Tests `tests/test_host_acceptance.py` with fake `codex`/`copilot` executables on PATH and temp `HOME`/`CODEX_HOME`/`COPILOT_HOME`/`CLAUDE_CONFIG_DIR`/`XDG_CACHE_HOME` (follow `tests/test_host_probe.py`, including its env scrubbing and the stub that records only named env keys): status phases; install runs the expected commands against the export folder and not the checkout; check PASS with a complete fake install + trace; FAIL rows for a version mismatch, no trace lines, a missing postToolUse; home path redacted in the report; `--observe` parsing.

### 3. Docs

- `docs/testing/host-acceptance.md`: the instructions for the testing agent. Written for an agent with no context. Sections: what this tests; prerequisites (git, python3 3.9+, jq, the host CLI; signed in where the host needs it); the two phases step by step for each host (Codex CLI, Copilot CLI, VS Code with Copilot), with the exact commands, what the human must do (Codex: trust hooks in `/hooks`; VS Code: reload window or start a new chat session; any manual install), how to make the three observations and pass them to `check`, how to trigger the postToolUse hook (run one shell command such as `git status` through the host's shell tool), and what to send back (the RESULT line, the report path, and the full Markdown report). Rules for the agent: do not edit repo files, do not change host config beyond the plugin install, do not commit or push, report FAIL honestly with the detail rather than working around it, and if a step is blocked (sign-in, a permission prompt, a missing CLI) record it as an observation with `skip:<reason>` or stop and ask the human.
- `docs/testing/prompts.md`: the short hand-off prompts, one per host, each 3-6 lines: where the repo is (a local clone path placeholder `<path to agent-kaizen clone>` or `https://github.com/HighwayofLife/agent-kaizen`, with branch `multi-host` until it is merged), "read docs/testing/host-acceptance.md and follow it for host X", "run `tools/host-acceptance status --host X` first", and "reply with the RESULT line and the report".
- Add one line to `docs/hosts.md` pointing to `docs/testing/host-acceptance.md`, and one bullet under the `hooks` group of the `## 0.12.0` entry in CHANGELOG.md: the opt-in host trace (what turns it on, that it records only event names, tool names and key names). Do not bump the version (0.12.0 is unreleased).

## Scope

Allowed files: the three hooks plus an optional new `hooks/lib/` file, `tools/host-acceptance` (new), `tests/test_host_acceptance.py` (new), hook test files and fixtures, `tools/context-budget.json`, `docs/testing/*` (new), `docs/hosts.md`, CHANGELOG.md. Do not touch skills, scripts, manifests, `hooks/hooks.json`, `tools/host-probe` (import from it if useful, but do not change it). If `tests/test_repo.py` privacy or consistency tests object to something, fix the new file, not the test.

## Verify

```
PYTHONPATH=tests python3 -m unittest tests.test_host_acceptance tests.test_hooks tests.test_hook_schedule tests.test_regression_notice tests.test_repo tests.test_host_probe
shellcheck -S warning hooks/*.sh hooks/lib/*.sh
python3 tools/host-acceptance --help
python3 tools/context_budget.py --check
git diff --exit-code d1accc4 -- hooks/hooks.json
```
(Use the context budget command the repo actually has; check `tools/ci-local` for how it calls it.)

Sandbox note: process, signal and temp-dir tests may fail inside your sandbox; the dispatcher's checks run outside it and are the authority. Do not install anything into the real `~/.codex` or `~/.copilot`.
