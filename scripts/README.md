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
`kaizen_credentials.py`, `codex_common.py`, `codex-run`, `preambles/` and `prompts/` beside the originals.
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
60 error/tail lines per failing check, each trimmed to 2,000 characters. Resume
rounds re-run failing checks, then confirm skipped checks once. Checks see
`DISPATCH_ROUND` and `DISPATCH_PASS` (`initial`, `retry`, `final`); latest and
per-round logs are retained. Infrastructure
failures caused by overload or an empty final message get one additional
attempt per Codex invocation; this is separate from check resumes.
If executable `tools/codemap` exists in the target, the dispatcher runs
`tools/codemap brief BRIEF` before dispatch and inserts its output before the
task. `CODEMAP_TIMEOUT` sets its timeout in seconds (default 20); absent,
failed, or timed-out codemaps are skipped. Failures are logged.
Exit codes: 0 DONE, 1 CHECKS FAILING, 2 CODEX FAILED or invalid arguments.
The report's `STATUS:` word is `DONE`, `CHECKS FAILING` or `CODEX FAILED`. On a
Codex failure, `Reason:` shows the cause; when Codex gave no final message it is
the last five stderr or error-event lines.

Built-in check `require-change` (shown as `Check 0`) fails an engineer run that
changed nothing. It is decided per Codex run, from a snapshot taken right before
and after the run, and is cumulative across rounds. Files written by `-k` checks
never count, a commit by Codex counts, and ignored files do not. The snapshot is
limited to the subdirectory when `-C` is a subdirectory of a Git repository
(changes elsewhere in the repo do not count); with `-C` at the repo root it
covers the whole repo. HEAD movement still counts, and the output directory is
excluded when it is inside the repo. Pass `--allow-no-change` when no change is
expected. The resume prompt after a failed check does not mention that flag; it
says no files changed and asks for the change or a plain reason none is needed.
The report and `--help` still name the flag.
If the tree was dirty before dispatch, the report has `WARNING: tree was dirty
before dispatch (N paths)`; if the snapshot fails, `WARNING: tree snapshot
failed: <reason>; require-change skipped`.

Reason guard: a model whose name matches a token in `CODEX_DISPATCH_REASON_MODELS`
(comma-separated, case-insensitive, default `sol`, empty = off) needs a line
`<Token> reason: <why>` or `Model reason: <why>` in the brief, outside code
fences. A token matches a whole name segment, optionally followed by digits
(`sol`, `gpt-6.1-sol`, `sol2` match; `solhigh` does not). Without it the
dispatch prints `Reason: model "<m>" needs a line ...` and `STATUS: CODEX
FAILED` (exit 2) before it creates `out/`. Only the name given by `-m` or
`CODEX_DISPATCH_MODEL` is checked; `--resume` is exempt. A line indented by
four or more spaces or a tab does not count, and a reason that is only a
placeholder in angle brackets, such as `<why>`, does not count.

`--check-timeout SECONDS` kills a `-k` check (default env
`CODEX_DISPATCH_CHECK_TIMEOUT`, else 1800; 0 = no limit); it shows as `Check N
FAIL: <cmd> — TIMEOUT after Ns` and is resumed like any failed check.
`--codex-timeout SECONDS` limits a Codex run (default env
`CODEX_DISPATCH_CODEX_TIMEOUT`, else 0 = no limit); a timeout gives `Reason:
Codex timed out: TIMEOUT after Ns` and `STATUS: CODEX FAILED`. Every Codex run
and every `-k` check runs in its own process group. SIGINT, SIGTERM or SIGHUP
to `codex-dispatch` kills that group before it exits. SIGTERM exits 143 and
SIGHUP exits 129.

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
Without a target, the default base is `origin/HEAD`, or the first existing ref
of `origin/main`, `origin/master`, and `origin/develop`. It is used only when
HEAD is ahead, and printed as `Base: <ref> (default)`. Otherwise uncommitted changes are
reviewed. An empty working tree with no ahead base prints `Error: nothing to
review: ...` and `STATUS: REVIEW FAILED`. With uncommitted changes and an
auto-chosen base, the header adds `Note: uncommitted changes are NOT part of this
review; pass --uncommitted to review them.` The STATUS words are `DONE` and
`REVIEW FAILED`. When no ignore rule covers `out/`,
it is added to the repository's `info/exclude` (shared by its worktrees).

