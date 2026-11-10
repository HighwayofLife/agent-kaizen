# Autonomy modes

By default every skill proposes changes and waits for your OK. If you trust the loop, let it apply changes itself.

| Mode | What the skills do |
|---|---|
| `propose` (default) | Show every change as a diff and wait for your OK |
| `safe` | Apply **low-risk** changes on their own (list below). Everything else becomes a proposal |
| `auto` (alias: `yolo`) | Apply every change except the **hard stops** below, which always need a human |

## Setting the mode

Highest precedence first:
1. **Per run:** pass it as the skill argument: `/agent-kaizen:cycle yolo`, `/agent-kaizen:trim-context safe`, `/agent-kaizen:review propose`.
2. **Per project:** `docs/kaizen/config.json` → `{"autonomy": "safe"}`. For scheduled runs, `scheduledAutonomy: auto` in a project file only counts when the project is in the global `autoProjects` list. `kaizen-scheduled config set --for DIR scheduledAutonomy=auto` writes both.
3. **Globally:** `agent-kaizen.json` in your Claude config dir (`$CLAUDE_CONFIG_DIR` or `~/.claude`) → `{"autonomy": "auto"}`.
4. **Default:** `propose`.

Scheduled runs use `scheduledAutonomy`, separate from interactive `autonomy`. Project settings override global settings; the default is `propose`. A tracked `docs/kaizen/config.json` applies to teammates too, so personal choices belong in the global file. `kaizen-scheduled config set` writes settings; `/agent-kaizen:schedule` and `/agent-kaizen:start` write `scheduledAutonomy` only from your answers, as does `install-schedule --auto` from its arguments.

`/agent-kaizen:autonomy [propose|safe|auto]` shows or sets the mode for you. `propose-only` (used by the scheduled review) always wins and never changes anything.

Optional settings in the same file:
```json
{ "autonomy": "auto", "maxChangesPerRun": 3, "allowInstalls": false }
```
- `maxChangesPerRun` (default 3) keeps each run's effect measurable: the next audit can only attribute a change in the numbers if few things changed at once.
- `allowInstalls` (default false) lets `auto` install CLI tools such as rg, fd and jq with your package manager.

## In `auto`, these are NOT reasons to skip a change

The person chose `auto` so they wouldn't be asked. Don't invent extra conditions:
- **"No measured saving yet."** Measuring comes after the change; that's what the ledger and the next audit are for. A reasoned expected effect is enough.
- **"The user hasn't confirmed I may edit this file."** In `auto`, every file under the project and the Claude config dir (CLAUDE.md, imported docs, agents, skills, the `orchestrator/` docs) and `AGENTS.md` in the Codex home is in scope, apart from the hard stops (permissions, hooks being removed, secrets). Scheduled auto runs cannot edit `.claude` instruction files, including CLAUDE.md and `.claude/rules`: Claude Code protects them in `-p` mode. They edit only other files and report instruction-file proposals for the owner (see Permissions). Scheduled auto runs are narrower in other ways too. They also cannot edit these project paths: `.claude/settings*.json`, `.claude/hooks/`, `.claude/agents/`, `.claude/commands/`, `.claude/skills/`, `.mcp.json`, `.github/workflows/` and `.husky/`; in the Claude config dir, settings, hooks, plugins, skills, commands, `bin/` and `agents/`; in the Codex home, `AGENTS.md` and its config files; or common credential files. [docs/scheduling.md](scheduling.md) has the full lists.
- **"It needs web access."** Interactive web research (models, whats-new, roster research) is free and allowed. Scheduled runs have no network egress and skip model and release web checks. "Spending money" means buying a plan or paying for API calls, not reading docs.
- **"It's a big change."** Make a smaller version that you can verify, for example trimming one section of one file.

If a run ends with zero changes applied while low-risk proposals existed that weren't hard stops, the run failed its job. Apply at least the best one.

## Low-risk changes (`safe` applies these)

