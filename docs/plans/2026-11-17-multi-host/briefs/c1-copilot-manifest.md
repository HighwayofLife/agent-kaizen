# Brief C1 (CONTINGENT): Copilot-only manifest and hooks file

**Run this brief only if the owner's live Copilot check (O1) shows that the shared `hooks/hooks.json` cannot serve Copilot**, for example: the plugin fails to load, `SessionStart` with matcher `startup|resume` never fires, `"async": true` makes the file rejected, the matcher `Bash` drops the events of Copilot's lowercase `bash` tool so `bash-burst.sh` never runs, or `agents/kaizen-auditor.md` breaks loading. The owner must tell you which failure. If the task does not say O1 failed, stop and report "C1 not triggered". It must land after P08 and before P09.

Agent: Terra, effort medium. Risk: normal. Size: S/M.
Do not commit or push.

## Goal and why

Agent Kaizen (Claude Code plugin, 0.11.0 with the multi-host work from P01 to P08 landed) installs on Copilot CLI from its Claude-format manifest and shared `hooks/hooks.json`. If a live check shows Copilot rejects or ignores that hook file, Copilot needs its own hook file. Copilot reads plugin manifests in this order: `.plugin/`, root `plugin.json`, `.github/plugin/`, `.claude-plugin/` (https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference, checked 2026-11-17). So a manifest at `.github/plugin/plugin.json` wins over `.claude-plugin/plugin.json` on Copilot, while Claude Code and Codex never read it. Do not add a root `plugin.json`: Copilot would treat it as an Agent Plugins manifest, which takes precedence and ignores root `agents/` and `hooks/hooks.json`.

## Context

- `.claude-plugin/plugin.json` holds `name` (`agent-kaizen`), `version`, `description`. `.claude-plugin/marketplace.json` names the marketplace `agent-kaizen-tools` with `source: "./"`.
- `hooks/hooks.json` wires `SessionStart` (matcher `startup|resume`: `audit-notice.sh`, then `session-audit.sh` with `async: true`), `UserPromptSubmit`, and `PostToolUse`/`PostToolUseFailure` (matcher `Bash`, `bash-burst.sh`). It must stay byte-identical to commit `d1accc4` (Claude Code behaviour is pinned).
- The hook scripts (after P05) detect the host and print Copilot-shaped output; Copilot sets `PLUGIN_ROOT`, `COPILOT_PLUGIN_ROOT` and `CLAUDE_PLUGIN_ROOT` for plugin hooks.
- `tests/test_repo.py` has JSON parse, manifest-name and plugin-root-reference tests; `tools/host-probe` (P01) checks the Copilot install when the `copilot` CLI is present; `tools/context_budget.py` and `tools/context-budget.json` pin wired hook text.
- Version rule: a change under `.claude-plugin/`, `hooks/` etc. needs a version bump and CHANGELOG entry. P09 does that; you only write a changelog fragment. P09 bumps `.github/plugin/plugin.json` together with `.claude-plugin/plugin.json` and merges `changelog/C1.md` under the heading `` `.github/plugin/plugin.json`, `hosts/copilot/hooks.json`: ``; the parity test you add makes it fail if only one is bumped. Keep the manifest at the current version (0.11.0) now.

## Files you may change or create

- Create `.github/plugin/plugin.json`: `name` `agent-kaizen`, `version` equal to `.claude-plugin/plugin.json`, `description` equal to it, and the hooks path pointing at the new file `hosts/copilot/hooks.json` (use the manifest key the Copilot plugin reference names for hooks; read the reference page above and quote the key in your report. If you cannot confirm the key, stop and report).
- Create `hosts/copilot/hooks.json`: the Copilot-native form of the same wiring, with only what the owner's O1 result requires (for example: no `"async"` key, no matcher on `SessionStart`, matcher `bash` or none for the `bash-burst.sh` entries if the `Bash` matcher drops Copilot's events; the script already accepts `bash` on Copilot). Use the same `bash "${CLAUDE_PLUGIN_ROOT}/hooks/<file>.sh"` command strings as `hooks/hooks.json` so the scripts are shared. Do not copy or change the scripts.
- `tests/test_repo.py`: add a test that `.github/plugin/plugin.json` exists, parses, and its `name`, `version` and `description` equal those of `.claude-plugin/plugin.json`, and that the hooks path it names exists. Add `hosts/copilot/hooks.json` to the JSON-parse test list.
- `tools/host-probe` (P01): add one Copilot check that the installed plugin folder contains `.github/plugin/plugin.json` (PASS/FAIL/SKIP in the existing output format, SKIP when `copilot` is missing). Extend `tests/test_host_probe.py` for it using the existing stub pattern.
- `tools/ci-local`: add `hosts/copilot/hooks.json` and `.github/plugin/*.json` to the `JSON` stage's patterns.
- `docs/hosts.md`: one line in the Copilot section saying Copilot reads `.github/plugin/plugin.json` and `hosts/copilot/hooks.json`.
- Create `docs/plans/2026-11-17-multi-host/changelog/C1.md` with a one-bullet user-facing line (no heading line: P09 adds the fixed heading).