## token-audit

Stream Claude transcript JSONL and Codex session JSONL into a compact Markdown
audit. Install the executable using the shared copy/symlink instructions; it has
no helper dependency. It reads Claude projects from `$CLAUDE_CONFIG_DIR` (default
`~/.claude`) and Codex sessions from `$CODEX_HOME` (default `~/.codex`) in a
rolling three-day window.

```bash
token-audit --days 7 > audit.log 2>&1 &
token-audit --project example --days 2 --out ./audit-reports > audit.log 2>&1 &
token-audit --since 2026-01-01 --json > audit.json 2> audit-errors.log &
```

Claude Code should invoke a background Bash command and read the printed report
path. `--project SUBSTRING` filters Claude folder names case-insensitively and does not
filter Codex sessions (`--cwd` selects both);
`--project-dir DIR` can explicitly select one or more folders; repeat `--cwd PATH` to select transcripts by working directory. `--out DIR` is a
directory (default `<Claude config dir>/audits/`), containing timestamped Markdown reports.
Normal stdout prints that path and totals; `--json` includes `report_path` and
all structured results. `--days N` and `--since YYYY-MM-DD` are mutually exclusive;
dates use UTC. The five threshold flags are `--stuck-repeats` (3), `--fact-sessions` (3),
`--prune-prompts` (10), `--prune-min-sessions` (2) and `--prune-sessions` (5).
`--days` must be 0 to 36500. There are no model environment variables. `--codex` is accepted for compatibility; sessions are already
included by default.

`--extract-out DIR` selects the machine-readable extract folder. Its default is
`<Claude config dir>/audits/extracts/`, independent of `--out`. Each report has a
matching `<report stem>.extract.json` file, where the stem is the report file name
without `.md`. The report records only this file name in
`<!-- token-audit-extract {"v": 1, "file": "<report stem>.extract.json"} -->`,
directly after its scope comment. The scope comment still follows the headline
comment. Extracts are written atomically. An extract write error goes to stderr;
the audit still exits 0 if the report was written. `--json` also includes the
absolute `extract_path`, or null if the extract could not be written.

Extract v1 has exactly `v` (1), `scope` (the report's scope dict), `since` (the
audit cutoff), `report` (the report file name only), and `usage`. `usage.agents`
holds the same rows as `agent_usage` in `--json`; `usage.sessions`,
`usage.task_switches`, and `usage.instructions` are empty lists for now.
Agent rows contain `agent`, `spawns`, `calls_median`, `calls_p90` (nearest rank),
`cost`, `cost_share`, `models` (calls by model), `effort` (counts by label),
`result_chars_median`, `stuck_share`, `failure_rate`, and
`cheaper_model_candidate`. Missing effort is `unknown`; missing result sizes
are null. Costs and shares are rounded to six decimal places. Result sizes count
serialized main-session Agent results; background launches can return short text.

The cheaper-model hint requires a cost share of at least 5%, median calls of at
most 15, a known median result size of at most 4000 characters, and at least one
priced model with an output rate above the cheapest `claude-` pricing entry.
Unpriced models are ignored. Without pricing the hint is false. Section 3 also
shows each agent type's cost share, up to three models by call count, and effort
counts. These are hints for review, not automatic model changes.

Duplicate assistant message IDs across selected transcripts count once. Entries
without message IDs count individually. Duplicate file paths are scanned once.
Codex numbers are in-window deltas: rows before the window set the baseline,
and a counter decrease is treated as a reset. The header reads `Since: <date>
(UTC; Claude calls in window, Codex in-window token deltas).`
Cached input is a subset of Codex input and is never added twice. Claude context
includes input, cache reads and cache creation. These are usage counts, not
currency estimates. Reports cap at 80 lines; JSON retains all rows. Malformed
rows are skipped and reported. Generic high median agent-call counts are
flagged. Claude and Codex brief sizes are reported, and median growth between
audits is flagged.
Reports include scope metadata and compare only with an earlier report of the same scope. Pre-0.4.0 reports have no scope and are not compared. Flags use per-call intensity, not volume.
Exit 0 means the report was written; errors use nonzero exit codes.

