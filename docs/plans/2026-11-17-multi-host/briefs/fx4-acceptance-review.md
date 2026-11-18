# FX4: fixes from the review of the host acceptance kit (T1)

Agent: Terra, effort medium. Risk: normal. Do not commit or push.

## Context

T1 added an opt-in hook trace (`hooks/lib/trace.sh`, a block in `hooks/audit-notice.sh`, `hooks/bash-burst.sh`, `hooks/session-audit.sh`), `tools/host-acceptance`, `tests/test_host_acceptance.py`, and the agent instructions `docs/testing/host-acceptance.md`. A coding agent inside Codex CLI, Copilot CLI or VS Code follows that doc to install the plugin, make observations, and run `tools/host-acceptance check`. A review found the defects below. Fix each one and add or adjust a test for each code change.

## Fixes

1. **No doctor skill exists.** `docs/testing/host-acceptance.md` step 3 of Phase 2 tells the agent to invoke `agent-kaizen:doctor`, but `skills/` has no `doctor` (the list is in `skills/`). Use the `scan` skill with `--demo` instead: Codex `$agent-kaizen:scan --demo`, Copilot CLI and VS Code `/agent-kaizen:scan --demo`. `pass` means the skill loaded and ran `scripts/kaizen-scan` (it prints a demo scorecard). Update the doc text, the `--help`/comments in `tools/host-acceptance` and any test text that mentions the doctor skill. The `doctor` check row (which runs `scripts/kaizen-doctor` directly) stays.
2. **`doctor` check fails a healthy manual VS Code install.** In `tools/host-acceptance` `check`, the doctor row requires the line `Copilot: plugin installed`. When the host is `vscode` and the state records `install: manual` or `--install-dir` was given, kaizen-doctor may not see that install. In that case make the row SKIP with detail `manual install; kaizen-doctor checks the Copilot CLI location only` unless the PASS line is present (then PASS). Other hosts unchanged.
3. **Live trace rows are pooled across hosts.** `hooks-live:*` uses every trace line since install time. Count only lines whose `host` matches the host under test (`codex` for `--host codex`, `copilot` for `copilot-cli` and `vscode`). Show other-host lines in the detail only if no matching lines exist (for example `no copilot lines; seen hosts: codex`). Also list in the report how many `sessionStart` lines were seen (more than one means several sessions contributed; note it, don't fail).
4. **Trace may record arbitrary strings.** In `hooks/lib/trace.sh`, `event` and `tool` come from the payload. Keep a value only if it matches `^[A-Za-z0-9_.:-]{1,64}$`; otherwise write the string `"<other>"`. Key names in `keys` get the same rule (replace a non-matching key name with `"<other>"`). Do it in the jq filter. In `tools/host-acceptance`, apply the same rule again when reading trace lines (defence in depth).
5. **Inherited `kaizen_tracing`.** In `hooks/audit-notice.sh` and `hooks/bash-burst.sh` (and `session-audit.sh` if it uses the variable), an environment value `kaizen_tracing=1` makes the hook use the cached input while the switch is off, so stdin is never read. Set `kaizen_tracing=0` (and `kaizen_input=`) unconditionally right before the `if [[ -f ... ]]` trace block in each hook.
6. **Bare `$HOME` under `set -u`.** The switch test expands `${CLAUDE_CONFIG_DIR:-$HOME/.claude}`. With `set -u` and no `HOME`, the hook errors (exit 127 seen in bash-burst). Use `${CLAUDE_CONFIG_DIR:-${HOME:-}/.claude}` in all three hooks and in `trace.sh`. A hook with no `HOME` and no `CLAUDE_CONFIG_DIR` must behave as before T1 (test it for bash-burst: same stdout and exit code as with trace off).
7. **Report redaction.** `tools/host-acceptance` redacts only the literal home string after `json.dumps`, so a non-ASCII home path escaped by JSON survives, and paths under other users' homes survive. Redact the data before serialising (walk dicts/lists/strings), and in each string replace the current home with `~` and any `/Users/<name>` or `/home/<name>` prefix with `~<name>`-free `~`. Write the JSON with `ensure_ascii=False`. Same redaction for the Markdown lines and the final stdout line.
8. **`skill_invoked=skip` gives PASS.** `skill_invoked` is required: a `skip` value becomes a FAIL row with detail `required observation skipped: <note>`. `notice_seen` and `skills_not_preloaded` keep accepting skip.
9. **`status` trusts a saved report path.** In `status`, print `Done: report at ...` only if that report file exists under this checkout's `out/host-acceptance/`. Otherwise fall back to the Phase 2 or Phase 1 message.

Not in scope: the offline check accepting empty hook output (empty output is a valid result when nothing is due).

## Doc touch-ups

In `docs/testing/host-acceptance.md`, keep the structure. Update step 3 of Phase 2 for fix 1, the `doctor` table row for fix 2, the `hooks-live` rows for fix 3 (only lines from this host count), and the observation text for fix 8 (`skill_invoked` cannot be skipped; if the host can't invoke it, report `fail:<reason>`). Plain short sentences.

## Scope

Allowed files: `hooks/lib/trace.sh`, `hooks/audit-notice.sh`, `hooks/bash-burst.sh`, `hooks/session-audit.sh`, `tools/host-acceptance`, `tests/test_host_acceptance.py`, `tests/test_hooks.py`, `tools/context-budget.json` (only if the context-budget check asks for it, via `tools/context_budget.py`), `docs/testing/host-acceptance.md`. Do not touch `hooks/hooks.json`, skills, scripts, manifests or CHANGELOG (the 0.12.0 entry already describes the trace).

## Verify

```
PYTHONPATH=tests python3 -m unittest tests.test_host_acceptance tests.test_hooks tests.test_hook_schedule tests.test_regression_notice tests.test_repo tests.test_host_probe
shellcheck -S warning hooks/*.sh hooks/lib/*.sh
python3 tools/host-acceptance --help
python3 tools/context_budget.py --root .
git diff --exit-code d1accc4 -- hooks/hooks.json
```

Sandbox note: process and temp-dir tests may fail inside your sandbox; the dispatcher's checks run outside it and are the authority. Do not install anything into the real `~/.codex` or `~/.copilot`.
