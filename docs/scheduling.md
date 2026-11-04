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

The first installs the audit; the second adds the weekly review. `--apply` prints a plan, then installs managed scripts through `kaizen-link --mode auto --replace-prefixed` into the Claude config directory's `bin/`. Source checkouts use links; plugin cache installs use copies so jobs survive plugin moves. Differing `kaizen-` files are saved as `.replaced-<date>`; differing generic files are reported as DRIFT and left alone. The installer passes both `--bin` and `--hooks-dir` explicitly, so a custom bin never writes hooks into the default config home. Re-run it after an update. Use `--model` and `--max-turns` to override the review defaults (Sonnet and 40 turns).

The installer records its source root in `bin/.kaizen-plugin-root`. The Drift check passes `--plugin-root` to `kaizen-link`, using `CLAUDE_PLUGIN_ROOT` when set, otherwise that record. If neither is known, Drift reports `unavailable` with a reason. If the source has moved, set `CLAUDE_PLUGIN_ROOT` or re-run the installer from its new location.

### Install through links

`kaizen-link` installs managed scripts and hooks as links, or as copies when the plugin is in a cache. Run `kaizen-link --check` to report drift; list intentional differences in `localScripts`. `--apply --replace` saves differing files with a `.replaced-<date>` suffix before replacement.

### Rollback after link replacement

Run these in order after `kaizen-link --replace`:

1. `kaizen-link --unlink --restore-replaced`
2. `kaizen-backup undo <dir>`

Unlink first: undo through a symlink writes into plugin sources. The backup command refuses restores through symlinks into the plugin root, including with `--force`. Keep the backup directory if rollback fails and resolve the link before retrying.

## Discovery and activity

Enrolled projects have a `docs/kaizen/` directory. Discovery reads the newest five Claude Code transcripts in each project folder (of any age), Codex sessions from the last 30 days, and a registry of previously seen projects. A session in a subfolder maps to its enrolled project. Linked git worktrees of a repository count as one project. Reports, checks and cycles run once in the enrolled canonical repository, even when only a worktree was discovered or selected. Worktree sessions still count as activity. Repeat `--project-dir DIR` to replace discovery with selected projects.

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
| `scheduledAutonomy` | Global or project | `propose` (default), `auto` |
| `retention` | Global only | `auto` (default), `off` keeps everything |
| `retentionOverrides` | Global only | Object, default `{}`; for example `{"extracts":{"days":14}}` |
| `projectCommands` | Global only | Object mapping absolute project paths (or `~/` paths) to `outcomeLog` relative paths and `shadowStatus`, `slowTests`, or `speedReport` argv lists; default `{}` |
| `notesLedger` | Global only | Object with `csv` path, optional `timeline` path and positive integer `measureAfterDays`; paths must be absolute after `~` expansion; default `{}` (off) |
| `calibrationLadder` | Global only | List of `model` or `model effort` strings; default `["haiku", "sonnet medium", "sonnet high", "opus high"]` |
| `rulesLintFiles` | Global only | List of non-empty glob strings; default `[]` |
| `localScripts` | Global only | List of non-empty strings without `/`; default `[]` |
| `autonomy` | Global or project | Interactive mode; scheduled runs do not read it |

Global `enabled=false` takes precedence over everything. Otherwise, project settings override global settings, which override defaults. Project values for global-only keys are ignored with a warning. A tracked project config applies to teammates too; put personal choices in the global file.

Use `kaizen-scheduled config set [--for DIR] KEY=VALUE...` to merge settings. `/agent-kaizen:schedule` and `/agent-kaizen:start` ask for your choices and run the relevant commands.