Reversible and local, with no effect on what agents are allowed to do:
- Creating `docs/kaizen/` files (ledger, baseline, model roster, reports) and git-ignore rules for audit reports.
- Shortening or deduplicating instruction files (CLAUDE.md, AGENTS.md, agent and skill descriptions), **as long as no rule is dropped**. Merged rules stay word-for-word in the diff.
- Adding a tools-before-tokens line, a code-map line or a topic-doc pointer to instructions.
- Adding one short, confirmed repo-fact line to a project's CLAUDE.md.
- Editing Markdown instruction files under the Claude and Codex homes (CLAUDE.md, agents/*.md, rules/**/*.md, memory MEMORY.md files, Codex AGENTS.md), interactively; unattended auto runs report `.claude` instruction-file proposals for the owner; settings, hooks, plugins, skills, commands, bin, credentials and every .json, .toml, .sh, .py and .js file under the homes stay denied in scheduled runs.
- Setting `disable-model-invocation: true` on your own user-triggered skills.
- Switching a single routing row to a model already in your roster, as a one-row trial.
- Writing new scripts under `tools/` or `<Claude config dir>/bin/` (new files only; nothing existing is replaced).

`permissions.deny` rules for unused tools are proposed in `safe` and applied only in
`auto`. They are reversible and tighten permissions, but can remove a tool needed by a
rare workflow.

## Hard stops (always need a human, in every mode)

- Anything involving secrets: reading, printing, moving or storing keys and tokens, or `.env` files.
- Spending money or using a new vendor: new subscriptions or API plans, or sending repo code to a vendor that hasn't seen it (for example the roster bake-off).
- Loosening permissions: `bypassPermissions`, broad allow rules, or removing deny rules or safety hooks.
- Deleting things: transcripts, backups, branches, build caches in active worktrees, or files kaizen did not create. Exceptions: the plugin's own generated data under <audits> (deleted on the retention schedule in every mode; see the retention and retentionOverrides settings in scheduling.md); files kaizen created in an earlier run, through `kaizen-backup undo`.
- Outward-facing actions: commits, pushes, PRs, publishing, messages.
- Installing packages, unless `allowInstalls` is true.
- Installing, changing or removing scheduled jobs (launchd, cron).
- Changing the interactive `autonomy` setting itself (only `/agent-kaizen:autonomy`, run by you, does that).

## What every applied change gets, in every mode

No exceptions: this includes the scaffolding `/agent-kaizen:start` creates, one-line edits to files such as `.gitignore`, and new files. A change without a manifest can't be undone, so it isn't made.

Use the bundled script for the bookkeeping. Call `<Claude config dir>/bin/kaizen-backup` if it exists, otherwise `${CLAUDE_PLUGIN_ROOT}/scripts/kaizen-backup`. Use one plain command per Bash call: no `cd`, no variables, no `;` or `&&` chains, absolute paths only. Permission rules match single commands. Write file contents with the Edit and Write tools, never with shell redirects.

