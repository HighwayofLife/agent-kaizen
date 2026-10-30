# Portable dispatch and audit scripts

Python 3.9+ and the standard library are sufficient. Dispatch and review also
require an installed, authenticated `codex` CLI on PATH; status uses `ps` when
available. No package installation is needed. Run `--help` on any executable.
No script commits or pushes. Logs and transcripts can contain repository data;
keep generated output private unless you have reviewed it.

Install the entire directory together so relative imports and prompt files work:

```bash
mkdir -p ~/.claude/bin
cp -R scripts/. ~/.claude/bin/
chmod +x ~/.claude/bin/codex-{dispatch,run,review} ~/.claude/bin/{token-audit,dispatch-status}
```

Alternatively, symlink each executable into `~/.claude/bin/` (using absolute
paths to this checkout). Executables resolve their real location, so keep
`codex_common.py`, `codex-run`, `preambles/` and `prompts/` beside the originals.
Add `~/.claude/bin` to PATH. The commands below assume that installation.
The Bash examples use caller-selected log files; create their parent directories
before starting background jobs. Claude Code should use Bash's background
execution facility and read the saved report when the command completes.

## codex-dispatch

Run a brief in a workspace-write Codex session, then run every `-k` check in
the host shell from `-C`, outside the Codex sandbox. Only supply trusted check
commands. Install with the shared instructions above; the adjacent runner is
required and is deliberately used instead of an unrelated helper on PATH.

```bash
codex-dispatch -C "$PWD" -k 'python3 -m unittest discover -s tests' task.md > dispatch.log 2>&1 &
codex-dispatch -C "$PWD" -p planner plan-task.md > planner.log 2>&1 &
codex-dispatch --disable-mcp browser --disable-mcp database -r 1 task.md > dispatch.log 2>&1 &
```

Claude Code should invoke one of these background Bash commands, then read
`OUTDIR` and `report.md`. Reports contain at most 25 lines and end with `STATUS:`.
Default logs live in the target repository's `out/dispatch/<UTC-stamp>-<brief>/`.
`-o DIR` overrides that location; reusing it overwrites matching filenames.
Brief and `-i IMAGE` paths resolve from the caller's directory. `-C` is the
Codex/check working directory. `-p engineer|planner|none` selects a preamble.

Set `CODEX_DISPATCH_MODEL` to your preferred model, or override it with `-m`.
When neither is set, no `-m` is sent to Codex; its configured default applies.
`-e` sets reasoning effort (default `medium`). `--resume THREAD` inherits the
thread's model. Repeat `--disable-mcp NAME` to pass
`-c mcp_servers.NAME.enabled=false`; other configured servers remain unchanged.
Names containing punctuation are quoted as TOML keys.

`-r 0|1|2` caps check-failure resumes (default 2). Each resume receives up to
60 error/tail lines per failing check, each trimmed to 2,000 characters. All
checks rerun, and both latest and per-round logs are retained. Infrastructure
failures caused by overload or an empty final message get one additional
attempt per Codex invocation; this is separate from check resumes.
If executable `tools/codemap` exists in the target, the dispatcher runs
`tools/codemap brief BRIEF` before dispatch and inserts its output before the
task. `CODEMAP_TIMEOUT` sets its timeout in seconds (default 20); absent,
failed, or timed-out codemaps are skipped. Failures are logged.
Exit codes: 0 DONE, 1 CHECKS FAILING, 2 CODEX FAILED or invalid arguments.

## codex-run

Internal Python runner used by dispatch. Install it beside `codex-dispatch`
using the shared instructions; it replaces the original shell helper and needs
no shell-specific array utilities. Prefer dispatch for ordinary use.

```bash
codex-run "${CODEX_DISPATCH_MODEL:-}" medium task.md > runner.log 2>&1 &
codex-run --resume THREAD medium followup.md > runner.log 2>&1 &
```

Claude Code should normally background `codex-dispatch` instead. Direct calls
accept `MODEL EFFORT BRIEF [ARGSFILE]`, or `--resume THREAD EFFORT BRIEF [ARGSFILE]`.
An empty model string uses Codex's configured default. ARGSFILE contains one
Codex argument per line. The runner has no independent model environment
variable; the example passes `CODEX_DISPATCH_MODEL` explicitly. Raw events,
stderr and final messages remain beside the brief, separately for each retry.
It retries once on overload or no final message, resuming the same thread when
an ID is available. Exit 0 means a successful final message; failures are nonzero.

