# Brief P01: `tools/host-probe`, isolated install and discovery checks

Suggested agent: Terra, medium effort. Risk: low. Size: M. Group A (runs in parallel with P02, P03, P05, P06; shares no files with them).

## Goal and why

Agent Kaizen is a Claude Code plugin (Markdown skills, hooks, stdlib scripts). Codex CLI and the GitHub Copilot runtime can load the same plugin tree. We need a repeatable, zero-sign-in check that installs the plugin into a throwaway home on each host CLI that is present and asserts it installs, shows the right version, lists no always-on `agent-kaizen:` skills on Codex, and that Codex discovers the plugin hooks. Later packets (CI stage in P08, release gate in P09) call this tool. Today (version 0.11.0) the "zero skills listed" check is EXPECTED to FAIL: Codex lists all 22 skills. Packet P02 fixes that.

## Context and facts you can rely on

Measured 2026-11-17 with `codex-cli 0.167.0`, isolated `HOME` and `CODEX_HOME`, no sign-in:

- `codex plugin marketplace add <path-or-OWNER/REPO>` prints `Added marketplace ...`; it reads `.claude-plugin/marketplace.json` (marketplace name `agent-kaizen-tools`). Exit 0.
- `codex plugin add agent-kaizen@agent-kaizen-tools` prints `Installed plugin root: <path>`. The tree is copied to `$CODEX_HOME/plugins/cache/agent-kaizen-tools/agent-kaizen/<version>`, where `<version>` is `version` in `.claude-plugin/plugin.json` (0.11.0 now).
- A local-path install copies the WHOLE working tree (including git-ignored `out/`, `.git`, `.claude/`). A `CODEX_HOME` placed inside the tree fails with `File name too long`. So: install from a clean export in a system temp dir, never from the checkout itself and never with a home under the repo.
- `codex debug prompt-input` (run with `cwd` set to the temp home) prints a JSON array. Skills appear in message text as lines `- agent-kaizen:<name>: <description> (file: ...)`. On the 0.11.0 tree 22 distinct `agent-kaizen:<name>` skills are listed. Other skills (for example `imagegen`) also appear and must be ignored. Count distinct matches of the regex `agent-kaizen:([a-z0-9-]+): ` over the whole output text. Zero matches only means "hidden" when the command itself worked: it must exit 0, print valid JSON (a JSON array) and that text must contain at least one skill-list line of the form `- <name>: <description> (file: ...)` (Codex's own bundled skills such as `imagegen` normally appear; their presence proves the skills section was rendered). Non-zero exit or invalid JSON is a FAIL on `skills hidden` with the reason, never a PASS; valid JSON with no skill-list line at all is a SKIP (`prompt output has no skills section`).
- Hook discovery works over the app server JSON-RPC on stdio: start `codex app-server` (cwd = temp home, same env), send newline-delimited JSON: `{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"clientInfo":{"name":"host-probe","version":"0"}}}`, read the response with `id` 1, send `{"jsonrpc":"2.0","method":"initialized"}`, send `{"jsonrpc":"2.0","id":2,"method":"hooks/list","params":{"cwds":["<temp home>"]}}`, read the response with `id` 2 (skip any other messages), then kill the process. `result.data[0].hooks` is a list; each entry has `eventName`, `pluginId` (`agent-kaizen@agent-kaizen-tools`), `source` (`plugin`), `trustStatus` (`untrusted` until a human trusts it in `/hooks`; that is expected, not a failure). Observed: 4 hooks from `hooks/hooks.json` (`postToolUse`, `sessionStart` x2, `userPromptSubmit`); `PostToolUseFailure` is not a Codex event and is silently dropped. Use PASS only when all four expected registrations are present with `pluginId == agent-kaizen@agent-kaizen-tools` and `source == plugin`: `postToolUse` x1, `sessionStart` x2, `userPromptSubmit` x1 (compare the multiset of `eventName` values; one surviving hook is not a pass). Report the count and event names in the detail. FAIL when any is missing (detail lists what is missing) or when there are 0; SKIP (with the reason) if the JSON-RPC exchange fails or times out. Do not guess.
- The Copilot CLI is not installed on the machine that wrote this brief, so Copilot commands are documented, not probed: `copilot plugin marketplace add <path>`, `copilot plugin install agent-kaizen@agent-kaizen-tools`; the install lands in `$COPILOT_HOME/installed-plugins/agent-kaizen-tools/agent-kaizen` (default `~/.copilot`). Source: GitHub Copilot CLI plugin reference.

## Scope

Create:
- `tools/host-probe`: executable (`chmod +x`), `#!/usr/bin/env python3`, stdlib only, Python 3.9 syntax (no `match`, no `X | Y` types, no 3.10+ stdlib). Style like `tools/ci-local`.
- `tests/test_host_probe.py`.
- `docs/plans/2026-11-17-multi-host/probe-results.md`.

Do NOT touch: anything else. In particular not `.claude-plugin/plugin.json` (version), `CHANGELOG.md`, `hooks/`, `skills/`, `scripts/`, `tools/ci-local`, `tests/test_repo.py`, `plan.md`. No changelog fragment is needed (`tools/` is not shipped at runtime).

## Required behaviour

CLI: `tools/host-probe [--host codex|copilot|all] [--source PATH] [--worktree] [--expect-hidden-skills | --no-expect-hidden-skills] [--timeout SECONDS] [--json]`. Defaults: `--host all`, `--source` the repository root (parent of `tools/`), `--expect-hidden-skills` on (use `argparse.BooleanOptionalAction`), `--timeout 120` per command. `--help` exits 0.

1. Make the sandbox with `tempfile.mkdtemp()` (it honours a `TMPDIR` override; the default is the system temp dir; never create it inside the `--source` tree) and remove it at exit. Inside it: `export/`, `home/`, `codex/`, `copilot/`. Child processes get `HOME=<tmp>/home`, `CODEX_HOME=<tmp>/codex`, `COPILOT_HOME=<tmp>/copilot`, `XDG_CONFIG_HOME=<tmp>/xdg/config`, `XDG_CACHE_HOME=<tmp>/xdg/cache`, `XDG_DATA_HOME=<tmp>/xdg/data`, `XDG_STATE_HOME=<tmp>/xdg/state`, `GIT_CONFIG_GLOBAL=/dev/null` and `cwd=<tmp>/home`. Never read or write the real home. Pass the rest of the environment through (so `PATH` and `TMPDIR` work), but first drop every inherited variable whose name starts with `KAIZEN_`, `CLAUDE_`, `CODEX_`, `COPILOT_` or `XDG_`, so an inherited config path cannot reach the real home.
2. Export the tree to `export/`: default `git -C SOURCE archive HEAD | tar -x -C export` (committed state only). With `--worktree`, copy the files listed by `git -C SOURCE ls-files -z --cached --others --exclude-standard` that exist on disk (includes uncommitted and new files, skips deleted ones; use `shutil.copy2`, keep modes). Run `tar`/`git` with `subprocess` without `shell=True`.
3. Output: one line per check, `PASS|FAIL|SKIP <host> <check>: <detail>`. Replace the temp dir path in details with `<tmp>` so output is stable and contains no machine paths. `--json` prints a JSON list of `{status, host, check, detail}` instead. Exit 1 if any FAIL, else 0. Every command runs with a timeout; a timeout is a FAIL with the command named.
4. Codex checks (host `codex`), in order; if `codex` is not on `PATH`, print `SKIP codex cli: codex not found on PATH` and nothing else for that host:
   - `cli version`: PASS with `codex --version` output.
   - `marketplace add`: `codex plugin marketplace add <export>`; PASS on exit 0.
   - `plugin add`: `codex plugin add agent-kaizen@agent-kaizen-tools`; PASS on exit 0. If it fails, FAIL and skip the dependent checks below (print SKIP for them).
   - `installed version`: the directory `$CODEX_HOME/plugins/cache/agent-kaizen-tools/agent-kaizen/<version>` exists with `<version>` equal to `version` in `<export>/.claude-plugin/plugin.json`; PASS detail `<version>`, else FAIL.
   - `skills hidden`: run `codex debug prompt-input`; first check the command succeeded and its output is valid (see Context), then count distinct `agent-kaizen:<name>` as above. With `--expect-hidden-skills`: PASS if 0, FAIL with detail `<N> listed` otherwise. With `--no-expect-hidden-skills`: PASS with detail `<N> listed` once the output is valid. An invalid or failed prompt command is FAIL (or SKIP for "no skills section") in both modes.
   - `hooks discovered`: as described under Context (all four expected registrations, not just one).
5. Copilot checks (host `copilot`): if `copilot` is not on `PATH`: `SKIP copilot cli: copilot not found on PATH`. Otherwise `copilot plugin marketplace add <export>`, `copilot plugin install agent-kaizen@agent-kaizen-tools`, then PASS if `$COPILOT_HOME/installed-plugins/agent-kaizen-tools/agent-kaizen` exists. If a command's output mentions a sign-in or login requirement (case-insensitive `sign in`, `login`, `log in`, `authenticate`) or it exits non-zero with such text, print `SKIP copilot <check>: needs sign-in` and continue. Other non-zero exits are FAIL.
6. `--host all` runs both hosts; a missing CLI only yields SKIP lines (exit 0).

## Tests (`tests/test_host_probe.py`, unittest, no network, no real codex or copilot)

Run the tool as a subprocess (`sys.executable`, path `tools/host-probe`) with `PATH` set to a temp bin dir that holds stub `codex` (and where needed `copilot`) scripts plus small wrapper scripts for the system `git`, `tar` and `python3` (`#!/bin/sh` then `exec <absolute path> "$@"`; symlinks can break tool shims). Never append the original `PATH`: a tools-only `PATH` keeps a real `codex` or `copilot` out of reach. Set `TMPDIR` for the child to a fresh temp dir. In the test process set misleading `XDG_CONFIG_HOME`, `CODEX_HOME`, `COPILOT_HOME`, `KAIZEN_X` values in the parent environment to prove they are replaced or dropped. Build a tiny fixture source repo in a temp dir: `git init`, `.claude-plugin/plugin.json` with `{"name":"agent-kaizen","version":"9.9.9"}`, `.claude-plugin/marketplace.json`, one commit (pass `-c user.name=t -c user.email=t@example.invalid` to git commit; set `GIT_CONFIG_GLOBAL=/dev/null`). Pass it with `--source`.

The stub `codex` is a Python script that appends a JSON line (argv, `HOME`, `CODEX_HOME`, cwd) to a record file named by an environment variable, and:
- `--version` prints `codex-cli 0.0.0-stub`;
- `plugin marketplace add X` exits 0; `plugin add ...` creates `$CODEX_HOME/plugins/cache/agent-kaizen-tools/agent-kaizen/9.9.9/` and exits 0;
- `debug prompt-input` prints a JSON array whose text lists N lines `- agent-kaizen:skill-<i>: text (file: x)` (N from an env var: 22 or 0) plus one unrelated `- imagegen: text` line;
- `debug prompt-input` also has env switches: exit 1; print text that is not JSON; print valid JSON with no skill-list lines;
- `app-server` is a small JSON-RPC responder on stdin/stdout answering `initialize` and `hooks/list` (return the 4 hooks: `postToolUse`, `sessionStart` x2, `userPromptSubmit`, each with `pluginId` `agent-kaizen@agent-kaizen-tools` and `source` `plugin`), or, with env switches, returns only 1 of the 4 hooks, or exits 1 immediately.

Cases: (a) N=22 with default flags gives a `FAIL codex skills hidden: 22 listed` line and exit 1, other checks PASS; (b) N=0 gives exit 0 and `PASS codex skills hidden`; (c) N=22 with `--no-expect-hidden-skills` exits 0; (d) tools-only bin (no codex, no copilot; assert `shutil.which('codex', path=bin)` is `None` in the test) with `--host all` prints two SKIP lines and exits 0; (e) every recorded `HOME`, `CODEX_HOME`, `COPILOT_HOME`, `XDG_*` value and cwd lies under the `TMPDIR` given to the child, none equals the real `HOME`, none lies under the `--source` fixture directory, no `KAIZEN_*` or `CLAUDE_*` variable and none of the misleading parent values reach the stub, and the sandbox directory no longer exists after the run (the record includes it); (f) app-server failure gives `SKIP codex hooks discovered` with a reason and exit 0; app-server returning 1 of 4 hooks gives `FAIL codex hooks discovered` and exit 1; (f2) prompt-input exiting 1 or printing non-JSON gives `FAIL codex skills hidden` (and no "0 listed" PASS), valid JSON with no skill lines gives SKIP; (g) a stub `copilot` that prints `Please sign in` and exits 1 gives SKIP lines and exit 0; a stub `copilot` that creates the install dir gives PASS; (h) `--json` output parses and has the same statuses; (i) `--worktree` exports an untracked file that `--source` has on disk (assert via the stub recording the export dir listing, or add an assertion in the stub's `marketplace add` that writes the list of exported files to the record). Keep it compact; one test class is enough.

## `probe-results.md`

Create `docs/plans/2026-11-17-multi-host/probe-results.md` (make the directory if the worktree lacks it) with:
1. `## Automated run` heading: date, `codex --version` output, the exact command line used, and the trimmed output lines of `tools/host-probe --host codex` on this tree. On the 0.11.0 tree expect install and version PASS, `skills hidden` FAIL with `22 listed`, hooks PASS (about 4). If `codex` cannot run inside your sandbox (blocked by the environment), write `not run: <reason>` under the heading and say so in your report; the owner (checklist item O5) or orchestrator will paste the run. Never invent output.
2. `## Owner checks` heading with empty results tables (columns: Check, Result, Date and version, Notes) and these rows (O1, O2, O3, O5), for a human with a signed-in host to fill in later:
   - O1 Copilot CLI: `/skills` shows `agent-kaizen:*` and none is invoked unprompted; `hooks/hooks.json` loads without error; `SessionStart` with matcher `startup|resume` fires and the audit notice appears; `"async": true` is ignored, honoured or rejected; a `Bash` call 8 times in one turn gives the nudge (and which `tool_name` is seen); whether `agents/kaizen-auditor.md` loads and what `model: sonnet` does; whether the model is given the skill's folder path; capture the raw hook payload keys and event names (and `tool_name` casing) Copilot sends for each wired hook, and whether the matcher `Bash` in the shared `hooks/hooks.json` delivers the `bash` tool's events (if not, contingent packet C1 applies); after packet P04 lands, invoke a skill from an unrelated project and check that the model resolves the plugin path and runs the bundled script; then the same install in VS Code with the Copilot session target.
   - O2 Codex CLI live session: trust the hooks in `/hooks`; the notice appears on start; what the quiet `{}` output shows; whether tool hooks inside a subagent carry `agent_id`; `$agent-kaizen:scan` runs the script from the cached plugin root; capture the raw hook payload keys and event names; after packet P04 lands, invoke a skill from an unrelated project and check that the plugin path resolves.
   - O3 Codex IDE extension: whether IDE sessions land in `$CODEX_HOME/sessions` (so `token-audit` would measure them).
   - O5 Runs a sandbox cannot do, before release: `tools/host-probe --host all --worktree` and `tools/ci-local --python 3.9` outside the sandbox (network, Python 3.9 download, real CLIs); paste the output.
3. No absolute home-directory paths anywhere (a repo test fails on `/Users/<name>` and `/home/<name>/`); use `<tmp>` and `~`.

## Acceptance criteria

1. `tools/host-probe --help` exits 0 and the file is executable.
2. All check kinds above exist and print lines in the stated format; exit code is 1 on any FAIL, else 0.
3. The tool never writes outside its own temp dir and never uses the real home (test (e)); `git status --short --untracked-files=all` after a run shows only the three new files.
4. `PYTHONPATH=tests python3 -m unittest tests.test_host_probe` passes with no real CLI, no network and no sign-in; the code uses Python 3.9 syntax only (check: `python3 -m py_compile tools/host-probe`, and `rg -n "match |:= | \| None" tools/host-probe` finds no 3.10+ constructs).
5. On the 0.11.0 tree the live Codex run (if runnable) shows install and version PASS and `skills hidden` FAIL (`22 listed`).

## Sandbox and environment (read before running any command)

- Writable temp dir: `mkdir -p out/tmp && export TMPDIR="$PWD/out/tmp"` (`out/` is git-ignored; keep the path short). If `out/` is not writable, use any writable directory outside the repo. Use it for every scratch file and temp directory you create.
- `tools/host-probe` honours `TMPDIR` but always exports the plugin with `git archive` (or the `--worktree` file list) into a fresh directory under it and runs the host CLI from that export, never from the checkout. Do not install a host CLI from the checkout or put a host home under `out/` inside the tree: Codex fails with "File name too long" when it copies a tree that contains `out/`.
- Record every command the environment blocks (read-only file system, no network, no sign-in, missing CLI) as `not run: <reason>`, separately from product failures (a failed assertion, or a non-zero exit from product code). Stop and report only for product failures. Never report a blocked run as a pass. A probe `FAIL` whose detail is an OS or network error (permission denied, read-only file system, DNS or connection error, sign-in) counts as blocked; a `FAIL` about the product (version mismatch, skills still listed, hooks missing) is a product failure.
- Check changed files with `git status --short --untracked-files=all` together with `git diff --stat`: the diff alone omits new files.
- Run narrow unit tests as `PYTHONPATH=tests python3 -m unittest tests.test_x ...` (some test modules import their siblings as top-level modules and fail without it).

## Verification (narrowest first)

```
PYTHONPATH=tests python3 -m unittest tests.test_host_probe
tools/host-probe --help
tools/host-probe --host codex            # exit 1 expected on this tree (skills hidden FAIL: 22 listed); needs codex, no sign-in; if the sandbox blocks it, record `not run: <reason>`
python3 -m unittest discover -s tests
shellcheck -S warning hooks/*.sh
git status --short --untracked-files=all # only the three new files (plus plan-folder files already present)
git diff --stat
```
`claude plugin validate .` is not affected by this packet.

## Reporting

Report: files created, the verify output (trimmed), the live probe lines, or `not run: <reason>` for anything the environment blocked (kept separate from product failures), and any deviation. Do not commit or push. If an assumption here proves wrong (for example the JSON-RPC exchange differs on the installed Codex version), stop and report it instead of guessing.
