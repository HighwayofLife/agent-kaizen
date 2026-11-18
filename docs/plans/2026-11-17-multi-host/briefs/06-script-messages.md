# Brief P06: host-aware script messages (`kaizen-doctor`, `kaizen-scan`, `token-audit`)

Suggested agent: Terra, medium effort. Risk: normal. Size: M. Group A (runs in parallel with P01, P02, P03, P05; you own `scripts/kaizen-doctor`, `scripts/kaizen-scan`, `scripts/token-audit`, `scripts/README.md`, `tests/test_doctor.py`, `tests/test_scan.py`, `tests/test_token_audit_fixes.py` in this group).

## Goal and why

Agent Kaizen is a Claude Code plugin whose scripts also run when the plugin is installed in Codex CLI or the Copilot runtime. Today `kaizen-doctor` assumes Claude Code (it reads the Claude plugin registry and suggests `claude plugin ...` and `kaizen-link --apply` fixes), and nothing tells a user that Copilot sessions exist but are not measured. Make the messages host-aware. Claude-only machines must see exactly the output they see today.

## Context and facts you can rely on

- Marketplace `agent-kaizen-tools`, plugin `agent-kaizen`, version in `.claude-plugin/plugin.json` (0.11.0 now).
- Codex installs to `${CODEX_HOME:-~/.codex}/plugins/cache/agent-kaizen-tools/agent-kaizen/<version>/` (probed: version directory named after the plugin version). Install/fix command: `codex plugin add agent-kaizen@agent-kaizen-tools`. Codex plugin hooks do nothing until the user trusts them in `/hooks` (vendor docs).
- Copilot installs to `${COPILOT_HOME:-~/.copilot}/installed-plugins/agent-kaizen-tools/agent-kaizen` (documented, not probed). Install/fix command: `copilot plugin install agent-kaizen@agent-kaizen-tools`. Copilot session logs are under `${COPILOT_HOME:-~/.copilot}/session-state/<id>/events.jsonl`; this version does not read them.
- `scripts/kaizen-doctor` (194 lines): `HOME` there is the CLAUDE config dir (`:23`); `emit(level, message, fix)` at `:26`; the first `try` block at about `:58-73` runs `kaizen-link --check`, then reads the Claude registry `plugins/installed_plugins.json` (`:59`) and prints `managed links`, `installed cache matches` or WARN lines with fixes `kaizen-link --apply`, `claude plugin update agent-kaizen`, `claude plugin list`; the hook-registration check `:75-94` prints FAIL with fix `claude plugin install agent-kaizen`; the pricing WARN at `:145` has fix `kaizen-link --apply --replace-prefixed after updating pricing.json`. `tests/test_doctor.py` `setUp` (`:15-57`) builds a temp home with a Claude registry, a copied plugin tree, a minimal `PATH` and asserts every WARN/FAIL line contains `; fix: `.
- `scripts/kaizen-scan:78-79` builds the `--demo` environment (`HOME`, `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, `XDG_CONFIG_HOME` all inside the demo temp dir; there is no `COPILOT_HOME` there yet). `scripts/kaizen-scan:89` prints `Start: review a warning with its named skill; for missing data, use Claude Code or Codex and scan again.` and relays `token-audit` stderr as `Audit note: ...` (home replaced by `~`). `tests/test_scan.py` sets `HOME` and the config dirs to a temp dir; `--demo` runs in a temp HOME and must stay unchanged.
- `scripts/token-audit` main starts at `:1501`; the "no Claude Code projects" stderr message is near `:1553`. The `# --- paths helper ---` block at `:17-29` is copied verbatim into `kaizen-link`, `kaizen-scheduled`, `install-schedule` and checked by `tests/test_runner.py:366`: DO NOT edit that block anywhere. Compute the Copilot path inline in `main`, outside the block.
- Performance: `token-audit` must stay zero-token and fast; AGENTS.md rule: time it against `git show HEAD:scripts/token-audit` when changing the scan. Bench: `python3 tests/bench_token_audit.py --baseline HEAD --max-ratio 1.10` (uses synthetic data, no network). It times `collect()` only, so it cannot see the new `os.path.isdir` check in `main()`: keep it for the scan, and ALSO time the end-to-end `--no-write` run (`scripts/token-audit --no-write`, which skips the report) before and after: save the baseline script with `git show HEAD:scripts/token-audit > "$TMPDIR/token-audit-base"`, then for each of the two scripts run `time (for i in 1 2 3 4 5 6 7 8 9 10; do CLAUDE_CONFIG_DIR="$TMPDIR/empty-claude" HOME="$TMPDIR/empty-home" CODEX_HOME="$TMPDIR/empty-codex" python3 SCRIPT --no-write >/dev/null 2>&1; done)` with empty directories (create them with `mkdir -p`). The new check is one `isdir` call, so expect no visible difference; report both timings. Take the baselines BEFORE editing and paste all numbers in your report.

## Scope

Edit: `scripts/kaizen-doctor`, `scripts/kaizen-scan`, `scripts/token-audit`, `scripts/README.md`, `tests/test_doctor.py`, `tests/test_scan.py`, `tests/test_token_audit_fixes.py`.
Create: `docs/plans/2026-11-17-multi-host/changelog/P06.md` (`mkdir -p`) with exactly:
`- kaizen-doctor reports whether the plugin is installed for Claude Code, Codex and Copilot and gives each host its own fix; on a machine without Claude Code it no longer suggests claude commands. kaizen-scan and token-audit say when Copilot sessions exist but are not measured yet.`

Do NOT touch: `.claude-plugin/plugin.json` (version), `CHANGELOG.md` (only P09 edits them), hooks, skills, docs, other scripts, the paths-helper block, `tools/`.

## Required behaviour

### `kaizen-doctor`
1. Detect (read-only, no commands run): `claude_present` = `HOME/plugins/installed_plugins.json` exists (the Claude registry, as today). Codex: the directory `${CODEX_HOME:-~/.codex}/plugins/cache/agent-kaizen-tools/agent-kaizen/` exists and has a version subdirectory. Copilot: `${COPILOT_HOME:-~/.copilot}/installed-plugins/agent-kaizen-tools/agent-kaizen` exists. Read the marketplace and plugin names from the plugin root's `.claude-plugin/marketplace.json` and `plugin.json` where practical (fallback to the constants above).
2. New lines, printed only for Codex and Copilot (never for Claude): Codex `PASS Codex: plugin installed (version X)` when X equals the plugin root's `plugin.json` version, else `WARN Codex: installed version(s) A differ from plugin root B; fix: codex plugin add agent-kaizen@agent-kaizen-tools`; Copilot `PASS Copilot: plugin installed` (compare the version in the installed copy's `.claude-plugin/plugin.json` when readable, same WARN form with `fix: copilot plugin install agent-kaizen@agent-kaizen-tools`). When Codex has the plugin, also print `INFO Codex: run /hooks once to trust the plugin hooks` (plain `emit('INFO', message)`, no fix). A missing Codex or Copilot install prints nothing (they are optional).
3. Claude-only lines are suppressed when `claude_present` is false AND at least one of Codex or Copilot has the plugin: omit the `managed links` line and the installed-cache lines (both come from the first `try` block), and replace the Claude-only fixes elsewhere (hook-registration FAIL: `claude plugin install agent-kaizen`; pricing WARN: `kaizen-link --apply ...`) with the host-neutral fix `update the plugin with your host's plugin command (see docs/hosts.md)`. In every other situation (Claude registry present, or nothing detected anywhere) the output is exactly today's.
4. Every WARN/FAIL line still ends with a `; fix: ...` part.

