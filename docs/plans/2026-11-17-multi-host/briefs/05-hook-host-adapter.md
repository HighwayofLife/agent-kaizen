# Brief P05: host adapter for the three wired hooks

Suggested agent: Terra, medium effort. Risk: normal. Size: M. Group A (runs in parallel with P01, P02, P03, P06; you own `hooks/audit-notice.sh`, `hooks/session-audit.sh`, `hooks/bash-burst.sh`, `tests/test_hooks.py`, `tests/test_hook_schedule.py`, `tests/test_regression_notice.py`, `tests/fixtures/hooks/*` and `tools/context-budget.json` in this group; `tests/test_usage_guard.py` and `tests/test_schedule_robustness.py` only if the env-scrub check below fails).

## Goal and why

Agent Kaizen is a Claude Code plugin; Codex CLI and the Copilot runtime load the same `hooks/hooks.json` and set a plugin-root variable for hooks. Three hooks are wired: `audit-notice.sh` (SessionStart notice), `session-audit.sh` (async background audit), `bash-burst.sh` (nudge after repeated Bash calls). They differ across hosts only in output shape, the skill-call syntax in the notice text, (Copilot) the Bash tool name, and (Copilot) async handling. Make them host-aware with one identical helper block, while keeping Claude Code output BYTE-IDENTICAL to 0.11.0 (a golden test compares the complete stdout, including jq's default multi-line formatting). `hooks/hooks.json` must not change, including its `Bash` matcher.

## Context and facts you can rely on

- Baseline commit `d1accc4` is release 0.11.0. Use `git show d1accc4:hooks/<file>` to get the original scripts.
- Hook wiring (`hooks/hooks.json`, unchanged): `SessionStart` matcher `startup|resume` runs `audit-notice.sh` then `session-audit.sh` (`async: true`); `UserPromptSubmit`, `PostToolUse` and `PostToolUseFailure` (matcher `Bash`) run `bash-burst.sh`.
- Output sites today: `hooks/audit-notice.sh:162` prints `{hookSpecificOutput:{hookEventName:"SessionStart",additionalContext:$c}}` via `jq -n --arg c "$msg"`; line 8 is an EXIT trap that prints `{}` on a quiet exit; the wording `/agent-kaizen:review` is at `:78` (inside `audit_msg`) and `:123` (inside `experiment_msg`). `hooks/bash-burst.sh:17-19` reads `hook_event_name`, `tool_name`, `has("agent_id")`, `is_interrupt`, `session_id`; `:29` tests `$tool == Bash`; `:41` prints `{hookSpecificOutput:{hookEventName:$event,additionalContext:$message}}`. `hooks/session-audit.sh` (7 lines) redirects stdio to /dev/null, exits if `CLAUDE_PLUGIN_ROOT` is unset, then runs `python3 "$CLAUDE_PLUGIN_ROOT/scripts/kaizen-scheduled" auto-audit`.
- Host facts (documented by the vendors, not probed live; do not claim more): Codex plugin hooks get `PLUGIN_ROOT` plus `CLAUDE_PLUGIN_ROOT`; Codex hook input and output shapes match Claude Code's (`hookSpecificOutput.additionalContext`); Codex tool name is `Bash`; Codex skills are invoked `$agent-kaizen:<name>`. Copilot plugin hooks get `PLUGIN_ROOT`, `COPILOT_PLUGIN_ROOT` and `CLAUDE_PLUGIN_ROOT`; for `sessionStart` only a top-level `additionalContext` is used; Copilot's shell tool is named `bash` (PascalCase-event payloads report Claude names such as `Bash`, so accept both); `"async": true` is not documented for Copilot; skills are `/agent-kaizen:<name>`. Whether Copilot honours the nudge output for tool hooks, which event and tool names it sends, and whether the shared matcher `Bash` in `hooks/hooks.json` delivers the events of its lowercase `bash` tool, is checked later by the owner on a signed-in host (owner check O1); contingent packet C1 (a Copilot-only hooks file) is the fallback if the matcher drops them. Do not add other spellings and do not change `hooks/hooks.json`.
- Host detection order (decided): `KAIZEN_HOST` if set to `claude`, `codex` or `copilot`; else `copilot` when `COPILOT_PLUGIN_ROOT` is set and non-empty; else `codex` when `PLUGIN_ROOT` is set and non-empty; else `claude`. Any other `KAIZEN_HOST` value counts as unset. Claude Code sets neither `COPILOT_PLUGIN_ROOT` nor `PLUGIN_ROOT`.
- `tools/context-budget.json` pins, per wired hook, `literal_bytes`, `sha256` and `literal_text` (the model-visible text a Claude session sees). `tools/context_budget.py` (only option `--root`) reports `hook changed; review and update inventory` when a sha256 differs. The model-visible text for Claude does not change, so preserve `literal_text` and `literal_bytes` exactly and change ONLY the three `sha256` values: get each with `shasum -a 256 hooks/<file>`. (Where the Claude golden output matches, nothing else in the inventory may change.) Do not edit `tools/context_budget.py` (P02 owns it).
- Tests: `tests/test_hooks.py:43` (`HookTests`; helpers `run_raw`/`run` at `:15-27` merge `os.environ` into the child's env), `tests/test_hook_schedule.py` (drives `session-audit.sh` with a stub audit; `HOLD_AUDIT` blocks the stub until a file exists), existing audit-notice tests at `tests/test_hooks.py:~346-440`, fixtures in `tests/fixtures/hooks/` (`sessionstart.json`, `pretooluse_agent.json`). Existing test setups inherit the caller's environment, so a developer shell that has `PLUGIN_ROOT`, `COPILOT_PLUGIN_ROOT` or `KAIZEN_HOST` set would flip the host: make `run_raw` in `tests/test_hooks.py` (this also covers `tests/test_usage_guard.py:14` and `tests/test_schedule_robustness.py:23`, which import it), the hook helper in `tests/test_hook_schedule.py`, and the env dict built at `tests/test_regression_notice.py:28-29` drop `KAIZEN_HOST`, `PLUGIN_ROOT` and `COPILOT_PLUGIN_ROOT` from the inherited environment unless the test passes them explicitly. Check the scrub with `KAIZEN_HOST=codex PLUGIN_ROOT=x COPILOT_PLUGIN_ROOT=y PYTHONPATH=tests python3 -m unittest tests.test_hooks tests.test_hook_schedule tests.test_usage_guard tests.test_schedule_robustness tests.test_regression_notice`; if `tests.test_usage_guard` or `tests.test_schedule_robustness` still fail in that run, add the same scrub to them.
- Before editing, run the narrow verify command once on the unchanged tree to confirm it runs (about 60 tests, a minute or so): `python3 -m unittest tests.test_hook_schedule` alone fails with `ModuleNotFoundError` because that module imports `test_scripts` as a top-level module; `PYTHONPATH=tests` (or `python3 -m unittest discover -s tests -p 'test_hook*.py'`) fixes it.

## Scope

Edit: `hooks/audit-notice.sh`, `hooks/session-audit.sh`, `hooks/bash-burst.sh`, `tests/test_hooks.py`, `tests/test_hook_schedule.py` (only for the env scrub and the new Copilot-detach test), `tests/test_regression_notice.py` (env scrub only), `tools/context-budget.json` (three `sha256` values only); `tests/test_usage_guard.py` and `tests/test_schedule_robustness.py` only if the scrub check fails.
Create: `tests/fixtures/hooks/codex_*.json` and `copilot_*.json` (session start; prompt submit; post-tool `Bash` for Codex, `bash` for Copilot), `docs/plans/2026-11-17-multi-host/changelog/P05.md` (`mkdir -p`) with exactly:
`- Hooks are host-aware: on Codex the notice says $agent-kaizen:review, on Copilot output uses top-level additionalContext, the Bash-burst nudge also accepts the lowercase bash tool name on Copilot, and the background audit detaches itself on Copilot. Claude Code output is unchanged. Codex users must trust the plugin hooks in /hooks, and trust is asked again after an update that changes a hook script.`

Do NOT touch: `hooks/hooks.json` (must stay identical to `d1accc4`), `.claude-plugin/plugin.json` (version), `CHANGELOG.md` (only P09 edits them), the other hooks, `tools/context_budget.py`, scripts, docs, skills.

## Required behaviour

1. One helper block, byte-identical in the three hook files, between the marker lines `# --- host helper ---` and `# --- end host helper ---` (exactly once each per file), placed near the top (after the header comments, before first use; keep `trap`/`exec` lines that must come first where they are). It must work under `bash` (the files use `#!/usr/bin/env bash`), be shellcheck-clean at `-S warning`, and use bash builtins only to detect the host and build strings (no `tr`, `sed`, `awk`: `tests/test_hooks.py:559` runs a hook with a bare `PATH`; only `jq`, which the hooks already require, may be called, and only inside `kaizen_context`). It sets `kaizen_host` per the detection order, and defines:
   - `kaizen_skill NAME`: prints `$agent-kaizen:NAME` on Codex, `/agent-kaizen:NAME` otherwise.
   - `kaizen_context EVENT TEXT`: Claude and Codex run `jq -n --arg ...` with the same filter text and no extra flags as today (`{hookSpecificOutput:{hookEventName:EVENT,additionalContext:TEXT}}`; do NOT add `-c` or any other flag, so jq's default multi-line output and the key order are unchanged and the bytes match 0.11.0); Copilot runs `jq -n --arg c "$2" '{additionalContext:$c}'` the same way. There is no single-line-JSON requirement. The function's exit status is jq's, so `audit-notice.sh` can keep its `if ! out=$(...)` failure handling.
2. `audit-notice.sh`: build the two messages with `$(kaizen_skill review)` in place of the literal `/agent-kaizen:review`; for Claude the resulting text must be byte-identical. Replace the `jq -n` call at `:162` with `kaizen_context SessionStart "$msg"` inside the same `if ! out=$(...) || [ -z "$out" ]` test (keep the failure handling and marker-removal logic as is). The quiet `{}` trap at `:8` stays.
3. `session-audit.sh`: root is `${CLAUDE_PLUGIN_ROOT:-${PLUGIN_ROOT:-}}`; exit 0 if empty; on Copilot start `python3 "$root/scripts/kaizen-scheduled" auto-audit` in the background (stdio already closed) and `exit 0` at once, since `async` is undocumented there. Claude and Codex keep the synchronous call, unchanged otherwise.
4. `bash-burst.sh`: the Claude test at `:29` (`$tool == Bash`) is unchanged for Claude and Codex; on Copilot it also accepts `bash` (`[[ $tool == Bash || ( $kaizen_host == copilot && $tool == bash ) ]]`). Output at `:41` through `kaizen_context "$event" "$message"`. Everything else (counting, resets, thresholds, subagent skip, private state dir) unchanged. The `Bash` matcher in `hooks/hooks.json` stays as is.

## Tests

- Golden (Claude): generate expected outputs ONCE by running the 0.11.0 scripts (`git show d1accc4:hooks/audit-notice.sh > <tmp>/audit-notice.sh`, same for `bash-burst.sh`) on the same inputs, then store the resulting stdout bytes as literals (or small files under `tests/fixtures/hooks/`) in the test. Tests must not call git at run time (CI may use a shallow clone). Cases, each run with no host variables: audit-notice with an unreviewed audit (use `AUDIT_DIR` temp, project with `docs/kaizen/`, `HOME` and `CLAUDE_CONFIG_DIR` in a temp dir, as the existing test at `tests/test_hooks.py:~346` does; substitute the temp path in the expected text), audit-notice experiment notice, audit-notice quiet case (`{}\n`), bash-burst nudge for `PostToolUse` and for `PostToolUseFailure`. Compare the COMPLETE stdout byte for byte (jq's multi-line pretty-printing, key order, trailing newline); do not normalise or re-serialise it.
- Codex: run with `PLUGIN_ROOT` and `CLAUDE_PLUGIN_ROOT` set: audit-notice message contains `$agent-kaizen:review` and not `/agent-kaizen:review`, output shape `hookSpecificOutput`; bash-burst accepts `Bash` and does NOT nudge for lowercase `bash` (same as Claude).
- Copilot: run with `COPILOT_PLUGIN_ROOT`, `PLUGIN_ROOT` and `CLAUDE_PLUGIN_ROOT` all set: audit-notice output is `{"additionalContext": ...}` with no `hookSpecificOutput`, wording `/agent-kaizen:review`; bash-burst accepts `bash` and `Bash` and prints the top-level shape (and for Claude, no host variables, lowercase `bash` gives no nudge, as in 0.11.0); `UserPromptSubmit` still resets the count and prints nothing.
- `KAIZEN_HOST` overrides detection (for example `KAIZEN_HOST=codex` with `COPILOT_PLUGIN_ROOT` set gives the Codex shape); an unknown value falls back to detection.
- Copilot detach (`tests/test_hook_schedule.py`): with `COPILOT_PLUGIN_ROOT` set and `HOLD_AUDIT` pointing at a file that does not exist yet, `session-audit.sh` returns promptly (well under the stub's wait) with empty stdout and stderr; creating the hold file then lets the audit finish (use `wait_for` from `test_schedule_robustness` as the neighbouring tests do). Claude path: the existing tests keep passing unmodified except for the env scrub.
- Helper identity: read the text between the two marker lines from all three hooks and assert they are equal and non-empty.
- Fixtures: `tests/fixtures/hooks/codex_sessionstart.json`, `codex_userpromptsubmit.json`, `codex_posttooluse_bash.json`, `copilot_sessionstart.json`, `copilot_userpromptsubmit.json`, `copilot_posttooluse_bash.json`; Claude-shaped payload fields (`session_id`, `cwd`, `hook_event_name`, `tool_name`, ...), no real paths or secrets.

## Acceptance criteria

1. Claude output is byte-identical to 0.11.0 (golden tests pass).
2. Codex and Copilot fixtures give the shapes above.
3. `git diff --exit-code d1accc4 -- hooks/hooks.json` exits 0 (the file, including the `Bash` matcher, is byte-identical).
4. The helper block is byte-identical in the three files (test).
5. `kaizen-doctor` hook check still passes (`tests.test_doctor`); `python3 tools/context_budget.py --root .` passes (`git diff -U0 tools/context-budget.json` shows only the three `sha256` lines changed; total stays 823 bytes); `shellcheck -S warning hooks/*.sh` is clean.
6. Only the files in Scope changed (`git status --short --untracked-files=all`).

## Sandbox and environment (read before running any command)

- Writable temp dir: `mkdir -p out/tmp && export TMPDIR="$PWD/out/tmp"` (`out/` is git-ignored; keep the path short). If `out/` is not writable, use any writable directory outside the repo. Use it for every scratch file and temp directory you create.
- Record every command the environment blocks (read-only file system, no network, no sign-in, missing CLI) as `not run: <reason>`, separately from product failures (a failed assertion, or a non-zero exit from product code). Stop and report only for product failures. Never report a blocked run as a pass.
- Check changed files with `git status --short --untracked-files=all` together with `git diff --stat`: the diff alone omits new files.
- Run narrow unit tests as `PYTHONPATH=tests python3 -m unittest tests.test_x ...` (some test modules import their siblings as top-level modules and fail without it).

## Verification (narrowest first)

```
PYTHONPATH=tests python3 -m unittest tests.test_hooks tests.test_hook_schedule tests.test_context_budget tests.test_doctor tests.test_regression_notice tests.test_usage_guard
KAIZEN_HOST=codex PLUGIN_ROOT=x COPILOT_PLUGIN_ROOT=y PYTHONPATH=tests python3 -m unittest tests.test_hooks tests.test_hook_schedule tests.test_usage_guard tests.test_schedule_robustness tests.test_regression_notice   # env scrub check
shellcheck -S warning hooks/*.sh
python3 tools/context_budget.py --root .
git diff --exit-code d1accc4 -- hooks/hooks.json
git diff -U0 tools/context-budget.json | rg '^[-+] '     # only sha256 lines
git status --short --untracked-files=all
python3 -m unittest discover -s tests
claude plugin validate .
```

## Reporting

Report files changed, the verify output (trimmed), how the golden values were generated, and any behaviour you could not reproduce. Do not commit or push. If an assumption here is wrong (for example `jq -n` key order differs from the original bytes, or the budget tool wants more than the sha256 change), stop and report.
