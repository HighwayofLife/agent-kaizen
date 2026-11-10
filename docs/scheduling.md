# Running the loop on a schedule

| Job | Frequency | Tokens |
|---|---|---|
| Global audit (`kaizen-scheduled audit`) | About every 3 days | None |
| Per-project review (`kaizen-scheduled review`) | Weekly, when due | One headless Sonnet run per project |
| Session notice | Session start | None |

## Why local and not cloud

Cloud scheduled tasks run on a fresh clone without your local transcripts. They cannot audit local Claude Code and Codex sessions. `/loop` only lasts while a session is open. A local scheduler can read these files; a Claude Desktop scheduled task can also run locally while the machine is awake.

## Install

Run `scripts/install-schedule` from the plugin or your clone. Without `--apply` or `--remove`, it prints the jobs without installing them. For example, inspect both scheduler outputs with:

```bash
scripts/install-schedule --review
scripts/install-schedule --scheduler systemd --review
```

For example, with a temporary home and executable used only to show the output, launchd prints:

```xml
        <string>/Library/Developer/CommandLineTools/usr/bin/python3 /private/tmp/kaizen-example/.claude/bin/kaizen-scheduled audit &gt;&gt; /private/tmp/kaizen-example/.claude/audits/run.log 2&gt;&amp;1</string>
        <string>/Library/Developer/CommandLineTools/usr/bin/python3 /private/tmp/kaizen-example/.claude/bin/kaizen-scheduled review --python /Library/Developer/CommandLineTools/usr/bin/python3 --claude /tmp/kaizen-example/bin/claude &gt;&gt; /private/tmp/kaizen-example/.claude/audits/run.log 2&gt;&amp;1</string>
```

The paths below were captured on macOS; on Linux they show your own `python3` and home directory.

The systemd output for the same example includes:

```ini
ExecStart=/bin/sh -c '/Library/Developer/CommandLineTools/usr/bin/python3 /private/tmp/kaizen-example/.claude/bin/kaizen-scheduled audit >> /private/tmp/kaizen-example/.claude/audits/run.log 2>&1'
ExecStart=/bin/sh -c '/Library/Developer/CommandLineTools/usr/bin/python3 /private/tmp/kaizen-example/.claude/bin/kaizen-scheduled review --python /Library/Developer/CommandLineTools/usr/bin/python3 --claude /tmp/kaizen-example/bin/claude >> /private/tmp/kaizen-example/.claude/audits/run.log 2>&1'
```

The printed job commands call the installed `kaizen-scheduled audit` and `kaizen-scheduled review`; their absolute paths, Python interpreter and Claude executable depend on your installation. Install or remove them with:

```bash
scripts/install-schedule --apply
scripts/install-schedule --apply --review
scripts/install-schedule --remove
```

The first installs the audit; the second adds the weekly review. `--apply` without `--review` (and without `--auto`) removes a review job this plugin installed earlier on the chosen backend: the launchd job, the `# agent-kaizen-review` cron line or the systemd review timer. It prints `removed review job (not requested; pass --review to keep it)` (`would remove ...` in a preview). The audit job is never touched. Removal covers only the chosen backend. `--apply` prints a plan, then installs managed scripts through `kaizen-link --mode auto --replace-prefixed` into the Claude config directory's `bin/`. Source checkouts use links; plugin cache installs use copies so jobs survive plugin moves. Differing `kaizen-` and `kaizen_` files are saved as `.replaced-<date>`; differing generic files are reported as DRIFT and left alone. The installer passes both `--bin` and `--hooks-dir` explicitly, so a custom bin never writes hooks into the default config home. Re-run it after an update. Jobs record `PATH` and, when set, `CLAUDE_CONFIG_DIR`, `CODEX_HOME` and `KAIZEN_BACKUP_DIR`. Use `--model` and `--max-turns` to override the review defaults (Sonnet and 40 turns).

Errors: a failed scheduler command or file write prints `install-schedule: <error>` on stderr and exits 2, and the `--auto` config step is skipped. On cron, if `crontab -l` fails with anything other than "no crontab", `--apply` and `--remove` print `install-schedule: crontab -l failed, crontab left unchanged: <stderr>`, exit 2 and write nothing.