`install-schedule --auto` implies `--review`. `--auto all` sets global scheduled auto mode; `--auto none` sets global propose mode; `--auto DIR...` opts specific projects into auto. Bare `--auto` opts in the one project selected by `--project-dir`, or the current directory.

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
<audits>/projects/<key>/cycle-<date>.md
<audits>/run.log
```

Reports carry a scope line and compare only with an earlier report of the same scope. Flags use per-call intensity, not volume. Reports from before 0.4.0 lack scope metadata and are never compared.

Each report has a machine-local JSON extract with per-agent usage and a cheaper-model hint. Extracts go in `<audits>/extracts/`, for scheduled and interactive runs alike. They never go into `docs/kaizen/`.

### Retention

The runner tidies after each scheduled audit and review; interactive cycles run it at the end. `kaizen-scheduled housekeep --dry-run` previews deletions. Use `--audits DIR` to select an audits folder.

| Kind | Files | Default |
|---|---|---|
| `extracts` | `extracts/*.extract.json`, `projects/*/*.extract.json`, `projects/*/host-probe-*.json`, `projects/*/friction-inputs-*.json` | 30 days; 200 MB cap |
| `markers` | `projects/*/cycle-*.failed.md`, `*.noticed-*`, `projects/*/*.noticed-*` | 30 days |
| `reports` | `token-audit-*.md`, `projects/*/token-audit-*.md`, `projects/*/cycle-*.md`, `checks-*.md`, `projects/*/project-report-*.md` | 365 days; newest 5 per folder and family kept |

A report's `.reviewed` marker is removed with it. Only regular files inside the audits folder are deleted; symlinks are skipped. Each deletion is logged: in `run.log` for scheduled runs, on screen for manual ones. Housekeeping does not touch `host-actions.json`, `host-fixes/`, `projects/index.json`, project `state.json` files, `run.log`, `kaizen-backups/`, transcripts, Codex sessions or project files.

Set `retention=off` to keep everything. Override a kind with `kaizen-scheduled config set retentionOverrides='{"extracts":{"days":14}}'`. Each kind accepts positive integer `days`, `hours` and `maxMB`; `hours` takes precedence over `days`.

## Schedulers and environment

macOS uses launchd, with a 72-hour audit interval (`StartInterval` 259200). Linux uses cron when available (`0 9 */3 * *`), or systemd user timers when cron is unavailable (`OnCalendar=*-*-01/3 09:00:00`). Cron and systemd run on days 1, 4, 7, and so on at 09:00; the gap across month end can be shorter than three days. Systemd uses `Persistent=true` to catch up missed runs. Its timers run while logged out only after `loginctl enable-linger <user>`; with `--apply`, the installer prints this hint when lingering is off, but does not run it. Windows is unsupported: run the scripts by hand or use Task Scheduler.

The installer captures `PATH` and, when set, `CLAUDE_CONFIG_DIR` and `CODEX_HOME`, and sets them inside each job. The Claude config directory defaults to `~/.claude`; Codex home defaults to `~/.codex`.

## Unattended permissions

The runner uses `--strict-mcp-config` and limits `--tools` to Read, Grep, Glob, WebFetch, WebSearch and Bash in propose mode. `--allowedTools` permits ls, wc, head, tail, rg, git status, shasum, sha256sum and jq. The cycle and review steps do not need git log or git diff, so neither is allowed. It uses `--permission-mode dontAsk`.

Auto mode adds Edit and Write, and permits mkdir, diff, cd, token-audit and only `kaizen-backup begin`, `finish` and `list` in addition to those commands. The model never gets `kaizen-backup undo` or `action`; the runner handles failed-change rollback after the cycle exits. It uses `--permission-mode acceptEdits` and `--disallowedTools` denies git push, git commit, git reset, git clean, gh, rm, rmdir, mv, curl, wget, launchctl, crontab, brew, npm, pip, pip3, sudo, env, printenv and chmod. It never uses bypassPermissions. Deny rules protect settings, hooks, plugins, skills, commands, bin, credentials and all `.json`, `.toml`, `.sh`, `.py` and `.js` files under both config homes, the Claude user config file, and the project’s `.claude/settings*.json`. Markdown instruction files, including `CLAUDE.md`, `agents/*.md`, rules, memory `MEMORY.md` and Codex `AGENTS.md`, remain editable. These rules cover Edit, Write and recognised file commands such as cat, sed, tee and redirects; they do not cover `cp` or scripts. See [autonomy.md](autonomy.md#permissions).

After an auto cycle exits, including a non-zero exit, the runner finds backups whose `run_id` or `session_id` matches this cycle and whose `created_at` is after the cycle started. It calls `kaizen-backup undo <dir> --force` for each unfinished backup or one with `verification=failed`, newest first. `begin` records creation time and the runner's session id; `finish` records `verification=passed` by default, or accepts `--verification failed` to record a failed check. Finished, verified backups and other runs' backups are left alone. Each rollback appears in the cycle report and the project state records `rolled-back`, without advancing `reviewed_at`. If undo fails, the runner reports the error, marks the run failed, exits non-zero and keeps the backup directory for recovery.

Auto mode permits only `notes-ledger add`. It rejects an invalid raw `notesLedger` config before granting that rule. Ledger paths must point to regular files and be absolute after `~` expansion. Symlinked ledgers are rejected before launch. Relative paths are rejected by config validation and review. Edit and Write deny rules cover both each unresolved absolute path and its resolved target, including symlinked csv and timeline files. Paths containing permission-rule metacharacters fail closed.

Bash commands can write files; the ledger is protected by the post-run guard, not by permission rules.

Before launching Claude in either auto or propose mode, the runner copies each configured ledger to a private run directory and records its size and sha256. The CSV is append-only: the guard checks its original byte prefix by hash, with growth limited to whole lines. The timeline must retain every old line in order, allowing `notes-ledger add` to insert rows through atomic replacement. This check does not prevent extra text from being inserted between old rows. Missing files, replacement symlinks (even to identical bytes), changed history or guard errors fail closed. The runner atomically restores damaged files from the original bytes held in memory, writes `ledger-violation` and the affected paths to the failed cycle report and project state, exits non-zero, and skips remaining projects and housekeeping. On-disk snapshots remain under the project's audits folder after a violation as debugging aids; successful runs remove them. An unreadable configured ledger prevents Claude from launching. An unreadable or malformed global config also blocks scheduled reviews; a missing config keeps the defaults. The guard protects only ledger files. Auto-mode backup rollback covers unfinished or failed changes; other edits remain. Background processes started by the run are not stopped.

## 0.3.x migration

Re-run `install-schedule --apply` with `--review` if desired. Cron and launchd jobs are replaced in place under the same names. `--project-dir` no longer defaults to the current directory: without it, every enrolled project with activity is reviewed. Bare `--auto` still selects auto for one project, from `--project-dir` or the current directory. Old reports have no scope line and are not compared.

- **Auto mode is now a setting.** 0.3.x put `--auto` into the job command. The review now reads `scheduledAutonomy`, which defaults to `propose`. Re-running `install-schedule --apply --review` without `--auto` turns an auto install into propose-only. Add `--auto all` or `--auto DIR...` to keep auto.
- **Projects must be enrolled.** A `--project-dir DIR` is reviewed only if `DIR/docs/kaizen/` exists. Run `/agent-kaizen:start` there first.
- **Proposals moved.** `cycle-<yyyy-mm-dd>.md` is now written per project, in `audits/projects/<key>/`, not in `audits/`.