### `kaizen-scan` and `token-audit`
5. `token-audit`: directly after the existing "no Claude Code projects" `if` block (at `:1552-1555`; place the new code OUTSIDE that block so it runs whether or not Claude projects exist), when the directory `${COPILOT_HOME:-~/.copilot}/session-state` exists (one `os.path.isdir`, nothing else; do not list or read it), print ONE line to stderr: `token-audit: Copilot sessions found but not measured in this version`. Printed in every mode (stdout stays pure data, including `--json`).
6. `kaizen-scan`: it already relays `token-audit` stderr as `Audit note: ...`, so the line surfaces there. When that note contains `Copilot sessions found`, end the Start line as `...for missing data, use Claude Code or Codex (Copilot sessions are not measured yet) and scan again.` Otherwise the Start line is unchanged. `--demo` output is unchanged: add `COPILOT_HOME=str(Path(tmp) / 'copilot')` to the `env.update(...)` of the demo branch (`:78-79`), so an inherited real `COPILOT_HOME` cannot add a Copilot line to the demo.
7. `scripts/README.md`: under the `token-audit` section add one sentence about the Copilot line; add one short paragraph (or bullets) to the section for the doctor if one exists, else a short new `## kaizen-doctor` section, describing the per-host lines and the Codex trust INFO. Plain words.