The installer records its source root in `bin/.kaizen-plugin-root`. The Drift check passes `--plugin-root` to `kaizen-link`, using `CLAUDE_PLUGIN_ROOT` when set, otherwise that record. If neither is known, Drift reports `unavailable` with a reason. If the source has moved, set `CLAUDE_PLUGIN_ROOT` or re-run the installer from its new location.

### Install through links

`kaizen-link` installs managed scripts and hooks as links, or as copies when the plugin is in a cache. Run `kaizen-link --check` to report drift; list intentional differences in `localScripts`. `--apply --replace` saves differing files with a `.replaced-<date>` suffix before replacement.

### Rollback after link replacement

Run these in order after `kaizen-link --replace`:

1. `kaizen-link --unlink --restore-replaced`
2. `kaizen-backup undo <dir>`

Unlink first: undo through a symlink writes into plugin sources. `begin` resolves user paths and the backup root, so symlinked home and temporary directories work. Finish and undo require stored target paths to remain canonical, with no final symlink, and reject directory targets before restoring anything, including with `--force`. Keep the backup directory if rollback fails and resolve the link before retrying.

## Discovery and activity

Enrolled projects have a `docs/kaizen/` directory. Discovery reads the newest five Claude Code transcripts in each project folder (of any age), Codex sessions from the last 30 days, and a registry of previously seen projects. A session in a subfolder maps to its enrolled project. A `docs/kaizen/` folder in a subdirectory of a larger git repository makes that subdirectory its own project; the git root is the project only when the root has `docs/kaizen/`. `config show --for DIR` resolves the project a real run would use. Linked git worktrees of a repository count as one project. Reports, checks and cycles run once in the enrolled canonical repository, even when only a worktree was discovered or selected. Worktree sessions still count as activity. Repeat `--project-dir DIR` to replace discovery with selected projects.

An active project is due when a session or a commit on a local branch occurred since its last review. The first run looks back seven days. A successful review records its exit time as `reviewed_at`; only later activity counts, and its own Claude session is excluded by id. Commits and Codex sessions during a successful review therefore do not make it due again. A failed or killed review does not update `reviewed_at`, so activity during it counts and it is tried again. `schedule=always` skips this gate. There is no review cap.

```bash
scripts/kaizen-scheduled review --dry-run
```

## Configuration

Settings live in `agent-kaizen.json` in the Claude config directory and in each project's `docs/kaizen/config.json`.

| Key | Scope | Values and default |
|---|---|---|
| `enabled` | Global | `true` (default), `false` disables all scheduled work |
| `schedule` | Global or project | `active` (default), `always`, `off` |
| `scheduledAutonomy` | Global or project | `propose` (default), `auto`. A project file's `auto` counts only if the project is in `autoProjects` |
| `autoProjects` | Global only | List of absolute project paths, default `[]`; the opt-in for project-level `auto` |
| `retention` | Global only | `auto` (default), `off` keeps everything |
| `retentionOverrides` | Global only | Object, default `{}`; for example `{"extracts":{"days":14}}` |
| `projectCommands` | Global only | Object mapping absolute project paths (or `~/` paths) to `outcomeLog` relative paths and `shadowStatus`, `slowTests`, or `speedReport` argv lists; default `{}` |
| `notesLedger` | Global only | Object with `csv` path, optional `timeline` path and positive integer `measureAfterDays`; paths must be absolute after `~` expansion; default `{}` (off) |
| `calibrationLadder` | Global only | List of `model` or `model effort` strings; default `["haiku", "sonnet medium", "sonnet high", "opus high"]` |
| `rulesLintFiles` | Global only | List of non-empty glob strings; default `[]` |
| `localScripts` | Global only | List of non-empty strings without `/`; default `[]` |
| `autonomy` | Global or project | Interactive mode; scheduled runs do not read it |

