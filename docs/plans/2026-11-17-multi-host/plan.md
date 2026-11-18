# Plan: Agent Kaizen on Codex CLI and the GitHub Copilot runtime

Date 2026-11-17. Baseline 0.11.0 (`d1accc4`, HEAD `d8a4cb7`). Mode: plan-only (briefs are written from **Packet notes** below by `sonnet-planner`). Inputs: `design.md` (Fable), `design-astra.md` (Astra), `research.md` (planner re-checks).

## Summary

Keep one plugin tree in Claude Code format. Codex CLI installs it today (probed twice: local checkout and `HighwayofLife/agent-kaizen`, no sign-in). The Copilot runtime (Copilot CLI, and VS Code with the Copilot harness, which is the same runtime) is documented to load the same tree: Claude manifests, nested `hooks/hooks.json`, `CLAUDE_PLUGIN_ROOT` set for hooks, `disable-model-invocation` honoured. The work is small fixes inside shared files: hide skills from Codex's always-on list, a two-line plugin-root preamble in each skill, a runtime host map, host-aware hook output, host-aware script messages, docs, CI. 9 packets (1 Luna, 8 Terra). Claude Code behaviour stays byte-identical; a golden test pins hook output.

## Goal / non-goals

Goal: a user on Codex CLI, Copilot CLI or VS Code (Copilot harness) can install Agent Kaizen with that host's own plugin command, invoke skills explicitly, get the session-start audit notice, and run the zero-token scripts; every unsupported feature says so in one line. Claude Code unchanged. Works on any user's machine (no paths, accounts or tools of the owner's assumed).

Non-goals for this plan: Codex IDE extension (it has no plugin support: "The IDE extension doesn't support plugins", re-read 2026-11-17); Copilot cloud agent (no installed plugins, no local logs); VS Code Local harness (deprecated, removed Feb 2027); the VS Code Claude and Codex harnesses (they are those hosts); Copilot usage measurement, guardrail hooks on new hosts, scheduled model reviews on new hosts, native auditor agents, a `KAIZEN_HOME` state root, generated per-host packages. See **Follow-ups**.

## Context (code map)

- Manifests: `.claude-plugin/plugin.json` (version 0.11.0, description says "for Claude Code (and optionally Codex)"), `.claude-plugin/marketplace.json` (marketplace `agent-kaizen-tools`).
- Skills: 22 `skills/*/SKILL.md`; 23 files under `skills/` and `agents/` hold 76 `${CLAUDE_PLUGIN_ROOT}` references. Frontmatter checked at `tests/test_repo.py:44-50`; reference existence at `tests/test_repo.py:60-71` (regex `\$\{CLAUDE_PLUGIN_ROOT\}/(...)`, so `${CLAUDE_PLUGIN_ROOT}` with no `/` after it is not checked); README skills table at `:73-77`. Other tests that read skill text: `tests/test_flow_skill.py:11,18`, `tests/test_process_rules.py:11,19`, `tests/test_schedule_steps.py:784`, `tests/test_scan.py:66`.
- Context budget: `tools/context_budget.py:70-90` counts a skill description as visible only when `disable-model-invocation != 'true'` (Claude rule). `tools/context-budget.json` holds `budget_bytes: 1024` and, per wired hook, `literal_bytes`, `sha256` and `literal_text`; any edit to `hooks/audit-notice.sh`, `hooks/bash-burst.sh`, `hooks/session-audit.sh` must refresh it.
- Hooks: `hooks/hooks.json` wires `SessionStart` (matcher `startup|resume`: `audit-notice.sh`, then `session-audit.sh` with `async: true`), `UserPromptSubmit`, `PostToolUse` and `PostToolUseFailure` (matcher `Bash`, `bash-burst.sh`). Output sites: `hooks/audit-notice.sh:162` (`{hookSpecificOutput:{hookEventName:"SessionStart",additionalContext:$c}}`), `:8` (prints `{}` on quiet exit), `:78` and `:123` (wording `/agent-kaizen:review`); `hooks/bash-burst.sh:17-19` (reads `hook_event_name`, `tool_name`, `has("agent_id")`, `is_interrupt`, `session_id`), `:29` (`$tool == Bash`), `:41` (hookSpecificOutput); `hooks/session-audit.sh:3-6` (exits if `CLAUDE_PLUGIN_ROOT` unset, runs `kaizen-scheduled auto-audit`). Tests: `tests/test_hooks.py:43` (`HookTests`), `tests/test_hook_schedule.py`, fixtures in `tests/fixtures/hooks/`.
- Scripts: `scripts/kaizen-doctor:58-94` (Claude registry `plugins/installed_plugins.json`, fixes `claude plugin update|list|install`, `kaizen-link --apply`; hook check at `:81-86` rebuilds the expected `bash "${CLAUDE_PLUGIN_ROOT}/hooks/..."` command), `scripts/kaizen-scan:89` ("use Claude Code or Codex"), `scripts/token-audit:17-29` (paths helper; the identical block also in `scripts/kaizen-link:13`, `scripts/kaizen-scheduled:46`, `scripts/install-schedule:33`, checked by `tests/test_runner.py:366`).
- CI: `.github/workflows/ci.yml:3-6` triggers on `v*` tags and `workflow_dispatch` only; `checks` job installs Node 22 and Claude Code, runs `tools/ci-local --skip-tests`. `tools/ci-local` stages: unit tests, context budget, shellcheck, JSON, Python compile, script help, plugin validation (when `claude` is on PATH), version and changelog; flags `--python`, `--tag`, `--skip-tests`, `--version-only`.
- Rules: `AGENTS.md:19` and `CONTRIBUTING.md:21` (version rule paths). README `## Quick start` at `README.md:61`, versions table `:65-69`, `## Skills` at `:200`.
- Bench: `python3 tests/bench_token_audit.py --baseline HEAD [--max-ratio R]`.

## Approach

One shared tree, Claude format, differences handled inside the shared files (Fable's architecture). Why: it is the only option with live evidence (Codex install and skill listing probed by both Fable and the planner), it needs no build step or release artifact from users, GitHub-source installs keep working on all three hosts, and the per-host differences found are small (one sidecar file per skill, two preamble lines, one output-shape branch in three hooks, message wording in two scripts).

Rejected:
- Generated self-contained per-host packages from `tools/package-host` (Astra): a build system, a release-ZIP install path and 14 packets to fix differences that a preamble and a sidecar cover; users could no longer install from the GitHub repo directly.
- Root Agent Plugins `plugin.json`: in Copilot it takes precedence and switches to rules that ignore root `agents/` and `hooks/hooks.json`; Claude Code does not read it.
- Per-host hook script sets: three wired hooks differ only by output shape and one tool name.
- Loose skills in `~/.agents/skills` / `.github/skills`: lose the `agent-kaizen:` prefix; `review`, `start`, `undo`, `models` would collide.
- Native auditor agents per host in this release (Astra): not needed for the loop (`cycle` with `propose-only` covers it); Copilot `.md` loading is unverified. Follow-up F4.

### Reconciled

| Topic | Fable | Astra | Chosen | Why |
|---|---|---|---|---|
| Codex install from the Claude manifests | Works (probed) | Use an isolated `.codex-plugin` package | Shared tree | Planner re-probed: local path and `HighwayofLife/agent-kaizen` both install 0.11.0, no sign-in. |
| Codex IDE extension | Out: no plugins | In: same package, separate smoke | Out | Current official doc: "The IDE extension doesn't support plugins." Bundled README is older evidence. |
| VS Code target | Copilot harness = Copilot CLI runtime | Local agent mode, Claude-shaped `hookSpecificOutput` | Copilot harness | VS Code hooks doc: Local harness deprecated, removed February 2027. |
| Copilot hook config | Shared nested `hooks/hooks.json` accepted | Native v1 `.github/hooks/*.json` | Shared `hooks/hooks.json` | Copilot changelog: "support Claude Code's nested matcher/hooks structure"; plugin reference reads `hooks/hooks.json`. Live check O1. |
| Copilot plugin root in hooks | `PLUGIN_ROOT`, `COPILOT_PLUGIN_ROOT`, `CLAUDE_PLUGIN_ROOT` | Same (bundled SDK) | Same | Changelog: "Plugin hooks receive PLUGIN_ROOT, COPILOT_PLUGIN_ROOT, and CLAUDE_PLUGIN_ROOT". |
| Copilot `sessionStart` output | Top-level `additionalContext` | Top-level (CLI) / nested (VS Code local) | Top-level on Copilot | Hooks reference: "Only `additionalContext` is consumed for `sessionStart`". |
| `disable-model-invocation` on Copilot | Honoured | Unproven; command fallback | Honoured | Changelog: "Fully honor the skill disable-model-invocation flag". Live check O1. |
| `disable-model-invocation` on Codex | Ignored; use `agents/openai.yaml` | Same | `agents/openai.yaml` per skill | Fable probed 22 to 19 with 3 sidecars; planner re-probed 22 listed. |
| Copilot install syntax | `copilot plugin marketplace add` / `copilot plugin install` | `/plugin marketplace add` / `/plugin install` | CLI subcommands | Current plugin reference documents `copilot plugin install` (alias `add`); `/plugin` is a dashboard. O1 confirms both. |
| CI enforces the version bump on PRs | Assumed (AGENTS.md) | No PR trigger exists | No PR trigger today | `.github/workflows/ci.yml:3-6`. See decision D3. |
| State location for non-Claude users | Keep `~/.claude` / `$CLAUDE_CONFIG_DIR` | Neutral `KAIZEN_HOME` | Keep (pending D1) | Moving it touches ~40 script/hook references and the paths helper x4; no user has asked. |
| Auditor agent on other hosts | Claude-only; use `cycle propose-only` | Native read-only role per host | Claude-only now | Simpler; Copilot `.md` loading unverified (O1). Follow-up F4. |
| Changelog collection | One shared `changelog-bullets.md` | Serialize metadata on one branch | Per-packet files `changelog/PNN.md` | A shared file conflicts across worktrees. |
| Probing a checkout with Codex | Temp homes | Disposable output root under `out/` | Clean `git archive` export to a system temp dir | Planner probe: a `CODEX_HOME` under `out/` fails ("File name too long"), and a local-path install copies `out/`, `.git`, `.claude/`. |

## Owner decisions (2026-11-17)

D1 keep `~/.claude` / `$CLAUDE_CONFIG_DIR` on every host for 0.12.0. D2 ship Copilot as experimental in 0.12.0. D3 add a `pull_request` trigger to `ci.yml`. D4 follow-ups F1–F5 go in a separate plan after 0.12.0. All four follow the recommendations below; nothing is blocked on a decision now.

## Decisions needed

| # | Decision | Recommendation | Blocks |
|---|---|---|---|
| D1 | Where Kaizen state lives for a user without Claude Code (config, audits, backups, usage DB). | Keep `$CLAUDE_CONFIG_DIR` or `~/.claude` on every host for 0.12.0 (one ledger across hosts); README says a Codex- or Copilot-only user gets a `~/.claude/` folder with only Agent Kaizen files. `KAIZEN_HOME` override is follow-up F5. | P07 (one README paragraph) |
| D2 | Ship Copilot support before its usage is measured and before the owner's live check O1 is done. | Yes, labelled experimental: skills and the session notice; "usage not measured yet". README rows only claim what `probe-results.md` or O1 shows. | P07 |
| D3 | Add a `pull_request` trigger to `.github/workflows/ci.yml` so the stated PR rule is real. | Yes, plain trigger on `pull_request` to `main`; no base-relative version diff now. Otherwise P08 changes AGENTS.md/CONTRIBUTING.md wording to "the release tag check enforces". | P08 (the trigger line and the rule wording only) |
| D4 | Follow-ups F1 to F5 go to a separate plan after 0.12.0, started when O1 results are in. | Yes. | none |

Settled without a decision (both designs agree): on non-Claude hosts, changes to host configuration are proposals only in every autonomy mode until `docs/hosts.md` marks that file verified (`kaizen-backup` knows only Claude paths). Codex IDE and Copilot cloud are out of scope.

## Assumptions

- Claude Code substitutes `${CLAUDE_PLUGIN_ROOT}` in skill bodies (the current skills rely on it), so the preamble's first line reads as a plain path there.
- Host detection order in hooks: `KAIZEN_HOST` if set, else `copilot` when `COPILOT_PLUGIN_ROOT` is set, else `codex` when `PLUGIN_ROOT` is set, else `claude`. Claude Code sets neither `COPILOT_PLUGIN_ROOT` nor `PLUGIN_ROOT`; the golden test catches it if that changes.
- Copilot ignores or tolerates `"async": true`; if O1 shows the file is rejected, contingent packet C1 applies.
- Copilot's hook matcher `Bash` in the shared `hooks/hooks.json` delivers (or not) the events of its lowercase `bash` tool: unknown until O1. `hooks/hooks.json` stays byte-identical; if O1 shows the event is dropped, C1 is the fallback.
- One integration branch; packets run in separate worktrees and merge in dependency order.

## Version and changelog (read before running packets)

- Only P09 edits `version` in `.claude-plugin/plugin.json` and `CHANGELOG.md` (0.12.0). No other packet touches them, so parallel worktrees do not conflict. P07 edits the `description` field of `plugin.json`; P09 runs after P07.
- Each packet that changes a runtime path writes its user-facing bullet(s) to its own file `docs/plans/2026-11-17-multi-host/changelog/PNN.md`; P09 merges them.
- Today CI does not run on PRs (ci.yml:3-6); `tools/ci-local` only checks that the current version has a CHANGELOG heading, so intermediate commits on the branch pass. D3 decides whether a PR trigger is added. The work lands on one branch and is released once.

## Verification environment (every packet)

Every brief carries this section; it exists because the review sandbox is read-only apart from the worktree and has no network.

- Writable temp dir: `mkdir -p out/tmp && export TMPDIR="$PWD/out/tmp"` (`out/` is git-ignored; keep the path short). If `out/` is not writable, use any writable directory outside the repo. `tools/host-probe` honours `TMPDIR` but always exports the plugin with `git archive` (or `git ls-files` for `--worktree`) into a fresh directory under it and runs the host CLI from there, never from the checkout: a Codex local install of a tree that contains `out/` failed with "File name too long".
- Python 3.9 check: `UV_OFFLINE=1 tools/ci-local --python 3.9`, only when Python 3.9 is already provisioned for `uv`; if `uv` would have to download it, do not run it.
- Record every command the environment blocks (read-only file system, no network, no sign-in, missing CLI, `uv` download) as `not run: <reason>`, separately from product failures (a failed assertion, or a non-zero exit from product code). Stop and report only for product failures. Never report a blocked run as a pass. A probe `FAIL` whose detail is an OS or network error (permission denied, read-only file system, DNS or connection error, sign-in) counts as blocked; a `FAIL` about the product (version mismatch, skills still listed, hooks missing) is a product failure.
- Check files with `git status --short --untracked-files=all` together with `git diff --stat`: the diff alone omits new files.
- Narrow unit tests run as `PYTHONPATH=tests python3 -m unittest tests.test_x ...` (some modules import their siblings as top-level modules and fail without it).
- Owner checklist item O5 covers the runs a sandbox cannot do.

## Packets

Tiers: `luna` = short docs-only edits with exact wording; `terra` = code, tests, scripts, hooks, CI. Full gate for every packet before reporting: `python3 -m unittest discover -s tests`, `shellcheck -S warning hooks/*.sh`, `claude plugin validate .` (narrow verify first, as listed).

| id | Title | Depends on | Parallel group | Tier / effort | Risk | Size | Blocked by decision | Verify (narrowest first) |
|---|---|---|---|---|---|---|---|---|
| P01 | `tools/host-probe`: isolated install and discovery checks | none | A | terra / medium | low | M | none | `PYTHONPATH=tests python3 -m unittest tests.test_host_probe`; `tools/host-probe --help`; `tools/host-probe --host codex` (expect skills check FAIL on 0.11.0 tree) |
| P02 | Codex skill visibility (`agents/openai.yaml` x22) and budget | none | A | terra / low | low | S | none | `PYTHONPATH=tests python3 -m unittest tests.test_repo tests.test_context_budget`; `python3 tools/context_budget.py --root .`; `claude plugin validate .` |
| P03 | `docs/hosts.md` runtime host map and autonomy rule | none | A | terra / low | normal | M | none | `rg -c '^## ' docs/hosts.md`; `PYTHONPATH=tests python3 -m unittest tests.test_repo` |
| P05 | Hook host adapter for the three wired hooks | none | A | terra / medium | normal | M | none | `PYTHONPATH=tests python3 -m unittest tests.test_hooks tests.test_hook_schedule tests.test_context_budget tests.test_doctor tests.test_regression_notice tests.test_usage_guard` (or `python3 -m unittest discover -s tests -p 'test_hook*.py'`); `shellcheck -S warning hooks/*.sh`; `git diff --exit-code d1accc4 -- hooks/hooks.json` |
| P06 | Host-aware script messages (`kaizen-doctor`, `kaizen-scan`, `token-audit`) | none | A | terra / medium | normal | M | none | `PYTHONPATH=tests python3 -m unittest tests.test_doctor tests.test_scan tests.test_token_audit_fixes tests.test_scripts tests.test_runner`; `python3 tests/bench_token_audit.py --baseline HEAD --max-ratio 1.10`; end-to-end `--no-write` timing (see P06 notes) |
| P04 | Skill preamble, `codex-dispatch` note, repo tests | P02, P03 | B | terra / low | normal | M | none | `PYTHONPATH=tests python3 -m unittest tests.test_repo tests.test_flow_skill tests.test_process_rules tests.test_schedule_steps tests.test_scan`; `claude plugin validate .`; `git diff --numstat -- skills/*/SKILL.md agents/kaizen-auditor.md` |
| P08 | CI and repo rules (`host probe` stage, Codex in CI, rule wording) | P01, P02 | B | terra / medium | low | S | none (D3 decided: yes) | `tools/ci-local --skip-tests` (stage runs the probe with `--worktree`); same with a `PATH` that has no `codex` or `copilot` (stage prints SKIP); `yq e . .github/workflows/ci.yml >/dev/null`; `PYTHONPATH=tests python3 -m unittest tests.test_repo` |
| P07 | README install per host, hosts table, manifest descriptions | P01-P06 | C | luna / low | low | M | none (D1, D2 decided: yes) | `python3 -m unittest tests.test_repo`; `claude plugin validate .`; `jq -r .description .claude-plugin/plugin.json` |
| P09 | Release 0.12.0 and end-to-end gate | all | D | terra / medium | low | S | none | `tools/ci-local`; `UV_OFFLINE=1 tools/ci-local --python 3.9`; `tools/host-probe --host all --worktree` (Codex all PASS); `git diff --exit-code d1accc4 -- hooks/hooks.json` |

Parallel groups (separate worktrees, no shared files within a group):
- **A, start now:** P01, P02, P03, P05, P06. File sets are disjoint: P01 owns `tools/host-probe`, `tests/test_host_probe.py`, `probe-results.md`; P02 owns `skills/*/agents/openai.yaml`, `tests/test_repo.py`, `tools/context_budget.py`, `tests/test_context_budget.py`, `changelog/P02.md`; P03 owns `docs/hosts.md`, `docs/autonomy.md`, `changelog/P03.md`; P05 owns the three hooks, `tests/test_hooks.py`, `tests/test_hook_schedule.py`, `tests/test_regression_notice.py` (and `tests/test_usage_guard.py`, `tests/test_schedule_robustness.py` only if the env-scrub check in P05 fails), `tests/fixtures/hooks/*`, `tools/context-budget.json`, `changelog/P05.md`; P06 owns `scripts/kaizen-doctor`, `scripts/kaizen-scan`, `scripts/token-audit`, `scripts/README.md`, `tests/test_doctor.py`, `tests/test_scan.py`, `tests/test_token_audit_fixes.py`, `changelog/P06.md`.
- **B:** P04 (after P02 and P03; it also edits `tests/test_repo.py`) and P08 (after P01 and P02: the probe's "zero skills" check fails without the P02 sidecars) run in parallel with each other. They share no files.
- **C:** P07 after A and B land (its claims must match probe output and the code), once D1 and D2 are answered.
- **D:** P09 last.

## Packet notes

### P01 `tools/host-probe` (terra/medium, low)
- Scope: new stdlib Python 3.9 executable `tools/host-probe` with `--host codex|copilot|all`, `--source PATH` (default repo root), `--expect-hidden-skills` (default on), `--json`. It never touches the real home: makes a temp dir with `tempfile.mkdtemp()` (system temp, never under the repo, since Codex copies the tree and a home inside it recurses), exports the tree with `git archive HEAD | tar -x` into it (so `out/`, `.git`, `.claude/` are not copied; `--worktree` flag exports `git ls-files` instead to include uncommitted tracked edits), sets `HOME`, `CODEX_HOME`, `COPILOT_HOME` and the `XDG_*` dirs to sub-dirs (dropping any inherited `CODEX_*`, `COPILOT_*`, `KAIZEN_*`, `CLAUDE_*`, `XDG_*` variable), and runs with a timeout per command. `tempfile.mkdtemp()` honours a `TMPDIR` override (the sandbox may need one); the export, never the checkout, is what the host CLI installs from.
- Codex checks: `codex plugin marketplace add <export>`; `codex plugin add agent-kaizen@agent-kaizen-tools`; installed path `$CODEX_HOME/plugins/cache/agent-kaizen-tools/agent-kaizen/<version>` exists and `<version>` equals `.claude-plugin/plugin.json`; `codex debug prompt-input` lists zero `agent-kaizen:` skills (FAIL on the 0.11.0 tree: 22 listed), counted only when the command exited 0 and printed valid JSON that contains at least one skill-list line (non-zero exit or invalid JSON is FAIL; valid JSON with no skill lines is SKIP, never PASS); hooks discovered: exactly the 4 expected registrations from `hooks/hooks.json` (`postToolUse` x1, `sessionStart` x2, `userPromptSubmit` x1, all with the plugin id) via `codex app-server` `hooks/list`, FAIL when any is missing (Fable did this on 0.167.0; if the JSON-RPC call is not workable in under ~60 lines, report the check as SKIP with a reason, do not guess).
- Copilot checks: run only when `copilot` is on PATH; `copilot plugin marketplace add <export>`, `copilot plugin install agent-kaizen@agent-kaizen-tools`, assert `$COPILOT_HOME/installed-plugins/agent-kaizen-tools/agent-kaizen` exists. If any command needs sign-in, print SKIP (needs sign-in), exit 0.
- Missing CLI: SKIP line, exit 0. Any FAIL: exit 1. Output one `PASS|FAIL|SKIP <host> <check>: <detail>` line per check.
- Tests: `tests/test_host_probe.py` with a stub `codex` script on a temp `PATH` that prints canned outputs (22 skills vs 0; failing and invalid prompt output; 1 of 4 hooks), asserting exit codes, the SKIP path, that `HOME`, `CODEX_HOME`, `COPILOT_HOME` and `XDG_*` passed to the stub are under the temp dir (even when the parent environment sets them to other values), and that the missing-CLI test uses a tools-only `PATH` (wrapper scripts for `git`, `tar`, `python3` only) so a real `codex` or `copilot` is unreachable.
- Writes `docs/plans/2026-11-17-multi-host/probe-results.md` with the trimmed run on the current tree (codex-cli version, date, lines; `not run: <reason>` if blocked), and the owner-check tables O1, O2, O3, O5 (O1/O2 include: capture the raw hook payload keys and event names Copilot sends, and invoke a skill from an unrelated project after P04).
- Files: `tools/host-probe`, `tests/test_host_probe.py`, `docs/plans/2026-11-17-multi-host/probe-results.md`. No changelog file (tools/ is not shipped at runtime).
- Accept: (1) `--help` exits 0; (2) on 0.11.0 tree install and version PASS, hidden-skills FAIL with "22 listed"; (3) no files written outside the temp dir (check `git status --short --untracked-files=all` shows only the three files); (4) tests pass on Python 3.9 syntax (no 3.10+ features).

### P02 Codex skill visibility (terra/low, low)
- Scope: create `skills/<name>/agents/openai.yaml` for all 22 skills with exactly:
  ```
  policy:
    allow_implicit_invocation: false
  ```
  Command: `for d in skills/*/; do mkdir -p "$d/agents"; printf 'policy:\n  allow_implicit_invocation: false\n' > "$d/agents/openai.yaml"; done`.
- `tests/test_repo.py`: new test, every skill folder has that file with exactly that content.
- `tools/context_budget.py`: a skill counts as visible if it is visible to Claude (`disable-model-invocation != true`) or to Codex (no `agents/openai.yaml` with `allow_implicit_invocation: false`; parse the two lines with a regex, no YAML library). Print `(disabled)` only when hidden on both. Add cases to `tests/test_context_budget.py` (missing sidecar counts; sidecar present counts 0). Do not edit `tools/context-budget.json`.
- Changelog file `changelog/P02.md`: "Codex no longer lists every skill on every turn: each skill ships `agents/openai.yaml` with implicit invocation off."
- Accept: test fails when one sidecar is removed; budget still under 1,024 bytes; `claude plugin validate .` passes; `git status` shows 22 new files plus the 3 edited files and the changelog file.

### P03 `docs/hosts.md` and autonomy rule (terra/low, normal)
- Scope: new `docs/hosts.md` (read by skills at runtime, so it is under the version rule; target under 200 lines). One `##` section each: Claude Code, Codex CLI, Copilot runtime (Copilot CLI and VS Code Copilot harness), Not supported (Codex IDE extension, Copilot cloud agent, VS Code Local harness). Each host section, short lines: how to tell you are in it (env vars above; Codex lists skills as `agent-kaizen:<name>` and is invoked with `$agent-kaizen:<name>`; Copilot `/agent-kaizen:<name>`); config dir (`~/.codex`/`$CODEX_HOME`; `~/.copilot`/`$COPILOT_HOME`); instruction files (Codex `AGENTS.md`; Copilot `AGENTS.md`, `.github/copilot-instructions.md`, `.github/instructions/*.instructions.md`, `~/.copilot/copilot-instructions.md`); where agents and hooks are defined; skill invocation; headless command (`codex exec`, `copilot -p`); session logs (`$CODEX_HOME/sessions/YYYY/MM/DD/rollout-*.jsonl`, measured; `~/.copilot/session-state/<id>/events.jsonl`, not measured yet); Kaizen state stays in `${CLAUDE_CONFIG_DIR:-~/.claude}` (D1 default, say "for now"); a per-feature line: works / degraded / not available, using the capability matrix in `design.md` lines 91-137, with every item not probed marked "unverified".
- Codex section must say: hooks do nothing until trusted in `/hooks`, and a release that changes a hook script asks again; `PostToolUseFailure` is not a Codex event; there is no `Read` tool, so read guards do not apply; `codex-dispatch` has no use inside Codex; scripts print `/agent-kaizen:<name>` in their messages, and on Codex you type `$agent-kaizen:<name>` (follow-up F6).
- Safety rule (also added as a short paragraph to `docs/autonomy.md`): on hosts other than Claude Code, changes to that host's settings, hooks and agent files are proposals only in every mode until this file marks the file verified. Covered: those files in the host's user config directory and in the project (`.codex/` such as `.codex/agents/`, `.github/hooks/`), and the host's user-level instruction files (`~/.copilot/copilot-instructions.md`). Not covered: git-tracked project instruction files (`AGENTS.md`, `.github/copilot-instructions.md`, `.github/instructions/`) and `docs/kaizen/`, which follow the normal autonomy rules. The `Safety rule` section also lists the Claude-only steps to skip on other hosts (Claude settings files, `claude` commands, `kaizen-link`), so the P04 preamble can point to it.
- The file opens with a short "Plugin root" paragraph: where each host puts it; substitute the resolved, quoted path for `CLAUDE_PLUGIN_ROOT` in skill commands; if it cannot be resolved, say so in one line and stop that step. Copilot: whether the model is told the skill path is unverified (O1).
- Files: `docs/hosts.md`, `docs/autonomy.md`, `changelog/P03.md`.
- Accept: four `##` host sections; no home-directory absolute paths (use `~` forms; privacy test passes); every unverified claim labelled; `docs/autonomy.md` diff is one paragraph.

### P04 Skill preamble and repo tests (terra/low, normal; after P02, P03)
- Scope: insert under the first `# ` heading of each of the 22 `SKILL.md` files, then a blank line, exactly (two lines):
  ```
  **Plugin root:** `${CLAUDE_PLUGIN_ROOT}`. If that is still a `${...}` placeholder, use the folder that contains `skills/` (this file is `skills/<name>/SKILL.md`), and substitute that path, in quotes, wherever this skill uses `CLAUDE_PLUGIN_ROOT`.
  **Not in Claude Code?** Read `docs/hosts.md` in the plugin root first. Skip steps that only work in Claude Code, and follow its propose-only rule before changing any host configuration.
  ```
  Use a short Python one-off (not hand edits) that inserts after the first line starting with `# ` and is idempotent. The agent file `agents/kaizen-auditor.md` has no heading: add the same two lines after its frontmatter's closing `---` and blank line, with "the folder that contains `skills/` (this file is `skills/<name>/SKILL.md`)" changed to "the folder that contains `agents/` (this file is `agents/kaizen-auditor.md`)". The pinned strings in the test are the same as these.
- `skills/codex-dispatch/SKILL.md`: one added line after the preamble: "Inside Codex, this skill does not apply: do the work in the current session."
- `tests/test_repo.py`: preamble present exactly once in every skill, with the exact skill text and the agent variant; `docs/hosts.md` exists and contains the headings "Claude Code", "Codex CLI", "Copilot".
- Files: `skills/*/SKILL.md`, `agents/kaizen-auditor.md`, `tests/test_repo.py`, `changelog/P04.md`.
- Accept: `git diff --numstat -- skills/*/SKILL.md agents/kaizen-auditor.md` shows 0 deleted and at most 3 added lines per file (one more for `codex-dispatch`); no other skill text changed; all listed tests pass; context budget unchanged (descriptions untouched). After P04, O1/O2 invoke a skill from an unrelated project and check the model resolves the plugin path.

### P05 Hook host adapter (terra/medium, normal)
- Scope: one identical helper block between `# --- host helper ---` and `# --- end host helper ---` in `hooks/audit-notice.sh`, `hooks/session-audit.sh`, `hooks/bash-burst.sh`. It sets `kaizen_host` (detection order in Assumptions) using bash builtins only (`tests/test_hooks.py:559` runs a hook with a bare `PATH`), and defines `kaizen_context EVENT TEXT`: for Claude and Codex it runs the same `jq -n --arg` call with the same filter and flags as today (`{hookSpecificOutput:{hookEventName:EVENT,additionalContext:TEXT}}`, no `-c`, so the output stays jq's default multi-line form and Claude stdout stays byte-identical); for Copilot `{additionalContext:TEXT}` (same call style). There is no single-line requirement.
- `audit-notice.sh`: use `kaizen_context` at `:162`; skill wording at `:78` and `:123` becomes `/agent-kaizen:review` on Claude and Copilot, `$agent-kaizen:review` on Codex. Quiet `{}` at `:8` unchanged.
- `session-audit.sh`: root from `${CLAUDE_PLUGIN_ROOT:-${PLUGIN_ROOT:-}}`; on Copilot, detach the `kaizen-scheduled auto-audit` call (background it with stdio closed and return at once), since `async` is not documented there. Claude and Codex path unchanged.
- `bash-burst.sh`: the Claude filter at `:29` (`$tool == Bash`) is unchanged for Claude and Codex; on Copilot it also accepts `bash`. Use `kaizen_context` at `:41`. `hooks/hooks.json` is not changed (its `Bash` matcher stays); whether Copilot delivers its `bash` events through that matcher is an O1 check, and C1 is the fallback.
- Tests: `tests/test_hooks.py` golden test: for each existing input with no host variables set, the complete stdout (multi-line jq output included) equals a stored 0.11.0 value (capture with `git show d1accc4:hooks/<file>` run on the same inputs). New fixtures `tests/fixtures/hooks/codex_*.json` and `copilot_*.json`; Codex run with `PLUGIN_ROOT` and `CLAUDE_PLUGIN_ROOT` set, Copilot with all three set; assert shapes above; lowercase `bash` gives no nudge on Claude and Codex and a nudge on Copilot. Test that the helper block is byte-identical in the three files. Env scrub: drop `KAIZEN_HOST`, `PLUGIN_ROOT`, `COPILOT_PLUGIN_ROOT` from the inherited environment in `test_hooks.run_raw` (this also covers `tests/test_usage_guard.py` and `tests/test_schedule_robustness.py`, which import it), in `tests/test_hook_schedule.py` and in `tests/test_regression_notice.py`; check with `KAIZEN_HOST=codex PLUGIN_ROOT=x COPILOT_PLUGIN_ROOT=y PYTHONPATH=tests python3 -m unittest tests.test_hooks tests.test_hook_schedule tests.test_usage_guard tests.test_schedule_robustness tests.test_regression_notice`.
- `tools/context-budget.json`: the hook text a Claude session sees does not change, so preserve `literal_text` and `literal_bytes` exactly and update only the three `sha256` values (`shasum -a 256 hooks/<file>`). `tools/context_budget.py` has only `--root` (no write flag): run it, read the mismatch it reports, edit the three values. `git diff -U0 tools/context-budget.json` shows only `sha256` lines.
- Files: the three hooks, `tests/test_hooks.py`, `tests/test_hook_schedule.py`, `tests/test_regression_notice.py`, `tests/fixtures/hooks/*`, `tools/context-budget.json`, `changelog/P05.md`; `tests/test_usage_guard.py` and `tests/test_schedule_robustness.py` only if the env-scrub check above fails.
- Accept: Claude output byte-identical (golden, full stdout); Codex and Copilot fixtures give the shapes above; `hooks/hooks.json` identical to `d1accc4`; `kaizen-doctor` hook check still passes (`tests.test_doctor`); shellcheck clean; budget stage passes with the total unchanged (823 bytes).

### P06 Host-aware script messages (terra/medium, normal)
- Scope: `scripts/kaizen-doctor` reports which hosts have the plugin: Claude registry (`:59`), Codex cache `${CODEX_HOME:-~/.codex}/plugins/cache/agent-kaizen-tools/agent-kaizen/`, Copilot `${COPILOT_HOME:-~/.copilot}/installed-plugins/agent-kaizen-tools/agent-kaizen`. Fix lines per host (`codex plugin add agent-kaizen@agent-kaizen-tools`; `copilot plugin install agent-kaizen@agent-kaizen-tools`); Claude-only fixes (`claude plugin ...`, `kaizen-link --apply`) only when Claude Code is installed (registry present). When only Codex has it, one INFO line: "Codex: run /hooks once to trust the plugin hooks". `scripts/kaizen-scan:89` wording drops "use Claude Code or Codex" where wrong; when `~/.copilot/session-state/` exists, `kaizen-scan` and `token-audit` print one line "Copilot sessions found but not measured in this version". The `token-audit` line is printed unconditionally, after (outside) the "no Claude Code projects" if-block. `kaizen-scan --demo` sets `COPILOT_HOME` to a path inside its demo temp home (next to the existing `CODEX_HOME` at `kaizen-scan:78-79`) so an inherited real `COPILOT_HOME` cannot change demo output. The `token-audit` change must not slow the scan (one `os.path.isdir`). Update `scripts/README.md` accordingly.
- Tests: `tests/test_doctor.py` (temp home with only a Codex cache: no Claude-only fix lines; Claude-only home: output unchanged), `tests/test_scan.py`, `tests/test_token_audit_fixes.py` (Copilot dir line); `--demo` test with a populated external `COPILOT_HOME` in the parent env: no Copilot text.
- Files: `scripts/kaizen-doctor`, `scripts/kaizen-scan`, `scripts/token-audit`, `scripts/README.md`, the three tests, `changelog/P06.md`.
- Accept: Claude-only output unchanged; bench median ratio ≤ 1.10 vs `HEAD` (take the baseline before editing; paste both numbers in the report); the bench times `collect()` only, so also time the end-to-end check once before and once after editing: `time (for i in 1 2 3 4 5; do python3 scripts/token-audit --no-write >/dev/null 2>&1; done)` against `git show HEAD:scripts/token-audit` saved to a temp file, same `CLAUDE_CONFIG_DIR` fixture or empty temp dir, report both; scripts still answer `--help`.

### P07 README and manifest wording (luna/low, low; after A and B; D1, D2)
- Scope: README `## Quick start` (`README.md:61`): one install block per host with exact commands: Codex `codex plugin marketplace add HighwayofLife/agent-kaizen`, `codex plugin add agent-kaizen@agent-kaizen-tools`, new session, `/hooks` once to trust; skills `$agent-kaizen:scan`. Copilot CLI `copilot plugin marketplace add HighwayofLife/agent-kaizen`, `copilot plugin install agent-kaizen@agent-kaizen-tools`; skills `/agent-kaizen:scan`. VS Code: set `chat.plugins.enabled`, choose the Copilot session target, Chat: Install Plugin from Source with the repo URL; a Copilot CLI install is also picked up. Hosts table (Install / Skills / Session notice / Agent / Usage measured) from `design.md` lines 93-100 minus the Codex IDE row, filtered to what `probe-results.md` shows or marked experimental (D2). One line: Codex IDE extension and Copilot cloud agent are not supported. The D1 state note. Versions table (`:65-69`): add a Codex row only for the version probed (0.167.0); no Copilot row until O1.
- `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`: `description` wording only; each sentence that says Copilot works says it is experimental (for example "... with Codex CLI and GitHub Copilot support (experimental on Copilot): ..."), and the plugin entry does not imply the auditor agent runs outside Claude Code. `docs/scheduling.md`: one note that scheduled reviews run only through Claude Code for now.
- Files: `README.md`, `.claude-plugin/plugin.json` (description only), `.claude-plugin/marketplace.json` (description only), `docs/scheduling.md`, `changelog/P07.md`.
- D1 and D2 are resolved: yes; the brief's text is used as written. Step 0 (running the probe) is optional.
- Accept: skills table test passes; `jq` shows `name` and `version` unchanged; every sentence or table row that says Copilot works (installs, runs, loads) contains "experimental", "not yet" or "not verified"; every capability claim matches `probe-results.md`, O1 results, or says experimental; changed files checked with `git status --short --untracked-files=all` and `git diff --stat`.

### P08 CI and repo rules (terra/medium, low; after P01 and P02; D3 = yes)
- Scope: `tools/ci-local`: new stage `host probe` running `tools/host-probe --host all --worktree` (so a local run probes the tree being checked, not the committed HEAD, and matches the direct probe in P09), SKIP when neither `codex` nor `copilot` is on PATH (same pattern as the `claude` plugin validation stage). `.github/workflows/ci.yml` `checks` job: `npm install -g @openai/codex` next to the Claude Code install (pin nothing; the probe needs no sign-in, verified on 0.167.0). D3 = yes (decided): add `pull_request: branches: [main]` under `on:`. `AGENTS.md:19` and `CONTRIBUTING.md:21`: add `docs/hosts.md` to the runtime-read docs list; mention `skills/*/agents/openai.yaml` is under `skills/`; commands list gains `tools/host-probe --host codex`; fix "CI enforces this on PRs" per D3 = yes.
- Files: `tools/ci-local`, `.github/workflows/ci.yml`, `AGENTS.md`, `CONTRIBUTING.md`.
- Accept: `tools/ci-local --skip-tests` passes with `codex` on PATH (if the sandbox blocks the probe with an OS or network error, record `not run: <reason>` and add it to O5; a product FAIL stops the packet) and prints `SKIP` for the `host probe` stage when run with a `PATH` that has no `codex` or `copilot`; `yq e . .github/workflows/ci.yml` parses (or `ruby -ryaml -e 'YAML.load_file(".github/workflows/ci.yml")'`); AGENTS.md and CONTRIBUTING.md list the same runtime paths.

### P09 Release 0.12.0 and end-to-end gate (terra/medium, low; last)
- Scope: bump `version` to 0.12.0 in `.claude-plugin/plugin.json` (and in `.github/plugin/plugin.json` when C1 landed; verify parity afterwards); add `## 0.12.0 (YYYY-MM-DD)` to `CHANGELOG.md` from `changelog/P*.md` (and `C1.md` when present), plus a line that Codex users must re-trust hooks after updates. Fragment group headings are fixed: P02 `` `skills/*/agents/openai.yaml`: ``; P03 `` `docs/hosts.md`, `docs/autonomy.md`: ``; P04 `` `skills`: ``; P05 `` `hooks`: ``; P06 `` `kaizen-doctor`, `kaizen-scan`, `token-audit`: ``; P07 as written in its fragment; C1 `` `.github/plugin/plugin.json`, `hosts/copilot/hooks.json`: ``. Run the end-to-end gate on the final tree and paste trimmed output into the P09 result block of this plan: `tools/host-probe --host all --worktree`, `tools/ci-local`, `UV_OFFLINE=1 tools/ci-local --python 3.9`, `git diff --exit-code d1accc4 -- hooks/hooks.json`. Blocked runs are written as `not run: <reason>` and go to O5; they are not passes.
- Files: `.claude-plugin/plugin.json` (version only), `.github/plugin/plugin.json` (version only, only if C1 landed), `CHANGELOG.md`, this `plan.md` (P09 result block), delete nothing.
- Accept: all runnable gate commands pass; host probe shows installed version 0.12.0 and zero `agent-kaizen:` skills listed on Codex (or `not run: <reason>`); open O1/O2 rows are listed as experimental in README (else stop and report); new files checked with `git status --short --untracked-files=all`.

## Owner checklist (needs a signed-in host or a human; not coding packets)

Record results in `docs/plans/2026-11-17-multi-host/probe-results.md` under "Owner checks". Use a throwaway project.

- **O1 Copilot CLI (signed in)**, after P05: install with the P07 commands; `/skills` shows `agent-kaizen:*` and none is invoked unprompted (disable-model-invocation); `hooks/hooks.json` loads with no error; `SessionStart` with matcher `startup|resume` fires on a new session and the audit notice appears (create an unreviewed audit with `scripts/kaizen-scheduled` or a fixture); `"async": true` is ignored, honoured or rejected; a `Bash` call 8 times in one turn gives the nudge (check `tool_name` seen); whether `agents/kaizen-auditor.md` loads and what `model: sonnet` does; whether the model gets the skill's folder path; capture the raw hook payload (keys, event names, `tool_name` casing) Copilot sends for each wired hook, and whether the matcher `Bash` in the shared `hooks/hooks.json` delivers the `bash` tool's events (if not, run C1); after P04, invoke a skill from an unrelated project and check the model resolves the plugin path and runs the bundled script. Then the same install in VS Code with the Copilot harness.
- **O2 Codex CLI live session (signed in)**, after P05: trust hooks in `/hooks`; notice appears on start; what the quiet `{}` shows; whether tool hooks inside a subagent carry `agent_id` (bash-burst skips subagents by it); `$agent-kaizen:scan` runs the script from the cached root; capture the raw hook payload keys and event names; after P04, invoke a skill from an unrelated project and check the plugin path resolves.
- **O3 Codex IDE extension**: do IDE sessions land in `$CODEX_HOME/sessions` so `token-audit` measures them (README can then say "measured, no plugin").
- **O4 Decisions D1 to D4**: decided 2026-11-17 (see above).
- **O5 Runs the sandbox cannot do**, before release: `tools/host-probe --host all --worktree` and `tools/ci-local --python 3.9` outside the sandbox (network, Python 3.9 download, real CLIs). Paste the output into `probe-results.md`.

If O1 shows the shared `hooks/hooks.json` cannot serve Copilot (file rejected, `SessionStart` not firing, or the `bash` tool's events dropped by the `Bash` matcher), run contingent packet C1.

## Contingent packet

- **C1 Copilot-only manifest (terra/medium, normal; only if O1 fails on hooks):** add `.github/plugin/plugin.json` pointing at `hosts/copilot/hooks.json` (Copilot reads it before `.claude-plugin/`; Claude Code and Codex do not), plus a `tests/test_repo.py` check that its `name` and `version` equal `.claude-plugin/plugin.json`, and a `tools/host-probe` check. Lands after P08 and before P09; P09 then bumps both manifests, merges `changelog/C1.md` and checks that the two versions match (the parity test in `tests/test_repo.py` fails otherwise).

## Follow-ups (separate plan after 0.12.0, D4)

- F1 Guardrail hooks on Codex and Copilot (high): wiring templates for `~/.codex/hooks.json` and `~/.copilot/hooks/`, Copilot `Read` argument mapping (command `preToolUse` is fail-closed), `kaizen-link --host`, guardrails skill sections.
- F2 Copilot usage in `token-audit` (high): `session-state/*/events.jsonl`, schema undocumented; format canary, synthetic fixtures, AI-credit prices copied from the vendor page.
- F3 Scheduled review on other hosts (normal): runner setting for `codex exec` / `copilot -p` in `kaizen-scheduled`.
- F4 Native auditor agents (normal): generated `kaizen-auditor.toml` for Codex, `.agent.md` for Copilot if O1 shows `.md` does not load.
- F5 `KAIZEN_HOME` state root (high: touches the paths helper x4 and ~40 references), if users ask.
- F6 Host-aware skill prefix in script messages (low): scripts print `/agent-kaizen:<name>`; on Codex the prefix is `$agent-kaizen:<name>`. Use `KAIZEN_HOST` or the plugin-root variables to choose it (P03 documents the difference meanwhile).
- Install size: Codex caches the whole repo per version (25 MB from GitHub); consider moving large assets out of the plugin tree.

## Traceability

| Requirement | Packets |
|---|---|
| Works in Codex CLI | P02, P04, P05, P06, P07; checked by P01, P09, O2 |
| Codex IDE | out of scope (no plugin support); O3 for usage only |
| Copilot CLI and VS Code Copilot | P03, P04, P05, P06, P07; O1; C1 if needed |
| Claude Code unchanged | P05 golden test, P09 `hooks/hooks.json` diff, full suite in every packet |
| Any user's setup | P01 isolated homes; P06 env-var homes; privacy test; no owner paths |
| Version/changelog once | P09 |

## End-to-end verification

P09 runs `tools/host-probe --host all --worktree`, `tools/ci-local`, `tools/ci-local --python 3.9`, and the `hooks/hooks.json` diff, and pastes the trimmed output here. The plan is not done until that run is clean and O1/O2 rows are either filled or listed as experimental in README.

## Risks and mitigations

1. Copilot is documented, not probed: O1 before the README claims anything beyond "experimental"; C1 ready.
2. Codex hooks silent until trusted, and re-trust after hook changes: README, CHANGELOG, `docs/hosts.md`, `kaizen-doctor` say it.
3. Claude-format loading is "legacy" on both hosts: the host probe in CI is the alarm.
4. Preamble relies on the model following two lines: low; Codex gives the skill file path (probed).
5. Copilot command `preToolUse` fails closed: no `preToolUse` hooks wired in this plan.
6. Probe results depend on the environment: a sandbox without a writable temp dir, network or Python 3.9 cannot run them; briefs record `not run: <reason>` and O5 covers the release run.
7. Codex session store may move ("paginated thread history"): format canary flags it; not handled here.

## Rollout / rollback

One branch, one 0.12.0 release. Rollback: revert the branch; Claude Code users are unaffected either way because Claude output and `hooks/hooks.json` are pinned. Users on other hosts uninstall with `codex plugin remove agent-kaizen@agent-kaizen-tools` or Copilot's plugin uninstall command (exact syntax confirmed in O1).

## Open questions

None blocking beyond D1 to D4 and O1 to O3.