## Do not touch

`hooks/hooks.json` (it must pass `git diff --exit-code d1accc4 -- hooks/hooks.json`), `hooks/*.sh`, `.claude-plugin/*`, `CHANGELOG.md`, `README.md`, any other skill or script. Do not bump the version.

## Acceptance criteria

1. The new test fails if `.github/plugin/plugin.json` `version` differs from `.claude-plugin/plugin.json` (check by editing a copy of the value, running the test, then restoring it).
2. `jq empty .github/plugin/plugin.json hosts/copilot/hooks.json` succeeds.
3. Claude Code and Codex files are unchanged: `git diff --exit-code d1accc4 -- hooks/hooks.json` exits 0 and `git diff --stat` / `git status --short --untracked-files=all` list none of `.claude-plugin/*`.
4. `tools/host-probe --host copilot` still exits 0 (SKIP lines when `copilot` is not installed).

## Sandbox and environment (read before running any command)

- Writable temp dir: `mkdir -p out/tmp && export TMPDIR="$PWD/out/tmp"` (`out/` is git-ignored; keep the path short). If `out/` is not writable, use any writable directory outside the repo. Use it for every scratch file and temp directory you create.
- `tools/host-probe` honours `TMPDIR` but always exports the plugin with `git archive` (or the `--worktree` file list) into a fresh directory under it and runs the host CLI from that export, never from the checkout. Do not install a host CLI from the checkout or put a host home under `out/` inside the tree: Codex fails with "File name too long" when it copies a tree that contains `out/`.
- Record every command the environment blocks (read-only file system, no network, no sign-in, missing CLI) as `not run: <reason>`, separately from product failures (a failed assertion, or a non-zero exit from product code). Stop and report only for product failures. Never report a blocked run as a pass. A probe `FAIL` whose detail is an OS or network error (permission denied, read-only file system, DNS or connection error, sign-in) counts as blocked; a `FAIL` about the product (version mismatch, skills still listed, hooks missing) is a product failure.
- Check changed files with `git status --short --untracked-files=all` together with `git diff --stat`: the diff alone omits new files.
- Run narrow unit tests as `PYTHONPATH=tests python3 -m unittest tests.test_x ...` (some test modules import their siblings as top-level modules and fail without it).

## Verification

```bash
PYTHONPATH=tests python3 -m unittest tests.test_repo tests.test_host_probe
jq empty .github/plugin/plugin.json hosts/copilot/hooks.json
git diff --exit-code d1accc4 -- hooks/hooks.json
git status --short --untracked-files=all
git diff --stat
tools/host-probe --host copilot
tools/ci-local --skip-tests
python3 -m unittest discover -s tests
shellcheck -S warning hooks/*.sh
claude plugin validate .
```

The live Copilot behaviour (does `hosts/copilot/hooks.json` fire the session notice) needs a signed-in `copilot`; it goes in the owner checklist (rerun O1). If `claude` is not installed in your sandbox, say so and skip only that command.

## Reporting

Report the manifest key you used for hooks (with the doc quote), each verify command pass/fail, and `git diff --stat`. Do not commit or push. If the O1 failure the owner described is not fixed by a separate hooks file (for example the failure is in loading `agents/kaizen-auditor.md`), stop and report that instead.

## Suggested agent

Terra, effort medium. Risk normal. **Contingent**: only if O1 fails on hooks.
