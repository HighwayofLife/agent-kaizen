# Multi-host design: Codex and GitHub Copilot

Date: 2026-11-17. Baseline: v0.11.0 (`d1accc4`). Status: design, not yet planned into briefs.

## Summary

Keep one plugin tree in Claude Code format. Codex CLI and the Copilot runtime both load that format today, so no new manifest is needed. Fix the four places where the hosts differ (skill visibility on Codex, the plugin-root placeholder in skill text, hook output and tool names, Claude-only wording in scripts) inside the shared files, with small host files only where a host needs one that the others ignore.

Claude Code files that must stay byte-identical: `.claude-plugin/plugin.json` (except `version` and wording in `description`), `.claude-plugin/marketplace.json` (wording only), `hooks/hooks.json`.

## What was verified, and how

Three levels of evidence are used below. Do not treat them as equal.

- **Probed**: run locally on 2026-11-17 against the unmodified v0.11.0 tree, with `codex-cli 0.167.0`, an empty isolated `HOME` and `CODEX_HOME`, and no sign-in. Claude Code 2.1.327 for `claude plugin validate`.
- **Documented**: read in the vendor's current docs or changelog (see Sources). Not run.
- **Unverified**: neither. Listed under Risks with the check that settles it.

Copilot CLI is not installed on the design machine, so nothing about Copilot is probed.

### Probed on Codex CLI 0.167.0

| Check | Result |
|---|---|
| `codex plugin marketplace add <repo>` | Accepted `.claude-plugin/marketplace.json` as the marketplace file. |
| `codex plugin add agent-kaizen@agent-kaizen-tools` | Installed. Version `0.11.0` read from `.claude-plugin/plugin.json`. Whole repo copied to `$CODEX_HOME/plugins/cache/agent-kaizen-tools/agent-kaizen/0.11.0/`. |
| `codex debug prompt-input` | All 22 skills listed as `agent-kaizen:<name>` in the always-loaded skills list. `disable-model-invocation: true` is ignored. That is 3,810 bytes on every turn, against this repo's own 1,024-byte budget (`tools/context-budget.json`). |
| Same, after adding `skills/<name>/agents/openai.yaml` with `policy.allow_implicit_invocation: false` to 3 skills | Those 3 left the list (22 to 19). `claude plugin validate .` still passes with the extra files. |
| app-server `hooks/list` | 4 hooks found from `hooks/hooks.json`: `postToolUse` (matcher `Bash`), `sessionStart` x2 (`async: true` kept on `session-audit.sh`), `userPromptSubmit`. `${CLAUDE_PLUGIN_ROOT}` expanded to the cache path. `PostToolUseFailure` dropped with no warning or error. All four `trustStatus: untrusted`. |
| Agent | `agents/kaizen-auditor.md` not loaded. Nothing about it reaches the prompt. |
| `token-audit`, `kaizen-scan`, `kaizen-doctor` with no Claude config dir | All exit 0. `token-audit` prints `FORMAT-DRIFT: no transcript data observed`. `kaizen-doctor` prints Claude-only fixes (`kaizen-link --apply`, `claude plugin ...`). |

### Documented, per host