Cost uses `pricing.json`. A price key or alias matches a model id only when the
rest of the id is empty, a `-YYYYMMDD` suffix, a bracket suffix such as `[1m]`,
or both; the longest match wins. Anything else, including a newer sibling model,
is Unpriced and appears in the Unpriced table. When `source.checked` is more than
60 days old the Cost section adds `Pricing last checked <date> (<N> days before
this audit); rates may be out of date.` (`cost.pricing_warning` in `--json`).
Zero-usage `<synthetic>` rows are not counted as calls.

## kaizen-scheduled

`kaizen-scheduled config show [--for DIR]` shows effective settings and the report path; `config set [--for DIR] KEY=VALUE...` merges settings, including global `retention` and `retentionOverrides`. `audit` writes a global audit; `review` audits and reviews due projects. `review --dry-run` previews without writes or tokens; add `--json` for structured output. Repeat `--project-dir DIR` to replace discovery, or use `--now` to set the review time.

`housekeep [--dry-run] [--audits DIR]` removes old generated audit files under the retention settings. Use `--dry-run` to preview deletions.

Both audit and review accept `--audits`, `--python`, `--token-audit` and `--pricing` overrides. Review also accepts `--claude`, `--model` and `--max-turns`. Run each subcommand with `--help` for details.

Under `<Claude config dir>/audits`, global reports are `token-audit-*.md`, extracts live in `extracts/`, and `projects/index.json` is the registry. Each `projects/<key>/` holds `state.json`, project `token-audit-*.md` and `cycle-<date>.md` (a second proposal on the same day gets a `-2` suffix). Scheduler output goes to `run.log`. `config set` takes a lock file, `agent-kaizen.json.lock`, beside the global config (beside the link when the config is a symlink), and leaves it in place. Reviews also lock the backup root, where protected active-run markers support hard-kill recovery across audits folders. The primary marker is `.active-run.json`; additional markers use `.active-run.<32-lowercase-hex-uuid>.json`. Unresolved recovery retains its marker and snapshots and makes each retry propose-only. The status gives a non-forced undo command when available and a command to discard the record after manual resolution. Statuses, run lock, timeouts, hard-kill recovery, auto-mode opt-in (`autoProjects`) and environment variables are in [docs/scheduling.md](../docs/scheduling.md).

## dispatch-status

List running dispatch commands and the latest saved report per supplied target
repository/worktree. Install the standalone executable with the shared
instructions. No model or project-specific environment variables are used.

```bash
dispatch-status "$PWD" ../another-worktree > status.log 2>&1 &
```

Claude Code can background this Bash command and read `status.log`. A process counts as running only when its argv has a word whose basename is `codex-dispatch`. It falls back to `git worktree list --porcelain` on git older than 2.36. Runs started with `-o DIR` are not shown. With no
paths it inspects the current directory. It reads `out/dispatch/*/report.md`;
review reports appear there too. It makes no changes and does not poll.

## Offline checks

```bash
python3 -m unittest discover -s tests -v
```

Tests create a fake `codex` executable on PATH and synthetic transcripts in
isolated temporary directories. No network, Docker, or real Codex session is
used. All executable scripts are Python, so shellcheck does not apply.

## install-schedule

Install, preview or remove the scheduled jobs (launchd, cron or systemd user
timers). Without `--apply` or `--remove` it only prints them.

```text
install-schedule [--scheduler auto|launchd|cron|systemd] [--apply] [--remove]
                 [--review] [--auto [all|none|DIR ...]]
                 [--project-dir DIR] [--model MODEL] [--max-turns N]
```

`--apply` installs the audit job and the managed scripts (through `kaizen-link`)
and adds the weekly review with `--review`. `--auto` implies `--review`.
`--apply` without `--review` or `--auto` removes an installed review job; the
audit job stays. If a review job is also installed in another backend (launchd
agent, systemd timer or cron line), it is left alone and a warning goes to
stderr, one per backend, with the command that removes it. `--remove` removes
both. Errors print `install-schedule:
<error>` and exit 2. See [docs/scheduling.md](../docs/scheduling.md).

