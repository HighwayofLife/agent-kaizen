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

The first installs the audit; the second adds the weekly review. `--apply` copies the runner, token-audit, kaizen-backup and pricing data into the Claude config directory's `bin/`, so jobs survive plugin updates. Re-run it after an update. Use `--model` and `--max-turns` to override the review defaults (Sonnet and 40 turns).

## Discovery and activity

Enrolled projects have a `docs/kaizen/` directory. Discovery reads the newest five Claude Code transcripts in each project folder (of any age), Codex sessions from the last 30 days, and a registry of previously seen projects. A session in a subfolder maps to its enrolled project. Linked git worktrees of a repository count as one project. Repeat `--project-dir DIR` to replace discovery with selected projects.

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
| `autonomy` | Global or project | Interactive mode; scheduled runs do not read it |

Global `enabled=false` takes precedence over everything. Otherwise, project settings override global settings, which override defaults. A tracked project config applies to teammates too; put personal choices in the global file.

Use `kaizen-scheduled config set [--for DIR] KEY=VALUE...` to merge settings. `/agent-kaizen:schedule` and `/agent-kaizen:start` ask for your choices and run the relevant commands.

`install-schedule --auto` implies `--review`. `--auto all` sets global scheduled auto mode; `--auto none` sets global propose mode; `--auto DIR...` opts specific projects into auto. Bare `--auto` opts in the one project selected by `--project-dir`, or the current directory.

## Reports and storage

The audits directory is `<Claude config dir>/audits`:

```text
<audits>/token-audit-*.md
<audits>/projects/index.json
<audits>/projects/<key>/state.json
<audits>/projects/<key>/token-audit-*.md
<audits>/projects/<key>/cycle-<date>.md
<audits>/run.log
```

Reports carry a scope line and compare only with an earlier report of the same scope. Flags use per-call intensity, not volume. Reports from before 0.4.0 lack scope metadata and are never compared.

## Schedulers and environment

macOS uses launchd, with a 72-hour audit interval (`StartInterval` 259200). Linux uses cron when available (`0 9 */3 * *`), or systemd user timers when cron is unavailable (`OnCalendar=*-*-01/3 09:00:00`). Cron and systemd run on days 1, 4, 7, and so on at 09:00; the gap across month end can be shorter than three days. Systemd uses `Persistent=true` to catch up missed runs. Its timers run while logged out only after `loginctl enable-linger <user>`; with `--apply`, the installer prints this hint when lingering is off, but does not run it. Windows is unsupported: run the scripts by hand or use Task Scheduler.

The installer captures `PATH` and, when set, `CLAUDE_CONFIG_DIR` and `CODEX_HOME`, and sets them inside each job. The Claude config directory defaults to `~/.claude`; Codex home defaults to `~/.codex`.

## Unattended permissions

The runner uses `--strict-mcp-config` and limits `--tools` to Read, Grep, Glob, WebFetch, WebSearch and Bash in propose mode. `--allowedTools` permits restricted read-only Bash: ls, wc, head, tail, rg, git status, git diff, git log, shasum, sha256sum and jq. It uses `--permission-mode dontAsk`.

Auto mode adds Edit and Write, and permits cp, mkdir, diff, touch, cd, token-audit and kaizen-backup in addition to those read-only commands. It uses `--permission-mode acceptEdits` and `--disallowedTools` denies git push, git commit, git reset, git clean, gh, rm, rmdir, mv, curl, wget, launchctl, crontab, brew, npm, pip, pip3, sudo, env, printenv and chmod. It never uses bypassPermissions. Changes to your Claude or Codex configuration are best applied interactively, where you see each edit. See [autonomy.md](autonomy.md#permissions).

## 0.3.x migration

Re-run `install-schedule --apply` with `--review` if desired. Cron and launchd jobs are replaced in place under the same names. `--project-dir` no longer defaults to the current directory: without it, every enrolled project with activity is reviewed. Bare `--auto` still selects auto for one project, from `--project-dir` or the current directory. Old reports have no scope line and are not compared.

- **Auto mode is now a setting.** 0.3.x put `--auto` into the job command. The review now reads `scheduledAutonomy`, which defaults to `propose`. Re-running `install-schedule --apply --review` without `--auto` turns an auto install into propose-only. Add `--auto all` or `--auto DIR...` to keep auto.
- **Projects must be enrolled.** A `--project-dir DIR` is reviewed only if `DIR/docs/kaizen/` exists. Run `/agent-kaizen:start` there first.
- **Proposals moved.** `cycle-<yyyy-mm-dd>.md` is now written per project, in `audits/projects/<key>/`, not in `audits/`.