1. **Backup first:** `kaizen-backup begin --skill <skill> --ledger "<ledger text>" <every file you will edit or create>`. Never list `docs/kaizen/LEDGER.md` itself: undo would restore it and erase the ledger row instead of marking it reverted. It copies the existing files, records the missing ones as created, and prints the change folder (`<backup root>/<run_id>-<NN>-<skill>/`, with `manifest.json`; the backup root is `KAIZEN_BACKUP_DIR`, or `kaizen-backups/` under the Claude config dir). Every change in one run shares a `run_id`: pass `--run <id>` from the first `begin`, or set `KAIZEN_RUN_ID`.
2. **Apply** the change with Edit or Write. Record any non-file action, such as a package install with `allowInstalls`, with `kaizen-backup action <change folder> --did "<cmd>" --undo "<reverse cmd>"`.
3. **Verify right away. No verification, no change:** if you can't run a change's verification (for example, the tool isn't permitted in this run), don't apply the change. List it as a proposal instead. Checks:
   - settings and other JSON parse with `jq`;
   - hooks pass their sample-input tests;
   - `claude plugin validate` or the project's checks pass where relevant;
   - agents and skills still have valid frontmatter.
4. **Finish or roll back:** if verification passes, run `kaizen-backup finish <change folder>`, which records the after-hashes undo uses to detect later edits. If it fails interactively, run `kaizen-backup undo <change folder> --force`, report the failure, and skip the change. In scheduled auto runs, leave the backup unfinished (or record `finish <change folder> --verification failed`) and report the failed check. The runner performs forced rollback after the cycle exits; the model never gets `undo` or `action`.
5. **Ledger row** in `docs/kaizen/LEDGER.md`, with the backup folder, so `/agent-kaizen:undo` can reverse it.
6. **Summary at the end:** what was applied, what was skipped and why (hard stop, cap reached, missing permission), and what was rolled back.

## Permissions

The autonomy mode decides what the *skills* will do. Claude Code's own permission prompts still apply. To run without tool prompts:
- **Interactive:** use a permission mode that auto-accepts edits (`acceptEdits`, or auto mode if your plan has it) for the session. Some files, such as your settings, may still prompt; skills skip what they're not allowed to do and list it.
- **Scheduled:** `install-schedule --auto all|none|DIR...` sets `scheduledAutonomy` globally or for selected projects. The `kaizen-scheduled` runner uses `dontAsk` in propose mode and `default` in auto mode, with explicit Edit/Write grants under the project and config homes. Both restrict available and allowed tools; propose mode grants no Bash commands (use Read, Grep and Glob); auto mode adds scoped Edit/Write and the exact `kaizen-backup begin|finish|list` and `notes-ledger add` helpers. Both modes also deny hard-stop commands and bulk Bash readers such as `grep`, `rg`, `find` and `cat`; use Read, Grep and Glob. It passes `--disallowedTools` deny rules using `Edit(//<abs>/...)` and `Write(//<abs>/...)` for both config homes: settings*.json, hooks, plugins, skills, commands, bin, `.credentials*`, `auth.json`, and every `.json`, `.toml`, `.sh`, `.py` and `.js` under them. It also denies edits to the Claude user config file and the project's `.claude/settings*.json`. Claude Code protects `.claude` instruction files (CLAUDE.md and `.claude/rules`) in `-p` mode. Auto changes are limited to other files; instruction-file proposals go in the report for the owner. Both modes deny Read/Edit/Write to the credential paths and backup trees, and use `--strict-mcp-config`. Credential protection rests on no network egress from scheduled tools: WebFetch and WebSearch are unavailable, and curl and wget are denied. The path and command deny lists are a second layer. The project `**/.env.*` rule also hides `.env.example`. `kaizen-backup begin` refuses credential paths; use `kaizen-backup list` for backup metadata. See [scheduled permissions](scheduling.md#unattended-permissions) for the exact lists.

  Edit/Write denies do not cover every Bash file command. Scheduled auto runs therefore use default permission mode and explicitly deny filesystem commands such as `cp`, rather than relying on `acceptEdits`. Every allowed helper re-checks its own paths. It never uses `bypassPermissions`. Changes to settings, hooks and permissions are still made interactively, where you see each edit.

## Undo

- `/agent-kaizen:undo last` reverses the most recent applied change.
- `/agent-kaizen:undo <change folder>` reverses a specific one.
- `/agent-kaizen:undo run` reverses everything from the last run.

After `kaizen-link --replace`, first run `kaizen-link --unlink --restore-replaced`, then `kaizen-backup undo <dir>`. Undo through a symlink writes into plugin sources; the backup command refuses such restores even with `--force`.

`/agent-kaizen:undo` runs `kaizen-backup undo`. That command skips changes already reverted, and treats a file whose hash differs from the recorded after-hash as a conflict (nothing is restored without `--force`). Undoing an unfinished change that created a file reports a conflict (`was created by <change>, which was never finished`, exit 2) unless `--force` is given. It restores backups, deletes created files that are unchanged, and prints recorded actions' reverse commands without running them. The skill then marks the ledger row.