## kaizen-backup

Backups, manifests and undo for Agent Kaizen changes.

```text
kaizen-backup begin --skill NAME --ledger TEXT [--run RUN_ID] FILE...
kaizen-backup finish CHANGE_DIR [--verification passed|failed]
kaizen-backup action CHANGE_DIR --did CMD --undo CMD
kaizen-backup list [--all]
kaizen-backup undo [last|run|CHANGE_DIR] [--force]
kaizen-backup prune --older-than DAYS [--apply]
```

`begin` copies existing files, records missing ones as created, refuses
credential paths and prints the change folder; run it before editing. Run and skill names cannot contain `/`, `..` or NUL. `finish`
records each file's sha256 after the edit. `action` records a non-file action
and its reverse command; `undo` prints that command and never runs it. `list`
shows changes newest first.

`undo` takes `last` (default), `run` (the changes of the newest run) or a change
directory. It restores files and deletes created files whose hash still matches.
A file changed since `finish` is a conflict and nothing is restored unless
`--force` is given. Undo of an unfinished change whose created file exists is
also a conflict (`<path> was created by <change>, which was never finished`,
exit 2); `--force` removes it. For several changes only the newest one touching
a path has its hash checked, and restore runs newest first. A corrupt manifest
is skipped with a message on stderr. `undo run` also reports a conflict when a
file was edited by hand between two changes of the run: `<path> was edited
between <older change> and <newer change>`. `--force` skips this check.
`undo run` undoes only the newest group of consecutive changes that share one
run id and session. Older changes that reused the id are left open, and stderr
says `kaizen-backup: run id <id> also appears on older changes; not undoing: <change>, ...`.
Undo those with `kaizen-backup undo CHANGE_DIR`.

`prune` lists finished changes created more than DAYS days ago (DAYS must be 1
or more). It is a dry run unless `--apply` is given, which deletes them. Each
change gets one line, `would remove <folder>\t<created_at>\t<N> bytes` (or
`removed ...`), then a total line with the count and bytes freed. It never
removes unfinished changes, changes with a corrupt manifest, changes without a
usable `created_at`, or anything newer than the cutoff; each is reported as
`skipped <folder>: <reason>`. Each change restores from its own backup, so
pruning an older change does not affect `undo` of a newer change to the same
file.

The backup root is `KAIZEN_BACKUP_DIR` if set (empty counts as unset), else
`<Claude config dir>/kaizen-backups`. The backup root is created with mode 700; an existing root is set to mode 700
only when it is the default location; a directory chosen with
`KAIZEN_BACKUP_DIR` keeps its mode; change folders are always mode 700.

## usage-series

Write `daily.csv` and `daily-agents.csv` to an explicit output directory. Dates
are UTC; `--until` includes the whole day. The default starts 30 days ago and
ends today. Empty days have zero measurements. With no selection, scan all
projects. Repeat `--cwd` for directories and descendants, or `--project` for
substrings (Claude project folder names; Codex recorded cwd). The two selection
options cannot be combined. `CLAUDE_CONFIG_DIR` and `CODEX_HOME` are honored.
Subagent transcripts whose parent transcript is gone may be missed by `--cwd`.
There is no `--days` option; use `--since YYYY-MM-DD`. `--out` is required.