| Topic | Codex CLI | Copilot runtime (Copilot CLI, VS Code Copilot harness, Copilot app) |
|---|---|---|
| Plugin manifest | Root `plugin.json` (Agent Plugins), `.codex-plugin/plugin.json` fallback, "legacy and Claude-compatible manifests" accepted. | Root `plugin.json` in Agent Plugins format wins if present. Otherwise legacy, checked in order: `.plugin/plugin.json`, `plugin.json`, `.github/plugin/plugin.json`, `.claude-plugin/plugin.json`. |
| Marketplace file | `.agents/plugins/marketplace.json`; `.claude-plugin/marketplace.json` read as legacy. | `marketplace.json`, `.plugin/`, `.github/plugin/`, `.claude-plugin/` (in that order). |
| Install | `codex plugin marketplace add OWNER/REPO`, `codex plugin add PLUGIN@MARKETPLACE`, or `/plugins` in the TUI. | `copilot plugin marketplace add OWNER/REPO`, `copilot plugin install PLUGIN@MARKETPLACE` (or `OWNER/REPO`, a Git URL, a local path). VS Code: Chat: Install Plugin from Source, and it also discovers `~/.copilot/installed-plugins/`. Needs `chat.plugins.enabled`. |
| Skill naming | `agent-kaizen:<name>`, invoked with `$` or `/skills`. | `/agent-kaizen:<name>` (plugin name is the prefix). |
| `disable-model-invocation` | Not honoured. Use `agents/openai.yaml`. | Honoured (changelog: "Fully honor the skill disable-model-invocation flag"). `argument-hint` supported. |
| Skill discovery outside plugins | `.agents/skills` up to repo root, `~/.agents/skills`, `/etc/codex/skills`. | `.github/skills`, `~/.copilot/skills`. |
| Agents | TOML files in `~/.codex/agents/` or `.codex/agents/` (`name`, `description`, `developer_instructions`, optional `model`, `model_reasoning_effort`). Plugins bundling agents is not documented. | `.agent.md` in a legacy plugin's `agents/`. Tool aliases accept `Read`, `Grep`, `Glob`, `Bash`, `WebFetch`, `WebSearch`; unknown tools are ignored. Whether a plain `.md` loads, and what `model: sonnet` does, is not stated. |
| Hook config | `hooks/hooks.json` in the plugin, `~/.codex/hooks.json`, `.codex/hooks.json`, or `[hooks]` in `config.toml`. Plugin hooks are skipped until the user trusts them in `/hooks`. | `hooks.json` or `hooks/hooks.json` in the plugin, `~/.copilot/hooks/*.json`, `.github/hooks/*.json`, repo `.claude/settings.json`. Claude's nested `matcher`/`hooks` layout and PascalCase event names are accepted. |
| Hook events | 14, including `SessionStart` (sources `startup`, `resume`, `clear`, `compact`, `fork`), `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `SubagentStart`. No `PostToolUseFailure`. | Includes `sessionStart` (sources `startup`, `resume`, `new`), `userPromptSubmitted`, `preToolUse`, `postToolUse`, `postToolUseFailure`, `subagentStart`, `preCompact`. |
| Hook input | Claude-shaped: `session_id`, `cwd`, `hook_event_name`, `tool_name`, `tool_input`. Tool names `Bash`, `apply_patch`, MCP names; `spawn_agent` also matches `Agent`. There is no `Read` tool: files are read through the shell. | PascalCase event names get snake_case fields (`hook_event_name`, `session_id`, `cwd`, `tool_name`, `tool_input`). `PreToolUse` reports Claude tool names (`Bash`, `Read`, `Agent`). Tool arguments are Copilot's own, not Claude's. |
| Hook output | `hookSpecificOutput.additionalContext`, `permissionDecision: "deny"`. Same shape as Claude Code. | Top-level `additionalContext`, `permissionDecision`. `userPromptSubmitted` output is dropped. A crashed or non-zero `preToolUse` command hook **denies the tool call**. |
| Plugin root in hooks | `PLUGIN_ROOT`, plus `CLAUDE_PLUGIN_ROOT` for compatibility. | `PLUGIN_ROOT`, `COPILOT_PLUGIN_ROOT`, `CLAUDE_PLUGIN_ROOT`. |
| Async hooks | `"async": true` supported. | Not documented. Default timeout 30 s, fail-open on timeout. |
| Instruction files | `AGENTS.md`. | `AGENTS.md`, `.github/copilot-instructions.md`, `.github/instructions/*.instructions.md`, `~/.copilot/copilot-instructions.md`, `.claude/rules`. |
| Session logs | `$CODEX_HOME/sessions/YYYY/MM/DD/rollout-*.jsonl` (what `token-audit` reads now). A `codex migrate-rollouts` command moves sessions to "paginated thread history". | `~/.copilot/session-state/<id>/events.jsonl` (or `$COPILOT_HOME`). The event schema is not documented. Usage totals are written when a session ends. |

Other facts that shape the design:

- **VS Code is not a separate target.** VS Code now runs "harnesses". The Copilot harness is the same runtime as Copilot CLI, with the same hook format and plugin store. The old Local harness is deprecated and removed in February 2027. Design for the Copilot harness only.
- **Codex IDE extension:** "Plugins aren't available in the IDE extension."
- **Agent Plugins** (agent-plugins.org, v1.0.0) is an open plugin format backed by Microsoft, OpenAI, Cursor, Amazon and Vercel. It covers skills and MCP servers only. Hooks and agents live in per-client folders such as `com.github.copilot/`. Claude Code is not a listed client.

## Architecture

**One tree, Claude format, differences handled in the shared files.**

1. **Manifests:** none added. Codex is probed to install from the Claude manifests. Copilot is documented to.
2. **Skills:** one `SKILL.md` per skill, as now. Two additions:
   - A `skills/<name>/agents/openai.yaml` beside each skill, so Codex stops listing it on every turn. Claude Code and Copilot ignore the file.
   - A fixed two-line preamble under each skill's title:

     ```
     **Plugin root:** `${CLAUDE_PLUGIN_ROOT}`. If that is still a `${...}` placeholder, use the folder two levels above this file.
     **Not in Claude Code?** Read `docs/hosts.md` in the plugin root first.
     ```

     Claude Code substitutes the placeholder, so the first line reads as a plain path there. Other hosts hand the model the raw file and its location.
3. **`docs/hosts.md`:** a new file skills read at runtime, like `docs/autonomy.md`. One section per host: how to tell you are in it, config directory, instruction files, where agents and hooks are defined, MCP config, skill invocation syntax, headless command, session log location, and which Agent Kaizen features are verified there. It also states the safety rule in Decision D4.
4. **Hooks:** `hooks/hooks.json` stays as it is. Each hook script gets one identical helper block (same convention as the `# --- paths helper ---` block in `scripts/`, enforced by a test) that:
   - names the host: `KAIZEN_HOST` if set, else `copilot` when `COPILOT_PLUGIN_ROOT` is set, else `codex` when `PLUGIN_ROOT` is set, else `claude`;
   - emits context or a denial in that host's output shape.

   Claude Code output must stay byte-identical; a golden test pins it.
5. **Scripts:** stay host-neutral Python. State stays where it is (Decision D1). Only messages and install checks become host-aware.
6. **Agent:** `agents/kaizen-auditor.md` stays Claude-only for now. On other hosts the equivalent is the `cycle` skill with `propose-only`.

### The one fact that would change this

If the Copilot live check (packet 01) shows the shared `hooks/hooks.json` cannot serve Copilot (for example the `startup|resume` matcher stops `SessionStart` from firing, or `agents/kaizen-auditor.md` breaks loading), add a Copilot-only manifest at `.github/plugin/plugin.json` that points at `hosts/copilot/hooks.json`. Copilot reads that path before `.claude-plugin/plugin.json`; Claude Code and Codex do not read it at all. Then a test must assert its `name` and `version` equal `.claude-plugin/plugin.json`.

## Capability matrix

Legend: **as-is** works unchanged; **adapter** works after the named packet; **degraded** works with a stated limit; **no** not possible or not in scope.

### Hosts at a glance

| Host | Install | Skills | Session hooks | Agent | Usage measured |
|---|---|---|---|---|---|
| Claude Code | as-is | as-is | as-is | as-is | as-is |
| Codex CLI | as-is (probed) | adapter (02, 03) | as-is after `/hooks` trust | degraded: use `cycle propose-only` | as-is |
| Codex IDE extension | no (no plugin support) | no | no | no | as-is, if it shares `$CODEX_HOME/sessions` (unverified) |
| Copilot CLI | as-is (documented) | adapter (03) | adapter (04) | unverified, else degraded | no in this plan; follow-up 10 |
| VS Code, Copilot harness | as-is (documented) | adapter (03) | adapter (04) | unverified, else degraded | no in this plan; follow-up 10 |
| Copilot cloud agent | no | no | no | no | no |

### Skills

| Skills | Codex CLI | Copilot runtime |
|---|---|---|
| `start`, `scan`, `review`, `cycle`, `autonomy`, `undo`, `flow`, `planning`, `code-map`, `tools-before-tokens`, `test-loop`, `models`, `whats-new`, `roster` | adapter (03). Work on files under `docs/kaizen/` and bundled scripts. | adapter (03). |
| `audit` | adapter (03). Full Codex data. | degraded. Runs, but reports no Copilot sessions. Packet 05 makes it say so. |
| `slim-instructions`, `trim-context`, `lean-agents`, `batch-wakeups`, `schedule` | degraded. Text is written for Claude Code settings; `docs/hosts.md` maps paths. Host config changes are propose-only (D4). | degraded, same. |
| `guardrails` | degraded. Read guards do not apply (no `Read` tool). Compaction and subagent hooks are follow-up 09. | degraded until follow-up 09. |
| `codex-dispatch` | no. Codex handing work to Codex has no use. The skill says so. | adapter (03). Needs the `codex` CLI. |

### Hooks

| Hook | Codex CLI | Copilot runtime |
|---|---|---|
| `audit-notice.sh` (SessionStart) | as-is after trust. Wording adapter (04): `$agent-kaizen:review`. | adapter (04): top-level `additionalContext`. |
| `session-audit.sh` (SessionStart, async) | as-is after trust (`async` kept, probed). | adapter (04): detach itself, since async is not documented. |
| `bash-burst.sh` | degraded. Failed-call event is dropped (probed); subagent filter unverified. | adapter (04): output shape, tool name `bash` or `Bash`. |
| `limit-big-read.sh`, `block-image-read.sh` | no. Codex reads files through the shell. | follow-up 09: argument names differ; fail-closed risk. |
| `after-compact.sh` | follow-up 09 (wiring only; `compact` source exists). | no. No `compact` session source; `preCompact` output is ignored. |
| `subagent-context.sh` | follow-up 09 (wiring only). | follow-up 09 (field name `agentName`). |
| `session-notes.sh` | follow-up 09 (wiring only). | follow-up 09 (output shape). |
| `tier-guard.sh` | no in this plan. `spawn_agent` input differs. | no in this plan. `task` input differs. |

### Scripts, agent, templates

| Component | Codex CLI | Copilot runtime |
|---|---|---|
| `token-audit`, `usage-db`, `usage-series`, `usage-compare` | as-is. | degraded: Claude and Codex data only. |
| `kaizen-scan`, `kaizen-doctor` | adapter (05): host-aware messages and install checks. | adapter (05). |
| `kaizen-scheduled` audit job, `install-schedule` | as-is. | as-is (measures only Claude and Codex). |
| Scheduled review (`claude -p`) | no until follow-up 11. Run the cycle skill by hand when the notice appears. | same. |
| `kaizen-backup`, `notes-ledger`, `packet-*`, `flow-report`, `brief-lint`, `rules-lint`, `experiment-check` | as-is. | as-is. |
| `agents/kaizen-auditor.md` | degraded: not loaded. | unverified. |
| `templates/` | degraded: Claude and Codex templates only. | degraded: reference only. |

What a user sees when degraded: the skill preamble sends the model to `docs/hosts.md`, which says in one line per feature what is not available on that host. Scripts print one plain line (packet 05), for example `Copilot sessions found but not measured in this version`.

## Repo layout changes

```
skills/<name>/agents/openai.yaml     new x22   Codex: no implicit invocation
docs/hosts.md                        new       runtime host map, read by skills
tools/host-probe                     new       isolated-home install checks per host CLI
tests/fixtures/hooks/codex_*.json    new       hook inputs per host
tests/fixtures/hooks/copilot_*.json  new
```

No new top-level directory. No generated copies of skills or hooks. `hosts/copilot/` and `.github/plugin/plugin.json` only if the fallback above is triggered.

## Install docs per host (README)

- **Claude Code:** unchanged.
- **Codex CLI:** `codex plugin marketplace add HighwayofLife/agent-kaizen`, then `codex plugin add agent-kaizen@agent-kaizen-tools`, start a new session, run `/hooks` once to trust the three hooks. Skills are `$agent-kaizen:scan` and so on. Say that hooks do nothing until trusted.
- **Copilot CLI:** `copilot plugin marketplace add HighwayofLife/agent-kaizen`, then `copilot plugin install agent-kaizen@agent-kaizen-tools`. Skills are `/agent-kaizen:scan`.
- **VS Code:** set `chat.plugins.enabled`, pick the Copilot session target, then Chat: Install Plugin from Source with the repo URL. A Copilot CLI install is also picked up.
- One table: what works on each host (the "Hosts at a glance" table), and a line that Codex IDE extension and Copilot cloud agent are not supported.
- Minimum tested versions table gains rows only for versions actually probed.

## Tests and CI

- `tests/test_repo.py`: every skill has `agents/openai.yaml` with the exact policy; every `SKILL.md` has the exact preamble; `docs/hosts.md` exists and names each host.
- `tests/test_hooks.py`: for each plugin-wired hook, run the Claude, Codex and Copilot fixture. Claude output is compared to a stored golden value. The helper block is identical in every hook that has it.
- `tools/context_budget.py`: also count skill descriptions that Codex would list (a skill without the `openai.yaml` policy), so the 1,024-byte budget covers Codex.
- `tools/host-probe`: stdlib Python. With a temp `HOME`, `CODEX_HOME` and `COPILOT_HOME` it adds the repo as a marketplace, installs the plugin, and asserts: installed version equals `plugin.json`; Codex lists zero `agent-kaizen:` skills in `codex debug prompt-input`; Codex `hooks/list` returns the 4 expected hooks with no errors. Skips a host whose CLI is missing. None of this needed a sign-in on Codex 0.167.0.
- `tools/ci-local`: new stage `host probe`, skipped when no host CLI is found, like the `claude` stage. `ci.yml` installs the Codex CLI in the `checks` job. Add Copilot CLI there only if packet 01 shows its plugin commands run without sign-in.
- No validator CLI exists for Copilot plugins or Agent Plugins that was verified here.

## Version and changelog rule

- Add to the rule in `AGENTS.md`: `docs/hosts.md` (read at runtime) and `skills/*/agents/openai.yaml` (already under `skills/`).
- `version` stays in `.claude-plugin/plugin.json` only. Codex reads it from there (probed).
- If any second manifest is ever added, `tools/ci-local` and `tests/test_repo.py` must fail when its `name` or `version` differs.
- Packets in this plan collect changelog bullets in `changelog-bullets.md`; packet 08 bumps to 0.12.0 once.

## Decisions needed

| # | Decision | Recommendation |
|---|---|---|
| D1 | Where does state live for a user without Claude Code (config, audits, backups, usage DB)? | Keep `$CLAUDE_CONFIG_DIR` or `~/.claude` on every host for this release. One store means one ledger for people who use two hosts. A Codex-only user gets a `~/.claude/` folder holding only Agent Kaizen files; say so in the README. Moving it touches the paths helper (4 copies), about 40 references in `scripts/` and `hooks/` and 79 across shipped files, so do it later behind a `KAIZEN_HOME` override if users ask. |
| D2 | Add a root Agent Plugins `plugin.json` now? | No. In Copilot it would switch the plugin to Agent Plugins rules, which ignore root `agents/` and `hooks/hooks.json`. It adds nothing Codex or Copilot need today. Revisit if a host drops Claude-format loading (the host probe will fail when that happens). |
| D3 | Ship Copilot support before its usage can be measured? | Yes, labelled experimental: skills and session notices work, usage is not measured. The audit is the centre of the loop, so the README must not claim more. |
| D4 | On hosts other than Claude Code, may `safe` and `auto` modes edit host configuration? | No. Until a host's section in `docs/hosts.md` marks a file as verified, changes to that host's config are proposals only, whatever the mode. `kaizen-backup` only knows Claude paths. |
| D5 | Codex IDE extension and Copilot cloud agent. | Out of scope. The extension has no plugin support. The cloud agent runs in a throwaway sandbox with no user files, no installed plugins and no local logs. |
| D6 | Who runs the signed-in Copilot checks in packet 01? | The owner, once, following the checklist the packet produces. It needs a Copilot account and cannot run in CI. |
| D7 | Guardrail hooks, Copilot usage adapter, scheduled review on other hosts (packets 09 to 11). | Separate plan after 0.12.0, started only when packet 01 results are in. |

## Risks and unknowns

1. **Copilot is documented, not probed.** Settled by packet 01: does `hooks/hooks.json` load; does `SessionStart` fire with matcher `startup|resume`; is a Claude-shaped `hookSpecificOutput` accepted or only top-level fields; is `"async": true` ignored, honoured or rejected; does `agents/kaizen-auditor.md` load and what does `model: sonnet` do; is the skill's folder given to the model.
2. **Codex hooks are probed for discovery, not for a live run.** Unknown: whether tool hooks fired inside a subagent carry `agent_id` (bash-burst uses it to skip subagents); how the `{}` that `audit-notice.sh` prints on a quiet start is shown.
3. **Trust step on Codex.** Until `/hooks` is run, the plugin looks installed and does nothing at session start. The Codex docs add that an update which changes a bundled hook script needs a new review, so most releases will ask again. Install docs, the changelog and `kaizen-doctor` must say it.
4. **Claude-format loading is called "legacy" by both vendors.** It can be withdrawn. The host probe in CI is the alarm.
5. **Codex session store may change** (`migrate-rollouts`, "paginated thread history"). The format canary should flag it; not handled here.
6. **Copilot `preToolUse` fails closed.** A bug in a guard hook would block every matching tool call. This is why read guards for Copilot are a later, high-risk packet.
7. **The preamble depends on the model following two lines.** Low risk, but it is the only thing between a non-Claude host and a broken `${CLAUDE_PLUGIN_ROOT}/scripts/...` path.
8. **Install size.** Codex copies the whole repo (about 12.9 MB with the teaser and the white paper) into its cache for each version. Not fixed here.
9. **Windows.** Hooks are bash scripts on every host. Unchanged.

## Packet outline

Packets 01 to 08 are this plan. 09 to 11 are follow-ups (D7).

### 01 Host probe tool and results (low)
- Scope: write `tools/host-probe` (checks listed under Tests and CI). Record its output for Codex in `probe-results.md`. Write the signed-in checklist for Copilot and for a live Codex session (Risks 1 and 2) with a results table for the owner to fill in.
- Files: `tools/host-probe`, `docs/plans/2026-11-17-multi-host/probe-results.md`.
- Accept: on a machine with `codex`, the probe passes install and hook discovery and **fails** the "zero skills listed" check on the 0.11.0 tree (it passes after 02). Never touches the real home directories.
- Verify: `tools/host-probe --host codex`; `tools/host-probe --help`; `git status` shows no changes outside the two files.

### 02 Codex skill visibility (low)
- Scope: add `skills/<name>/agents/openai.yaml` (two lines) to all 22 skills. Extend the repo test and the context budget.
- Files: `skills/*/agents/openai.yaml`, `tests/test_repo.py`, `tools/context_budget.py`, `tools/context-budget.json`, `tests/test_context_budget.py`.
- Accept: test fails if a skill lacks the file or the policy; `claude plugin validate .` passes; probe lists zero `agent-kaizen:` skills.
- Verify: `python3 -m unittest tests.test_repo tests.test_context_budget`; `claude plugin validate .`; `tools/host-probe --host codex`.

### 03 Skill preamble and host map (normal)
- Scope: add the exact preamble to all 22 skills and the plugin-root line to `agents/kaizen-auditor.md`. Write `docs/hosts.md`. Add the D4 rule to `docs/autonomy.md`. Mark `codex-dispatch` as not applicable inside Codex.
- Files: `skills/*/SKILL.md`, `agents/kaizen-auditor.md`, `docs/hosts.md`, `docs/autonomy.md`, `tests/test_repo.py`.
- Accept: preamble identical in every skill (test); no other skill text changed; `docs/hosts.md` has a section each for Claude Code, Codex CLI and the Copilot runtime, and marks every unverified item as unverified.
- Verify: `python3 -m unittest tests.test_repo tests.test_flow_skill tests.test_process_rules`; `claude plugin validate .`; `git diff --stat` shows two added lines per skill.
- After 02 (both edit `tests/test_repo.py`).

### 04 Hook host adapter (normal)
- Scope: add the shared helper block to `audit-notice.sh`, `session-audit.sh`, `bash-burst.sh`. Host-specific output shape and skill syntax in notices; `bash-burst` accepts `bash` and `Bash`; `session-audit` detaches itself on Copilot. `hooks/hooks.json` unchanged.
- Files: `hooks/audit-notice.sh`, `hooks/session-audit.sh`, `hooks/bash-burst.sh`, `tests/test_hooks.py`, `tests/test_hook_schedule.py`, `tests/fixtures/hooks/*`, `tools/context-budget.json`.
- Accept: with no host variables set, output for every existing test input is byte-identical to 0.11.0; Codex and Copilot fixtures produce the documented shape; `kaizen-doctor` hook check still passes; shellcheck clean.
- Verify: `python3 -m unittest tests.test_hooks tests.test_hook_schedule tests.test_doctor tests.test_context_budget`; `shellcheck -S warning hooks/*.sh`; `git diff --exit-code hooks/hooks.json`.
- Needs the Copilot output-shape answer from 01. If it is not in, build the Codex side and leave Copilot emitting top-level fields as documented.

### 05 Host-aware script messages (normal)
- Scope: `kaizen-doctor` reports which hosts have the plugin installed (Claude registry, Codex cache, Copilot `installed-plugins`), gives fixes per host, and warns when Codex hooks are untrusted if that can be read cheaply. `kaizen-scan` and `token-audit` print one line when a Copilot session folder exists but is not measured, and drop "use Claude Code or Codex" wording where it is wrong.
- Files: `scripts/kaizen-doctor`, `scripts/kaizen-scan`, `scripts/token-audit`, `scripts/README.md`, `tests/test_doctor.py`, `tests/test_scan.py`, `tests/test_token_audit_fixes.py`.
- Accept: Claude-only machine output unchanged; a temp home with only a Codex cache gives no Claude-only fix lines; `token-audit` scan time within noise of `git show HEAD:scripts/token-audit`.
- Verify: `python3 -m unittest tests.test_doctor tests.test_scan tests.test_token_audit_fixes tests.test_scripts`; `python3 tests/bench_token_audit.py`.

### 06 README and manifest wording (low)
- Scope: install section per host, the hosts table, the unsupported list, D1 note on the state folder, descriptions in the two manifests.
- Files: `README.md`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `docs/scheduling.md` (one note on other hosts).
- Accept: every claim matches `probe-results.md` or is marked experimental; skills table test still passes.
- Verify: `python3 -m unittest tests.test_repo`; `claude plugin validate .`.

### 07 CI and repo rules (low)
- Scope: `host probe` stage in `tools/ci-local`; install the Codex CLI in `ci.yml` `checks`; extend the version rule and the commands list in `AGENTS.md` and `CONTRIBUTING.md`.
- Files: `tools/ci-local`, `.github/workflows/ci.yml`, `AGENTS.md`, `CONTRIBUTING.md`.
- Accept: `tools/ci-local --skip-tests` passes with and without `codex` on `PATH`; the stage prints SKIP when absent.
- Verify: `tools/ci-local --skip-tests`; `PATH` without codex, same command.

### 08 Release 0.12.0 and gate (low)
- Scope: version bump, changelog from `changelog-bullets.md`, full gate.
- Files: `.claude-plugin/plugin.json`, `CHANGELOG.md`.
- Accept: all tests pass on Python 3.9 and 3.13; `hooks/hooks.json` identical to 0.11.0; host probe passes; the owner's checklist from 01 is filled in or its open rows are listed as experimental in the README.
- Verify: `tools/ci-local`; `tools/ci-local --python 3.9`; `git diff d1accc4 -- hooks/hooks.json`.

Order: 01, then 02, then 03; 04 and 05 can run in parallel with 03 (different files); 06 and 07 after 02 to 05; 08 last.

### Follow-ups (not in this plan)

- **09 Guardrail hooks on Codex and Copilot (high):** wiring templates for `~/.codex/hooks.json` and `~/.copilot/hooks/`, argument mapping for Copilot `Read`, `kaizen-link --host`, guardrails skill sections. Gate: live results from 01.
- **10 Copilot usage in `token-audit` (high):** read `session-state/*/events.jsonl`. Schema is undocumented; needs a format canary, synthetic fixtures and a price source for AI credits copied from the vendor page.
- **11 Scheduled review on other hosts, Codex auditor agent (normal):** a runner setting for `codex exec` or `copilot -p` in `kaizen-scheduled`; a generated `kaizen-auditor.toml` for `~/.codex/agents/`.

## Rejected alternatives

- **Generated per-host copies of skills and hooks:** two or three copies of 22 skills to keep in step, for differences that two lines and one sidecar file cover.
- **Root Agent Plugins manifest with `com.github.copilot/` and `com.openai` extension folders:** cleaner on paper, but it changes how Copilot and Codex load a tree that already loads, and Claude Code does not read it.
- **Per-host hook scripts:** the three wired hooks differ by output shape and one tool name. One helper block is smaller than three script sets.
- **Loose skills in `~/.agents/skills` or `.github/skills` instead of a plugin:** loses the `agent-kaizen:` prefix, so `review`, `models`, `start` and `undo` would collide with host commands and other skills.
- **Targeting the VS Code Local harness:** removed in February 2027.

## Sources

All read on 2026-11-17.

- Codex plugins, build and packaging: https://developers.openai.com/codex/plugins/build (redirects to https://developers.openai.com/plugins/build/plugins)
- Codex plugins, use: https://developers.openai.com/codex/plugins (redirects to https://learn.chatgpt.com/docs/plugins)
- Codex hooks: https://developers.openai.com/codex/hooks (redirects to https://learn.chatgpt.com/docs/hooks)
- Codex skills: https://developers.openai.com/codex/skills (redirects to https://learn.chatgpt.com/docs/build-skills)
- Codex subagents: https://developers.openai.com/codex/subagents (redirects to https://learn.chatgpt.com/docs/agent-configuration/subagents)
- Codex CLI 0.167.0, local binary: `codex plugin --help`, `codex debug prompt-input`, `codex app-server generate-json-schema`, app-server `hooks/list`, `codex migrate-rollouts --help`
- Agent Plugins: https://agent-plugins.org/ , https://agent-plugins.org/compatible-clients , https://agent-plugins.org/plugin-authors/manifest , https://agent-plugins.org/plugin-authors/client-extensions , https://agent-plugins.org/plugin-authors/skills
- Copilot CLI plugin reference: https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference
- Copilot hooks reference: https://docs.github.com/en/copilot/reference/hooks-configuration (redirects to https://docs.github.com/en/copilot/reference/hooks-reference)
- Copilot CLI config directory: https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-config-dir-reference
- Copilot custom agents configuration: https://docs.github.com/en/copilot/reference/custom-agents-configuration
- Copilot cloud agent: https://docs.github.com/en/copilot/concepts/agents/cloud-agent/about-cloud-agent
- Copilot CLI changelog (latest entry 1.0.113, 2026-11-17): https://raw.githubusercontent.com/github/copilot-cli/main/changelog.md
- VS Code agent plugins: https://code.visualstudio.com/docs/copilot/customization/agent-plugins (redirects to https://code.visualstudio.com/docs/agent-customization/agent-plugins)
- VS Code agent skills: https://code.visualstudio.com/docs/agent-customization/agent-skills
- VS Code hooks: https://code.visualstudio.com/docs/copilot/customization/hooks (redirects to https://code.visualstudio.com/docs/agent-customization/hooks)