Global `enabled=false` takes precedence over everything. Otherwise, project settings override global settings, which override defaults. Project values for global-only keys are ignored with a warning. A project file's `scheduledAutonomy: auto` is ignored unless the project's canonical path (symlinks resolved) is in the global `autoProjects`; the run then uses the global or default value, normally `propose`, and prints `config: <project>/docs/kaizen/config.json: scheduledAutonomy=auto in the project file is ignored: <dir> is not in autoProjects ...` with the command to run. `config show --for DIR`, `review --dry-run` and `--json` show this as a `note`. A global `scheduledAutonomy=auto` still applies to every enrolled project. A tracked project config applies to teammates too; put personal choices in the global file.

Use `kaizen-scheduled config set [--for DIR] KEY=VALUE...` to merge settings. `config set --for DIR scheduledAutonomy=auto` writes the project file and adds the path to the global `autoProjects`; `scheduledAutonomy=propose` removes it. A symlinked config file stays a symlink. Both forms of `config set` (global and `--for`) take a lock file, `agent-kaizen.json.lock`, beside the global config (beside the link when the config is a symlink). The file is left in place. `config show [--for DIR]` prints the effective settings and, with `--for`, the report folder. `/agent-kaizen:schedule` and `/agent-kaizen:start` ask for your choices and run the relevant commands. `DIR` must be the project that runs use. For a subdirectory or a linked worktree of an enrolled project, `scheduledAutonomy=auto` is refused with a message that names that project, and nothing is written; other keys are written to that project's `docs/kaizen/config.json`, with a note.

`install-schedule --auto` implies `--review`. `--auto all` sets global scheduled auto mode; `--auto none` sets global propose mode; `--auto DIR...` opts specific projects into auto. Bare `--auto` opts in the one project selected by `--project-dir`, or the current directory. Project opt-in goes through `config set --for DIR scheduledAutonomy=auto`, so it also writes the global `autoProjects`.

Upgrade note: a project that had `scheduledAutonomy: auto` only in its project file runs as `propose` until you run `config set --for DIR scheduledAutonomy=auto` (or `install-schedule --auto DIR`) once.

## Reports and storage

The audits directory is `<Claude config dir>/audits`:

```text
<audits>/token-audit-*.md
<audits>/token-audit-*.reviewed
<audits>/checks-*.md
<audits>/extracts/*.extract.json
<audits>/projects/index.json
<audits>/projects/<key>/state.json
<audits>/projects/<key>/token-audit-*.md
<audits>/projects/<key>/project-report-*.md
<audits>/projects/<key>/*.extract.json
<audits>/projects/<key>/cycle-<date>[-N].md
<audits>/run.log
<audits>/run.log.1
<audits>/.lock
```

A second proposal on the same day is written as `cycle-<date>-2.md`, then `-3`, and never replaces the first. At the start of a non-dry run, a `run.log` larger than 1 MiB is copied to `run.log.1` and truncated. `.lock` is the run lock (see Failure handling).

Reports carry a scope line and compare only with an earlier report of the same scope. Flags use per-call intensity, not volume. Reports from before 0.4.0 lack scope metadata and are never compared.

Each report has a machine-local JSON extract with per-agent usage and a cheaper-model hint. Extracts go in `<audits>/extracts/`, for scheduled and interactive runs alike. They never go into `docs/kaizen/`.

The scheduled `audit` job runs `usage-db ingest --quiet` after the token audit, so the SQLite usage store keeps history after Claude Code deletes old transcripts. The database is `KAIZEN_USAGE_DB`, default `kaizen-usage.db` under the Claude config dir. A failure there is logged as a step failure and never fails the audit.

### Retention

The runner tidies after each scheduled audit and review; interactive cycles run it at the end. `kaizen-scheduled housekeep --dry-run` previews deletions. Use `--audits DIR` to select an audits folder.

| Kind | Files | Default |
|---|---|---|
| `extracts` | `extracts/*.extract.json`, `projects/*/*.extract.json`, `projects/*/host-probe-*.json`, `projects/*/friction-inputs-*.json` | 30 days; 200 MB cap |
| `markers` | `projects/*/cycle-*.failed.md`, `*.noticed-*`, `projects/*/*.noticed-*` | 30 days |
| `ledger-runs` | `projects/*/.ledger-*/*` (ledger snapshots kept after a violation, failed rollback or interrupted run) | 7 days |
| `temp` | `projects/*/cycle-*.md.*` (temporary files of a killed run) | 1 day |
| `reports` | `token-audit-*.md`, `projects/*/token-audit-*.md`, `projects/*/cycle-*.md`, `checks-*.md`, `projects/*/project-report-*.md` | 365 days; newest 5 per folder and family kept |