## codex-review

Read-only reviews of diffs, engineering plans, visual acceptance criteria, or
image questions. Install with the shared instructions, including `prompts/`
and `codex_common.py`. All modes run `codex exec` in a read-only sandbox.

```bash
codex-review diff --uncommitted --focus 'error handling' -C "$PWD" > review.log 2>&1 &
codex-review diff --base origin/main > review.log 2>&1 &
codex-review plan plan.md > review.log 2>&1 &
codex-review visual --criteria criteria.md result.png --ref reference.png > review.log 2>&1 &
codex-review look --question 'Are the labels readable?' chart.png > review.log 2>&1 &
```

Claude Code should background the whole Bash command and read its saved report.
Reports and raw output live under `-C`'s `out/dispatch/<UTC-stamp>-review/`.
Reports preserve `VERDICT:` (or `ANSWER:`) and end with `STATUS:`; they are capped
at 25 lines (15 for `look`). Exit 0 includes completed reviews with findings;
exit 2 means review failure or invalid arguments. Missing/empty finals and
overload trigger one retry. Visual criteria accept a file or literal text.
Images attach directly; no image processing dependency is required.

Set `CODEX_REVIEW_MODEL` for diff/plan reviews and `CODEX_LOOK_MODEL` for
visual/look reviews to your preferred models. `-m` overrides the relevant
variable; when unset, no `-m` is passed. `-e` defaults to `medium`.
`--disable-mcp NAME` is repeatable in every mode. Plan reviews also use
`tools/codemap brief PLAN` when available, with `CODEMAP_TIMEOUT` (default 20).
Diff targets are mutually exclusive: `--uncommitted`, `--base`, `--commit`.
Without a target, the original branch heuristic uses `origin/master` when HEAD
is ahead of it, otherwise uncommitted changes; use `--base` for another branch.

## token-audit

Stream Claude transcript JSONL and Codex session JSONL into a compact Markdown
audit. Install the executable using the shared copy/symlink instructions; it has
no helper dependency. Defaults to every folder under `~/.claude/projects/` and
Codex sessions under `~/.codex/sessions/` in a rolling three-day window.

```bash
token-audit --days 7 > audit.log 2>&1 &
token-audit --project example --days 2 --out ./audit-reports > audit.log 2>&1 &
token-audit --since 2026-01-01 --json > audit.json 2> audit-errors.log &
```

Claude Code should invoke a background Bash command and read the printed report
path. `--project SUBSTRING` filters folder names case-insensitively;
`--project-dir DIR` can explicitly select one or more folders. `--out DIR` is a
directory (default `~/.claude/audits/`), containing timestamped Markdown reports.
Normal stdout prints that path and totals; `--json` includes `report_path` and
all structured results. `--days N` and `--since YYYY-MM-DD` are mutually exclusive;
dates use UTC. There are no model environment variables; `HOME` controls default
storage locations. `--codex` is accepted for compatibility; sessions are already
included by default.

Duplicate assistant message IDs across selected transcripts count once. Entries
without message IDs count individually. Duplicate file paths are scanned once.
Codex counts final cumulative session totals for sessions with usage events in
the window, including resumes of older files, attributed to the latest model.
Cached input is a subset of Codex input and is never added twice. Claude context
includes input, cache reads and cache creation. These are usage counts, not
currency estimates. Reports cap at 80 lines; JSON retains all rows. Malformed
rows are skipped and reported. Generic high median agent-call counts are flagged.
Exit 0 means the report was written; errors use nonzero exit codes.

## dispatch-status

List running dispatch commands and the latest saved report per supplied target
repository/worktree. Install the standalone executable with the shared
instructions. No model or project-specific environment variables are used.

```bash
dispatch-status "$PWD" ../another-worktree > status.log 2>&1 &
```

Claude Code can background this Bash command and read `status.log`. With no
paths it inspects the current directory. It reads `out/dispatch/*/report.md`;
review reports appear there too. It makes no changes and does not poll.

## Offline checks

```bash
python3 -m unittest discover -s tests -v
```

Tests create a fake `codex` executable on PATH and synthetic transcripts in
isolated temporary directories. No network, Docker, or real Codex session is
used. All executable scripts are Python, so shellcheck does not apply.