## Tests

- `tests/test_doctor.py`: (a) temp home with ONLY a Codex cache (no Claude registry; set `CODEX_HOME` in the env to a temp dir containing `plugins/cache/agent-kaizen-tools/agent-kaizen/<version>/`): output has `PASS Codex: plugin installed`, the INFO trust line, and NO line containing `claude plugin` or `kaizen-link --apply`; every WARN/FAIL has a fix. (b) Codex cache with a different version gives the WARN with the codex fix. (c) Copilot-only install via `COPILOT_HOME`. (d) Claude-only (the existing `setUp`): the output of the existing tests is unchanged and contains no `Codex` or `Copilot` text; set `CODEX_HOME` and `COPILOT_HOME` to empty temp dirs in the shared env so a developer's real installs cannot leak in. All existing tests must pass unmodified apart from that env addition.
- `tests/test_scan.py`: with a `session-state` directory under the temp `COPILOT_HOME` (or `HOME/.copilot`), stderr contains `Audit note:` and `Copilot sessions found but not measured`, and the Start line has the Copilot sentence; without it, output equals today's; `--demo` has no Copilot text, also when the parent environment sets `COPILOT_HOME` to a directory that has a populated `session-state/` (the demo must ignore it).
- `tests/test_token_audit_fixes.py` (class `FixCase`, `self.env` already has an isolated `HOME`): the stderr line appears when `COPILOT_HOME/session-state` exists, is absent otherwise, and `--json` stdout still parses. Set `COPILOT_HOME` explicitly in the test.

## Acceptance criteria

1. Claude-only machine output of `kaizen-doctor`, `kaizen-scan` and `token-audit` is unchanged (existing tests pass; new test (d)).
2. A Codex-only home produces no Claude-only fix lines (test (a)).
3. Bench median ratio <= 1.10 vs `HEAD` (report baseline and after numbers), and the end-to-end `--no-write` timing before and after (report both; they should be within noise).
4. All scripts still answer `--help` (`scripts/kaizen-doctor --help`, `scripts/kaizen-scan --help`, `scripts/token-audit --help` exit 0).
5. The paths-helper block is untouched (`PYTHONPATH=tests python3 -m unittest tests.test_runner` passes).

## Sandbox and environment (read before running any command)

- Writable temp dir: `mkdir -p out/tmp && export TMPDIR="$PWD/out/tmp"` (`out/` is git-ignored; keep the path short). If `out/` is not writable, use any writable directory outside the repo. Use it for every scratch file and temp directory you create.
- Record every command the environment blocks (read-only file system, no network, no sign-in, missing CLI) as `not run: <reason>`, separately from product failures (a failed assertion, or a non-zero exit from product code). Stop and report only for product failures. Never report a blocked run as a pass.
- Check changed files with `git status --short --untracked-files=all` together with `git diff --stat`: the diff alone omits new files.
- Run narrow unit tests as `PYTHONPATH=tests python3 -m unittest tests.test_x ...` (some test modules import their siblings as top-level modules and fail without it).

## Verification (narrowest first)

```
python3 tests/bench_token_audit.py --baseline HEAD --max-ratio 1.10     # run once BEFORE editing and note the numbers
PYTHONPATH=tests python3 -m unittest tests.test_doctor tests.test_scan tests.test_token_audit_fixes tests.test_scripts tests.test_runner
scripts/kaizen-doctor --help && scripts/kaizen-scan --help && scripts/token-audit --help
python3 tests/bench_token_audit.py --baseline HEAD --max-ratio 1.10     # again after editing
# end-to-end: the 10-run `--no-write` loop from the Performance note, baseline script vs scripts/token-audit, before and after
python3 -m unittest discover -s tests
shellcheck -S warning hooks/*.sh
claude plugin validate .
git status --short --untracked-files=all
git diff --stat
```

## Reporting

Report the baseline and after bench numbers, the verify output (trimmed), files changed, and any rule you had to interpret (the suppression rule in item 3 especially). Do not commit or push. If an assumption here is wrong (for example the Claude-only output cannot stay byte-identical), stop and report.