A report's `.reviewed` marker is removed with it. Only regular files inside the audits folder are deleted; symlinks are skipped. Each deletion is logged: in `run.log` for scheduled runs, on screen for manual ones. Housekeeping does not touch `host-actions.json`, `host-fixes/`, `projects/index.json`, project `state.json` files, `run.log`, `kaizen-backups/`, transcripts, Codex sessions or project files.

Set `retention=off` to keep everything. Override a kind with `kaizen-scheduled config set retentionOverrides='{"extracts":{"days":14}}'`. Each kind accepts positive integer `days`, `hours` and `maxMB`; `hours` takes precedence over `days`.

## Schedulers and environment

macOS uses launchd, with a 72-hour audit interval (`StartInterval` 259200). Linux uses cron when available (`0 9 */3 * *`), or systemd user timers when cron is unavailable (`OnCalendar=*-*-01/3 09:00:00`). Cron and systemd run on days 1, 4, 7, and so on at 09:00; the gap across month end can be shorter than three days. Systemd uses `Persistent=true` to catch up missed runs. Its timers run while logged out only after `loginctl enable-linger <user>`; with `--apply`, the installer prints this hint when lingering is off, but does not run it. Windows is unsupported: run the scripts by hand or use Task Scheduler.

Environment variables read by the scheduled runner:

| Variable | Effect |
|---|---|
| `KAIZEN_REVIEW_TIMEOUT` | Seconds allowed for one model run; default 3600, `0` = no limit. Every other step has a fixed 600-second limit |
| `KAIZEN_LOCK_WAIT` | Seconds a run waits for the run lock; default 1800 |
| `KAIZEN_SKIP_CHECKS` | `1` skips the project discovery and index update, the `checks-*.md` report (drift, stale rules, notes-ledger due) and the per-project report. The token audit, the review and housekeeping still run |
| `KAIZEN_BACKUP_DIR` | Backup root, default `<Claude config dir>/kaizen-backups`; empty counts as unset |
| `KAIZEN_USAGE_DB` | Usage database, default `kaizen-usage.db` under the Claude config dir |
| `KAIZEN_REVIEW_MODEL`, `KAIZEN_REVIEW_MAX_TURNS` | Defaults for `review --model` and `--max-turns` (Sonnet, 40) |