`--from-db` reads calls, tokens and cost from the [usage-db](#usage-db) store
instead of transcripts, for windows whose transcripts have been deleted. Calls without an id that share the same second and usage count once in the database. With no
database it exits 1 (`usage-series: no database at PATH; run: usage-db ingest`).
`--git` still reads git. The database does not store some measurements, so
`daily.csv` has `n/a` (not 0) in `wakeups`, `wakeup_avg_ctx`, `main_images`,
`main_reads`, `spawns_total`, `codex_threads_db`, `codex_tokens_db`, every
`codex_tokens_db_*` and every `command_*` column, and `daily-agents.csv` has
`n/a` in `runs`. Other columns match the transcript output where both have full
data. `--cwd` matches the stored working directory and its descendants.
`--project` matches the transcript folder name rebuilt from the stored path
(every character outside a-z, A-Z, 0-9 becomes `-`) for Claude calls, and the
stored working directory for Codex calls.

```bash
usage-series --since 2026-10-01 --until 2026-10-30 --cwd . --out out/series
usage-series --since 2026-10-01 --out out/series --git . \
  --count-command 'codemap=^tools/codemap'
```

Main context includes fresh input, cache reads and cache writes. Wake-ups are
main calls following task notifications. Main reads count completed `Read`
requests with neither `offset` nor `limit`. Command regexes search the original
Bash command in both main and subagent transcripts; each tool call counts once.
Columns use `command_NAME`. Agent runs count each transcript once per day.
`codex_sessions` counts each session once per active day; a session crossing
midnight counts twice when daily counts are summed.
The CSVs contain dates, agent-type labels and numbers, without paths or prompts.

`claude_context_tokens` and `claude_output_tokens` include main and subagent
usage across all Claude models. Context is input plus cache reads plus cache
writes. `main_context_tokens` and `sub_context_tokens` split that context by
main session and subagents. Zero-token `<synthetic>` rows are ignored.

Costs use the adjacent `pricing.json`, including aliases, cache rates and
context thresholds. Override it with `--pricing FILE`. Claude costs are grouped
by family; Codex costs also have `cost_codex_model_MODEL` columns for priced
models. Unknown models contribute zero cost with a warning. `unpriced_calls`
counts calls whose model has no price that day; warnings list the model ids.
Costs are API list price equivalents, not bills. Do not add model columns to family columns;
`cost_total` already sums the family columns once.

The highest numbered `CODEX_HOME/state_*.sqlite` is opened read-only. Only
`created_at`, `model`, `cwd` and `tokens_used` are queried. A locked database is
copied with its WAL and SHM into a temporary directory. Missing tables or
columns produce one warning. `codex_threads_db`, `codex_tokens_db` and
`codex_tokens_db_FAMILY` assign each thread's lifetime total to its creation day.
These tokens include cached input and do not split cached, fresh and output
usage, so they measure volume and cannot supply a price. They overlap session
log usage; do not add them.

Repeat `--git REPO` for optional activity. Non-merge commits across all refs are
counted once by author date in UTC, including across repeated repositories.
`lines_changed` sums insertions and deletions; binary files are skipped.
Invalid repositories produce a warning.

## usage-compare

Compare days with at least 50 main calls on each side. The cutoff is the first
after day; `--before-from` and `--after-to` are inclusive bounds. Totals and rates
use only the listed active days. Average context is weighted by main calls;
peak context is the maximum. Ratios are after / before; a zero denominator is
`n/a`. Override the activity threshold with `--active-min-calls N`.

`--from-db` (needs `--clean-split`; with `--series` it exits 2) computes the
clean-split metrics from the usage-db store, Claude calls only. Calls without an id that share the same second and usage count once in the database. Windows are split
by call time, so the rule that drops files modified at or after the cutoff does
not apply: a transcript that spans the cutoff is split, not dropped.
`wake-ups/day` and `images/day` print `n/a` because the database stores neither.
The first warning line says the split uses the usage database. A missing
database exits 1 with `usage-compare: no database at PATH; run: usage-db ingest`.

```bash
usage-compare --series out/series --cutoff 2026-10-20 --before-from 2026-10-01
usage-compare --series out/series --cutoff 2026-10-20 --json
usage-compare --cutoff 2026-10-20 --before-from 2026-10-01 \
  --clean-split --cwd .
```

Fewer than three active days produces a warning. Each day with DB tokens but
zero Codex log cost is excluded from Codex and total cost rates, including
their call and commit denominators. Warnings list excluded dates and coverage.
When no days remain, these costs show `n/a (logs missing)`. Claude metrics use
all active days. Unpriced calls on either side produce a warning.
Command counts appear per day and per main call.
`Claude tokens/day` adds context and output. When both sources are present,
`Claude + Codex DB tokens/day` and `tokens/commit` add Claude tokens to Codex DB
tokens. This measures volume, not price; Codex DB tokens include cached input.
JSON contains the same metrics, ratios, active days and warnings; unavailable
numbers are `null` and the `unavailable` list identifies missing-log costs.

`--clean-split` reads local Claude transcripts instead of `daily.csv`.
`--series` is optional here. A window with zero main calls produces a warning.
It keeps only files last written before the cutoff in the before set, including each
subagent file independently. Both sets are filtered to their UTC windows.
It calls the adjacent token-audit with both report and extract outputs in a
temporary directory. Codex logs and DB totals are excluded from this mode.
Rates use elapsed UTC days, not active days. The before window defaults to the
30 days before the cutoff, and the after window ends now unless `--after-to`
is set. Pass the original selection and pricing options again; CSVs do not
store private scope information.

## usage-db

Keep per-call token usage in a small SQLite file, so history survives after
Claude Code deletes old transcripts and repeat reports do not re-read them.
The file is `$KAIZEN_USAGE_DB` if set, else `kaizen-usage.db` in
`CLAUDE_CONFIG_DIR` (default `~/.claude`). `--db PATH` overrides both. It is
created with mode 0600. It holds only ids, timestamps, model names, working
directory paths and token counts, never message text. The scheduled `audit` job runs `usage-db ingest --quiet`.

```bash
usage-db ingest [--db PATH] [--quiet]
usage-db status [--db PATH]
usage-db report [--db PATH] [--since YYYY-MM-DD] [--until YYYY-MM-DD]
                [--by day|model|project|agent|session|source]
                [--project SUBSTR] [--source claude|codex]
                [--format table|csv|json] [--pricing PATH]
usage-db prune --older-than DAYS [--apply] [--db PATH]
usage-db sql QUERY [--db PATH] [--format table|csv|json]
```

`ingest` finds Claude transcripts and Codex sessions the way `usage-series`
does (`CLAUDE_CONFIG_DIR`, `CODEX_HOME`). It skips a file whose size and
modification time match the last run, and reads a new or changed file from the
start, adding only calls it has not stored. One message id counts once across
files. Zero-token `<synthetic>` rows are not stored. Codex rows store the
change since the previous cumulative counter. A file that is later deleted
keeps its rows. Bad lines and unreadable files are counted and printed as
warnings, not errors. `--quiet` prints nothing.

Schema version 2 keys Codex call ids by the session id stored inside the session
file (the `id` in its first line), not the file name, so a session file that is
copied or moved to a new name is not counted twice. A file with no session id
falls back to its file name. A version 1 database is upgraded in place by the
next `ingest`, with no flag or prompt. Codex rows whose session file still
exists are re-keyed, and rows already stored twice under two file names collapse
to one. Rows whose file was deleted before the upgrade keep their old ids, so a
session that was also copied stays counted twice. `status`, `report` and `sql`
read a version 1 database without migrating it.

`status` shows the path, size, schema version, calls per source, first and last
day and last ingest time. A missing database exits 1.

`report` groups calls, tokens, cost and unpriced calls by `--by` (default
`day`) and adds a total row. Dates are UTC days and `--until` is inclusive.

Cost is not stored. `report` prices each call when it runs, with `pricing.json`
(or `--pricing`), so a corrected price also corrects old rows. Models without a
price show as `unpriced_calls` and add no cost.

`prune` deletes calls whose UTC day is before today minus DAYS and runs
`VACUUM` when `--apply` is given. Without `--apply` it is a dry run that prints how many calls and which
dates would go, and changes nothing. DAYS must be a whole number of 1 or more,
otherwise it exits 2. A missing database exits 1 and is not created. Nothing is
pruned automatically: `ingest` and `report` never delete. A transcript that
still exists and later changes is read again in full, which stores its pruned
calls again.

`sql` runs one statement against a read-only connection; an error exits 2.
Tables are `calls`, `files` and `meta`. A database written by a newer schema
version is refused with exit 2.

A file that is not a usable SQLite database is refused with `usage-db: <path> is
not a usable SQLite database: <sqlite message>` and exit 2. It is not modified.

## kaizen-link

Install or check managed scripts and hooks. Cache installs use copies; `localScripts` marks intentional differences.

```text
usage: kaizen-link [-h] [--bin BIN] [--hooks-dir HOOKS_DIR]
                   [--mode {auto,link,copy}] [--only ONLY]
                   [--apply | --check | --unlink]
                   [--replace | --replace-prefixed] [--restore-replaced]
                   [--json] [--plugin-root DIR]
```

Output says `linked` or `copied`. A live symlink that points outside the plugin is `DRIFT <name> re-run kaizen-link --apply --replace` and is left alone. `--replace` saves it as `NAME.replaced-<date>` and installs the plugin's version. Broken links, links into the plugin root and links into an older plugin cache copy are fixed without `--replace`. A link into
another copy under `plugins/cache` or `plugins/marketplaces` counts as this
plugin's own only when a path component equals the plugin name. `--unlink` removes links into the plugin and copies that are byte-identical to the source (`removed copy`); a differing copy is left (`skip: differs from the plugin source, left in place`). A malformed `agent-kaizen.json` gives a warning and only symlinks are removed. `--restore-replaced` (with `--unlink`) restores the newest `.replaced-*` file. `--only` takes comma-separated names; spaces are ignored.

Example: `kaizen-link --check`.

## packet-report

Read outcomes and propose calibration changes using the [outcome log contract](../docs/outcome-log.md).

```text
usage: packet-report [-h] [--packets PACKETS | --project PROJECT]
                     [--since SINCE] [--until UNTIL] [--ladder LADDER]
                     [--markdown | --json]
```

An escalation is labelled by its full path of model names, with consecutive duplicates removed (`terra->sol->terra`). Names are normalised against the calibration ladder. `rounds: 1.0` is accepted; `1.5` and NaN make that history invalid. An escalation is also counted when only the effort rises between rounds (same model); such a pair is labelled with model and effort (`terra:medium->terra:high`). When only the model changes the label stays the model path (`terra->sol`). If both change, every step is labelled `model:effort`.

Example: `packet-report --project . --markdown`.

## kaizen-project-report

Report outcomes, calibration proposals, configured command output and pending ledger rows for an enrolled project. Global `projectCommands` supplies argv lists; each command has a 120-second timeout.

```text
usage: kaizen-project-report [-h] --project PROJECT [--since SINCE]
                             [--out OUT] [--json] [--verbose]
```

Example: `kaizen-project-report --project .`.

## rules-lint

Find stale wording using `rules-lint.patterns`, the user file `kaizen-rules-lint.txt` in the Claude config directory, and each project's `docs/kaizen/rules-lint.txt`. Global `rulesLintFiles` adds files to scan.

```text
usage: rules-lint [-h] [--repo DIR] [--json]
```

A repository with only `AGENTS.md` is detected. The bundled `rules-lint.patterns` hold no personal patterns; put them in `<Claude config dir>/kaizen-rules-lint.txt` or `docs/kaizen/rules-lint.txt`.

Example: `rules-lint --repo .`.

## notes-ledger

Record changes, update them, or propose due measurements. Configure paths in global `notesLedger` in `agent-kaizen.json`: `csv` (required), `timeline` (optional) and `measureAfterDays` (default 7). Paths must be strings. Unattended runs may only use `add`.

```text
notes-ledger add --date D --category C --change X --why W --measure M --source S
                 [--status planned|active] [--dry-run]
notes-ledger set --match TEXT [--status planned|active|superseded|reverted]
                 [--measured yes|no] [--effect TEXT] [--dry-run]
notes-ledger due [--project DIR] [--json]
```

The CSV header is `date,category,change,source,status,measured`. `add` does not create the file: it must exist with that header, and the error names the path. `add` treats a same-date row as already present only when the text before ` Why: ` is equal. `set --match` selects the CSV row whose change cell contains TEXT; it must select exactly one row. In the timeline it matches the row exactly first, and falls back to a substring only when no exact row exists. Errors name the row (`invalid CSV row N: expected 6 columns, found K`). A BOM and blank lines are tolerated, `add` keeps the file's line ending, and a symlinked ledger stays a link.

Exit codes: 0 success, 1 file or runtime error, 2 invalid data or arguments, 3 no `notesLedger.csv` configured.

Example: `notes-ledger due`.
