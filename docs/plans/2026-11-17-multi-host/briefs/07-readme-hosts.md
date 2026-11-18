# Brief P07: README install per host, hosts table, manifest descriptions

Agent: Luna, effort low. Risk: low. Size: M (text only).
Do not commit or push. Do not edit any file not listed under "Files you may change".

## Goal and why

Agent Kaizen is a Claude Code plugin (version 0.11.0). This release makes the same plugin tree install on Codex CLI and on the GitHub Copilot runtime (Copilot CLI, and VS Code with the Copilot harness). Earlier packets (P01 to P06, P08 is independent) already changed the code and docs. Your job is the user-facing words: one install block per host in `README.md`, a table of what works where, and the plugin description strings. Everything you write must be true as stated. Where a claim is not yet checked, the text below already says "experimental" or "not yet checked". Do not make claims stronger and do not add claims.

## Context (facts you can rely on)

- Codex CLI 0.167.0 installs the plugin from `HighwayofLife/agent-kaizen` and from a local checkout with no sign-in (planner probe, 2026-11-17, `docs/plans/2026-11-17-multi-host/research.md`). Codex does not support the plugin in its IDE extension ("The IDE extension doesn't support plugins", https://learn.chatgpt.com/docs/plugins).
- Copilot CLI install (`copilot plugin marketplace add`, `copilot plugin install`) comes from GitHub's plugin reference (https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference). It has not been run on this plugin yet, so every Copilot line says "experimental". The owner decided (D2, final: yes) to ship Copilot labelled experimental.
- State location (D1, final decision): Agent Kaizen keeps its files in `~/.claude/` or `$CLAUDE_CONFIG_DIR` on every host.
- `tests/test_repo.py::test_readme_lists_every_skill` collects every `` `/agent-kaizen:<name>` `` (backticked, leading slash, lowercase name) in `README.md` and compares with the skill folders. So: only write `` `/agent-kaizen:` `` names that exist as folders in `skills/` (`scan`, `cycle`, `review` and `audit` exist), and never invent one. `$agent-kaizen:scan` (with `$`) is not matched by that test and is fine.
- `tests/test_repo.py::test_no_personal_data` fails on home-directory paths such as `/Users/<name>` or `/home/<name>/`. Use `~` forms only.
- The README already has: `## Quick start` with a versions table, then `### 1. Install ...`, `### 2. Scan recent usage`; and an `### Uninstall` list.

## Files you may change

- `README.md`
- `.claude-plugin/plugin.json` (the `description` field only; do not touch `name`, `version` or anything else)
- `.claude-plugin/marketplace.json` (the two `description` fields only)
- `docs/scheduling.md` (one added paragraph)
- `docs/plans/2026-11-17-multi-host/changelog/P07.md` (new; create the folder if missing)

## Do not touch

Everything else. In particular: no `skills/`, `hooks/`, `scripts/`, `tests/`, `tools/`, `CHANGELOG.md`, `AGENTS.md`, `CONTRIBUTING.md`, and no `version` in `plugin.json` (packet P09 bumps it to 0.12.0 and writes CHANGELOG.md). Do not edit `docs/plans/2026-11-17-multi-host/probe-results.md` or `plan.md`.

## Step 0: preconditions (the file checks are required; the probe run is optional)

Run:

```bash
ls tools/host-probe docs/hosts.md skills/scan/agents/openai.yaml agents/kaizen-auditor.md
rg -c 'Plugin root' skills/scan/SKILL.md
```

All four files must exist and the count must be 1. If not, stop and report: earlier packets have not landed.

Optional: if `codex` is on PATH and your sandbox allows it (see "Sandbox and environment"), run `tools/host-probe --host codex` and read its lines. Every `codex` line must start with `PASS` or `SKIP`. If a line starts with `FAIL` and the detail is a product problem (version mismatch, skills still listed, hooks missing), stop and report the line; do not edit anything. If the run is blocked by the environment (OS or network error, `codex` missing, no writable temp dir), write `not run: <reason>` in your report and continue; this does not stop the packet. Afterwards run `git status --short --untracked-files=all`; if `docs/plans/2026-11-17-multi-host/probe-results.md` shows as modified, restore it with `git checkout -- docs/plans/2026-11-17-multi-host/probe-results.md`.

## Edits (exact wording)

Text marked **[D1]** or **[D2]** records an owner decision. Both are resolved: yes. Use the text as written.

### 1. README versions table

Find this exact line in `README.md`:

```
| Codex CLI (optional) | — | 0.163.0 |
```

Keep it, and add this line directly under it:

```
| Codex CLI plugin install (optional) | — | 0.167.0 |
```

Add no Copilot row.

### 2. README new subsection

Insert the block below as a new subsection directly before the line `### 2. Scan recent usage` (leave one blank line before and after the block). Copy it exactly. The fenced `bash` blocks are part of the text to insert.

````
### Other hosts: Codex CLI, Copilot CLI and VS Code

Claude Code is the main target. Codex CLI works today. The Copilot runtime is experimental. This README writes skills as `/agent-kaizen:<name>`; on Codex, type `$` instead of `/`, for example `$agent-kaizen:scan`.

**Codex CLI** (tested on 0.167.0; installing needs no sign-in):

```bash
codex plugin marketplace add HighwayofLife/agent-kaizen
codex plugin add agent-kaizen@agent-kaizen-tools
```

Start a new Codex session, run `/hooks` once and trust the Agent Kaizen hooks. Hooks do nothing until you trust them, and you must trust them again after an update that changes a hook script. Then run `$agent-kaizen:scan`.

**GitHub Copilot CLI** (experimental, not yet checked in a live session):

```bash
copilot plugin marketplace add HighwayofLife/agent-kaizen
copilot plugin install agent-kaizen@agent-kaizen-tools
```

Then try `/agent-kaizen:scan` (experimental: not yet checked).

**VS Code with the GitHub Copilot harness** (experimental, not yet checked): set `chat.plugins.enabled`, choose Copilot as the session target, run **Chat: Install Plugin from Source** and enter `https://github.com/HighwayofLife/agent-kaizen`. A plugin you installed with Copilot CLI should also be picked up (not verified).

| Host | Install | Skills | Session notice | Agent | Usage measured |
|---|---|---|---|---|---|
| Claude Code | Yes | Yes | Yes | Yes | Yes |
| Codex CLI | Yes | Yes | Yes, after you trust the hooks in `/hooks` (not yet checked in a live session) | No: the `cycle` skill does the same job | Yes |
| Copilot CLI | Experimental | Experimental | Experimental | Not verified | Not yet |
| VS Code, Copilot harness | Experimental | Experimental | Experimental | Not verified | Not yet |

The Codex IDE extension and the GitHub Copilot cloud agent are not supported: they do not run installed plugins. Copilot support is experimental, and Copilot session usage is not measured yet; `scan` and `audit` say so.

**[D1]** Agent Kaizen keeps its files in `~/.claude/` (or `$CLAUDE_CONFIG_DIR`) on every host, so one ledger and one set of audits covers all hosts. If you only use Codex or Copilot, you will get a `~/.claude/` folder that holds only Agent Kaizen files.

On Codex and Copilot, changes to that host's own configuration files are proposals only, in every autonomy mode. Details: [docs/hosts.md](docs/hosts.md).
````

### 3. README uninstall

In the `### Uninstall` list, find this exact line:

```
3. Remove the plugin: `claude plugin uninstall agent-kaizen@agent-kaizen-tools`.
```

Add directly under it (no blank line between):

```
4. On Codex CLI: `codex plugin remove agent-kaizen@agent-kaizen-tools`. On Copilot (experimental), use the plugin uninstall command listed by `copilot plugin --help`.
```

### 4. Manifest descriptions

Set `description` in `.claude-plugin/plugin.json` to exactly:

```
A self-improving workflow for Claude Code, with Codex CLI and GitHub Copilot support (experimental on Copilot): measure token use, trim context, route work to the cheapest capable model, and keep checking whether each change paid off.
```

In `.claude-plugin/marketplace.json`, set the top-level `description` to exactly:

```
Agent Kaizen: a self-improving workflow plugin for Claude Code, with Codex CLI and GitHub Copilot support (experimental on Copilot).
```

and the `description` inside `plugins[0]` to exactly:

```
Skills, scripts and templates for a self-improving workflow on Claude Code and Codex CLI, and experimentally on the Copilot runtime; the auditor agent runs on Claude Code only.
```

Use `jq` only to check the result, not to rewrite the files (it reorders nothing but changes spacing; edit the text in place instead).

### 5. docs/scheduling.md

Directly after the first table in `docs/scheduling.md` (the table whose last row starts `| Session notice |`), add one blank line and this paragraph, then one more blank line:

```
Scheduled reviews run only through Claude Code for now. On Codex CLI and Copilot, run the `cycle` skill by hand when the session notice appears.
```

### 6. Changelog fragment

Create `docs/plans/2026-11-17-multi-host/changelog/P07.md` with exactly this content (packet P09 merges it into CHANGELOG.md):

```
`README`, `plugin.json`:

- The README quick start has install steps for Codex CLI (tested on 0.167.0) and, marked experimental, for Copilot CLI and VS Code with the Copilot harness, plus a table of what works on each host.
- The plugin and marketplace descriptions now mention Codex CLI and GitHub Copilot support.
```

## Acceptance criteria

1. `README.md` contains exactly one line `### Other hosts: Codex CLI, Copilot CLI and VS Code`, placed between the `### 1. Install` section and `### 2. Scan recent usage`.
2. The versions table has both Codex rows and no Copilot row.
3. `rg -c 'copilot plugin install agent-kaizen@agent-kaizen-tools' README.md` prints 1, and `rg -c 'codex plugin add agent-kaizen@agent-kaizen-tools' README.md` prints 1.
4. Every sentence or table row in the new text (README block, table, uninstall line, the three descriptions) that says Copilot works, installs, runs or loads contains "experimental", "not yet" or "not verified" (`rg -n -i 'copilot' README.md` and read each hit in the new block). No text says the auditor agent runs outside Claude Code, except to say it does not.
5. `jq -e '.name=="agent-kaizen" and .version=="0.11.0"' .claude-plugin/plugin.json` succeeds (name and version unchanged), and the three descriptions equal the strings above.
6. `git diff --stat` lists only `README.md`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `docs/scheduling.md`, and `git status --short --untracked-files=all` additionally shows only the new `docs/plans/2026-11-17-multi-host/changelog/P07.md`.
7. All verify commands below pass.

## Sandbox and environment (read before running any command)

- Writable temp dir: `mkdir -p out/tmp && export TMPDIR="$PWD/out/tmp"` (`out/` is git-ignored; keep the path short). If `out/` is not writable, use any writable directory outside the repo. Use it for every scratch file and temp directory you create.
- `tools/host-probe` honours `TMPDIR` but always exports the plugin with `git archive` (or the `--worktree` file list) into a fresh directory under it and runs the host CLI from that export, never from the checkout. Do not install a host CLI from the checkout or put a host home under `out/` inside the tree: Codex fails with "File name too long" when it copies a tree that contains `out/`.
- Record every command the environment blocks (read-only file system, no network, no sign-in, missing CLI) as `not run: <reason>`, separately from product failures (a failed assertion, or a non-zero exit from product code). Stop and report only for product failures. Never report a blocked run as a pass. A probe `FAIL` whose detail is an OS or network error (permission denied, read-only file system, DNS or connection error, sign-in) counts as blocked; a `FAIL` about the product (version mismatch, skills still listed, hooks missing) is a product failure.
- Check changed files with `git status --short --untracked-files=all` together with `git diff --stat`: the diff alone omits new files.
- Run narrow unit tests as `PYTHONPATH=tests python3 -m unittest tests.test_x ...` (some test modules import their siblings as top-level modules and fail without it).

## Verification

Narrowest first:

```bash
PYTHONPATH=tests python3 -m unittest tests.test_repo
jq -r .description .claude-plugin/plugin.json
jq -r '.description, .plugins[0].description' .claude-plugin/marketplace.json
jq -e '.name=="agent-kaizen" and .version=="0.11.0"' .claude-plugin/plugin.json
rg -n 'Other hosts: Codex CLI' README.md
rg -n 'plugin (add|install) agent-kaizen@agent-kaizen-tools' README.md
git diff --stat
git status --short --untracked-files=all
```

Then the full gate:

```bash
python3 -m unittest discover -s tests
shellcheck -S warning hooks/*.sh
claude plugin validate .
```

If `claude` is not installed in your sandbox, say so in the report as `not run: claude not installed` and skip only that command. None of these commands needs network or a sign-in. Record any command the environment blocks as `not run: <reason>`, separately from product failures.

## Reporting

Report: the result of Step 0 (host-probe lines or `not run: <reason>`), each verify command with pass/fail (or `not run: <reason>`), `git diff --stat` and `git status --short --untracked-files=all`. Do not commit or push. If a precondition or an anchor line in this brief does not match the repository, stop and report instead of improvising.

## Owner decisions

D1 (state location) and D2 (Copilot labelled experimental) are resolved: yes. Use the text as written; do not ask. If the live Copilot check (O1) later passes, "Experimental" cells may become "Yes" only on the owner's word.

## Suggested agent

Luna, effort low. Risk low.