`review` also takes `--force` (skip the activity gate for the projects named by `--project-dir`), `--propose-only` (force the restricted propose-only mode), `--now ISO-TIME` (review time, with UTC offset) and `--json` (with `--dry-run`, list each project's autonomy and its source as JSON).

The installer captures `PATH` and, when set, `CLAUDE_CONFIG_DIR` and `CODEX_HOME`, and sets them inside each job. The Claude config directory defaults to `~/.claude`; Codex home defaults to `~/.codex`.

## Unattended permissions

The runner uses `--strict-mcp-config` and limits `--tools` to Read, Grep, Glob and Bash in propose mode. Propose mode grants no Bash commands. Search with the Grep tool: Bash `rg` can execute a preprocessor via `--pre` or a helper via `--hostname-bin`. No git command is granted; even `git status` can execute helpers from repository config. The runner reports git state. Propose mode uses `--permission-mode dontAsk`.

Auto mode scopes Read, Grep and Glob to the project, Claude config dir, Codex home, plugin root, default audits folder and actual `--audits` folder. It grants Read rules for resolved and unresolved forms; Read rules also scope Grep and Glob. Propose mode grants bare Read, Grep and Glob. Auto mode grants Edit and Write only under the project and both config homes, using explicit absolute path rules. Its exact Bash allow list is the fixed installed `kaizen-backup` path with `begin`, `finish` or `list` (directly, with `python3`, or with the runner's configured Python), and the fixed installed `notes-ledger` path with `add` (with `python3` or the configured Python). Helpers are granted only when installed. There are no general Python, script, shell, redirection or file-writing command grants. The model never gets `kaizen-backup undo` or `action`; the runner handles failed-change rollback after the cycle exits.

Auto mode uses `--permission-mode default`. In `-p` mode, unapproved tools are denied. `acceptEdits` is not used: it implicitly approves filesystem Bash commands, including inside config homes passed with `--add-dir`. In both modes, `--disallowedTools` denies git push, git commit, git reset, git clean, gh, rm, rmdir, mv, curl, wget, launchctl, crontab, brew, npm, pip, pip3, sudo, env, printenv, chmod, cp, touch, mkdir, sed, dd, install, ln, truncate, perl, `python3 -c`, python, grep, egrep, fgrep, rg, find, cat, strings, xxd, od and base64. Use Read, Grep and Glob for file access. The exact `python3 <helper> <subcommand>` grants still work. The runner never uses bypassPermissions. Every allowed helper re-checks its own paths. Edit/Write denies do not cover every Bash file command, which is why auto mode uses `default` mode and denies filesystem commands such as `cp`. Changes to settings, hooks and permissions are made interactively, where you see each edit.

Both Edit and Write are denied under the project's `**/.git/**` and each config home's `<home>/**/.git/**`, protecting config and hooks for future interactive git commands. Other auto-mode Edit and Write denies are, under each config home: `settings*.json`, `hooks/**`, `plugins/**`, `skills/**`, `commands/**`, `bin/**`, `**/*.json`, `**/*.toml`, `**/*.sh`, `**/*.py`, `**/*.js`, `.credentials*`, `auth.json` and `**/.git/**`; under the Claude home also `agents/**`; under the Codex home also `AGENTS.md`. They also cover the Claude user config file and, under the project: `.claude/settings*.json`, `.claude/hooks/**`, `.claude/agents/**`, `.claude/commands/**`, `.claude/skills/**`, `.mcp.json`, `.github/workflows/**` and `.husky/**`. Scheduled auto runs are therefore narrower than the scope described in autonomy.md. Absolute grants and denies include resolved and unresolved paths. Claude Code also protects `.claude` instruction files, including `CLAUDE.md` and `.claude/rules`, in `-p` mode. Unattended auto runs can edit only other files; instruction-file proposals go in the report for the owner. See [autonomy.md](autonomy.md#permissions).

Both scheduled modes deny Read, Edit and Write for the paths in `CREDENTIAL_PATHS` in `scripts/kaizen_credentials.py`, shared with `kaizen-backup`:

- At the top level of each Claude and Codex config home: `.credentials.json`, `auth.json`, `*token*.json` and `*secret*.json`.
- Under the user home: `.ssh/**`, `.aws/**`, `.gnupg/**`, `.netrc`, `.config/gh/**`, `.docker/config.json`, `.kube/config`, `.npmrc`, `.pypirc`, `.git-credentials`, `.config/gcloud/**`, `.azure/**`, `.config/op/**` and `.terraform.d/credentials.tfrc.json`.
- In the project, in any directory: `**/.env`, `**/.env.*` (also hides `.env.example`), `**/.npmrc`, `**/.envrc`, `**/*.pem`, `**/*.key`, `**/id_rsa*` and `**/id_ed25519*`.

Credential protection rests on having no network egress from scheduled tools: WebFetch and WebSearch are unavailable, curl and wget are denied, and strict MCP configuration excludes external tools. Scheduled runs skip model and release web checks; interactive runs keep them. Deny lists are a second layer, since readable secrets can escape Read denies through some Bash commands.

Backup trees deny Read, Edit and Write in resolved and unresolved forms. Use `kaizen-backup list` for metadata; `begin` checks credential patterns against both the given path and its resolved target before copying. A credential reached only through an ordinary-looking symlink can still be copied, but the copy is in the backup root, which the model cannot read, and scheduled runs have no network egress.

Credential denies include resolved and unresolved forms, plus targets of existing top-level token/secret JSON symlinks. Permission-rule metacharacters in path roots fail closed: a project, config home or backup root whose path contains any of `, ( ) * ? [ ] \` cannot be reviewed, and the project gets status `unsupported-path` with the reason in `last_error` in `state.json` and in `run.log`. In auto mode the script directory, the Python path and the helper paths are also checked, and a path with any of those characters, a quote, a backtick, `$ ; & | < >` or whitespace is rejected. A plugin or Python path containing a space therefore gets no auto runs, with a visible message. The independent test pins the credential list. To check actual CLI enforcement with the real login and a disposable project, run `KAIZEN_LIVE_PROBE=1 python3 -m unittest discover -s tests -p test_schedule_live_probe.py -v` outside a network-restricted sandbox. This opt-in probe needs Claude authentication and network access. It runs real `claude -p --model haiku --max-turns 4` calls with the generated auto flags, uses only new targets and a credential decoy, and cleans up in `finally`. It requires permission-denial records for protected reads, Bash `cp`, `cat`, `grep -r` and writes (including `.claude/*.md` and `.claude/rules/*.md`), checks WebFetch is unavailable, and confirms an ordinary project write succeeds. It also checks the newer project and Claude-home write denies, successful reads inside the project and Claude config dir, and denied reads outside the allowed roots. The Codex `AGENTS.md` write deny is skipped when the Codex home is missing or that file already exists.

After an auto cycle exits, including a non-zero exit, the runner finds backups whose `run_id` or `session_id` matches this cycle and whose `created_at` is after the cycle started. It calls `kaizen-backup undo <dir> --force` for each unfinished backup or one with `verification=failed`, newest first. `begin` records creation time and the runner's session id; `finish` records `verification=passed` by default, or accepts `--verification failed` to record a failed check. Finished, verified backups and other runs' backups are left alone. Each rollback appears in the cycle report and the project state records `rolled-back`, without advancing `reviewed_at`. If undo fails, the runner reports the error, marks the run failed, exits non-zero and keeps the backup directory for recovery.

Auto mode permits only `notes-ledger add`. It rejects an invalid raw `notesLedger` config before granting that rule. Ledger paths must point to regular files and be absolute after `~` expansion. Symlinked ledgers are rejected before launch. Relative paths are rejected by config validation and review. Edit and Write deny rules cover both each unresolved absolute path and its resolved target, including symlinked csv and timeline files. Paths containing permission-rule metacharacters fail closed.

The post-run ledger guard is an additional check on the scoped helper grants and file permission denies.

Before launching Claude in either auto or propose mode, the runner copies each configured ledger to a private run directory and records its size and sha256. The CSV is append-only: the guard checks its original byte prefix by hash, with growth limited to whole lines. The timeline must retain every old line in order, allowing `notes-ledger add` to insert rows through atomic replacement. This check does not prevent extra text from being inserted between old rows. Missing files, replacement symlinks (even to identical bytes), changed history or guard errors fail closed. The runner atomically restores damaged files from the original bytes held in memory, writes `ledger-violation` and the affected paths to the failed cycle report and project state, exits 1, and skips remaining projects and housekeeping. Before restoring, it saves the rejected file content beside the snapshot (`csv.rejected` or `timeline.rejected` in the kept `.ledger-*` folder) and names that path in the message. On-disk snapshots remain under the project's audits folder after a violation or failed rollback; successful runs remove them. Interrupted-run snapshots remain after recovery, and the `ledger-runs` retention kind removes kept snapshots after 7 days.

A ledger that cannot be snapshotted at the start (missing, unreadable or a symlink) is a different case, status `ledger-config-error`: no model run for that project, other projects continue, housekeeping still runs, and the exit code is 1. Only a real violation, where history changed during the run, skips the remaining projects and housekeeping. An unreadable or malformed global config also blocks scheduled reviews; a missing config keeps the defaults.

If `<csv>.lock` is a symlink, a FIFO or cannot be opened, the guard reports a violation (`ledger guard failed (cannot lock the ledger: ...)`) and does not restore.

The guard protects only ledger files. Auto-mode backup rollback covers unfinished or failed changes; other edits remain. The model process group is stopped before rollback, even if its leader has exited.

### Failure handling

The model run is stopped after `KAIZEN_REVIEW_TIMEOUT` seconds (default 3600; `0` = no limit); the project state is then `timed-out`. Other steps stop after 600 seconds. Every step the runner starts (model run, token audit, usage-db ingest, git, rollback) runs in its own session. On timeout or error the whole process group is killed, even if its leader has exited. SIGTERM, SIGHUP and SIGINT stop the model group, run rollback and the ledger check, skip housekeeping, and exit 143, 129 and 130 respectively.

Before each model run the runner creates `<backup-root>/.active-run.json` with exclusive, no-follow access and mode 0600. It records the run and session ids, mode and authenticated ledger snapshot metadata. An unresolved marker is never replaced; a later run uses `<backup-root>/.active-run.<32-lowercase-hex-uuid>.json`. Recovery also accepts older `.active-run-<hyphenated-uuid>.json` files. The scan accepts only these exact names and the primary name, and only regular files checked with `lstat`. It opens markers without following symlinks and requires mode 0600. Reviews also hold `<backup-root>/.lock`, reusing the audits lock if both folders are the same. A watchdog inherits the lock. If the runner dies, the watchdog stops the model process group before recovery can take the lock.

On the next review, recovery retries every protected marker, even with a different audits folder. It matches both run and session ids and undoes finished changes with failed verification only if their after hashes still match. It does not use `--force`. Unfinished changes have no verified after hash and require manual inspection and resolution. Recovery authenticates ledger snapshots before verifying the ledgers. Valid appends and timeline insertions remain; damaged history is restored only from authenticated snapshots. Rejected bytes and restoration copies are kept under `<backup-root>/.ledger-recovery-*/` when a violation is found.

Recovery removes the marker only after rollback and ledger verification or restoration succeed. A restored ledger is verified again. Normal cleanup follows the same rule; a verifier exception, failed restore or failed rollback retains the marker and snapshots. Marker deletion is the commit point, before disposable snapshots are deleted. A restored ledger violation makes every project propose-only for that cycle. An intact leftover snapshot alone does not. Unresolved recovery keeps the marker and makes every project propose-only on each retry. Housekeeping preserves snapshots referenced by unresolved protected markers; an unreadable marker protects all ledger snapshots. Normal retention resumes after removal.

The `recovery:` status reports the problem, a non-forced undo command when a matching backup exists, and a command to discard the recovery record after the owner resolves changes and ledger by hand if needed. Undo commands include custom `CLAUDE_CONFIG_DIR` and `KAIZEN_BACKUP_DIR` assignments when needed. Removal uses `rm --` for files and symlinks, or `rm -r --` for a legacy directory. The runner never executes this removal command. Unreadable protected markers and legacy audit-local markers are reported as `ledger-unverified`; audit-local markers cannot authorize rollback or ledger restoration. A failed ledger restore is left for a later retry.

`audit`, `review` and `housekeep` take `<audits>/.lock`. A second run prints `waiting up to <N> s for the run lock <audits>/.lock` once, waits up to `KAIZEN_LOCK_WAIT` seconds (default 1800), then logs `another run holds the lock <audits>/.lock; this run was skipped` and exits 0. Dry runs and `config` take no lock.

## 0.3.x migration

Re-run `install-schedule --apply` with `--review` if desired. Cron and launchd jobs are replaced in place under the same names. `--project-dir` no longer defaults to the current directory: without it, every enrolled project with activity is reviewed. Bare `--auto` still selects auto for one project, from `--project-dir` or the current directory. Old reports have no scope line and are not compared.

- **Auto mode is now a setting.** 0.3.x put `--auto` into the job command. The review now reads `scheduledAutonomy`, which defaults to `propose`. Re-running `install-schedule --apply --review` without `--auto` turns an auto install into propose-only. Add `--auto all` or `--auto DIR...` to keep auto.
- **Projects must be enrolled.** A `--project-dir DIR` is reviewed only if `DIR/docs/kaizen/` exists. Run `/agent-kaizen:start` there first.
- **Proposals moved.** `cycle-<yyyy-mm-dd>.md` is now written per project, in `audits/projects/<key>/`, not in `audits/`.
