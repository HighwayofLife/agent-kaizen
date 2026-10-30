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
2. **Per project:** `docs/kaizen/config.json` → `{"autonomy": "safe"}`.
3. **Globally:** `~/.claude/agent-kaizen.json` → `{"autonomy": "auto"}`.
4. **Default:** `propose`.

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
- **"The user hasn't confirmed I may edit this file."** In `auto`, every file under the project and `~/.claude/` (CLAUDE.md, imported docs, agents, skills, the `~/.claude/orchestrator/` docs) and `~/.codex/AGENTS.md` is in scope, apart from the hard stops (permissions, hooks being removed, secrets).
- **"It needs web access."** Web research (models, whats-new, roster research) is free and allowed. "Spending money" means buying a plan or paying for API calls, not reading docs.
- **"It's a big change."** Make a smaller version that you can verify, for example trimming one section of one file.

If a run ends with zero changes applied while low-risk proposals existed that weren't hard stops, the run failed its job. Apply at least the best one.

## Low-risk changes (`safe` applies these)

Reversible and local, with no effect on what agents are allowed to do:
- Creating `docs/kaizen/` files (ledger, baseline, model roster, reports) and git-ignore rules for audit reports.
- Shortening or deduplicating instruction files (CLAUDE.md, AGENTS.md, agent and skill descriptions), **as long as no rule is dropped**. Merged rules stay word-for-word in the diff.
- Adding a tools-before-tokens line, a code-map line or a topic-doc pointer to instructions.
- Adding one short, confirmed repo-fact line to a project's CLAUDE.md.
- Setting `disable-model-invocation: true` on your own user-triggered skills.
- Switching a single routing row to a model already in your roster, as a one-row trial.
- Writing new scripts under `tools/` or `~/.claude/bin/` (new files only; nothing existing is replaced).

`permissions.deny` rules for unused tools are proposed in `safe` and applied only in
`auto`. They are reversible and tighten permissions, but can remove a tool needed by a
rare workflow.

## Hard stops (always need a human, in every mode)

- Anything involving secrets: reading, printing, moving or storing keys and tokens, or `.env` files.
- Spending money or using a new vendor: new subscriptions or API plans, or sending repo code to a vendor that hasn't seen it (for example the roster bake-off).
- Loosening permissions: `bypassPermissions`, broad allow rules, or removing deny rules or safety hooks.
- Deleting things: transcripts, audits, backups, branches, or files Claude did not create in this run.
- Outward-facing actions: commits, pushes, PRs, publishing, messages.
- Installing packages, unless `allowInstalls` is true.
- Installing, changing or removing scheduled jobs (launchd, cron).
- Changing the autonomy setting itself (only `/agent-kaizen:autonomy`, run by you, does that).

## What every applied change gets, in every mode

No exceptions: this includes the scaffolding `/agent-kaizen:start` creates, one-line edits to files such as `.gitignore`, and new files. A change without a manifest can't be undone, so it isn't made.

Use the bundled script for the bookkeeping. Call `~/.claude/bin/kaizen-backup` if it exists, otherwise `${CLAUDE_PLUGIN_ROOT}/scripts/kaizen-backup`. Use one plain command per Bash call: no `cd`, no variables, no `;` or `&&` chains, absolute paths only. Permission rules match single commands. Write file contents with the Edit and Write tools, never with shell redirects.

1. **Backup first:** `kaizen-backup begin --skill <skill> --ledger "<ledger text>" <every file you will edit or create>`. Never list `docs/kaizen/LEDGER.md` itself: undo would restore it and erase the ledger row instead of marking it reverted. It copies the existing files, records the missing ones as created, and prints the change folder (`~/.claude/kaizen-backups/<run_id>-<NN>-<skill>/`, with `manifest.json`). Every change in one run shares a `run_id`: pass `--run <id>` from the first `begin`, or set `KAIZEN_RUN_ID`.
2. **Apply** the change with Edit or Write. Record any non-file action, such as a package install with `allowInstalls`, with `kaizen-backup action <change folder> --did "<cmd>" --undo "<reverse cmd>"`.
3. **Verify right away. No verification, no change:** if you can't run a change's verification (for example, the tool isn't permitted in this run), don't apply the change. List it as a proposal instead. Checks:
   - settings and other JSON parse with `jq`;
   - hooks pass their sample-input tests;
   - `claude plugin validate` or the project's checks pass where relevant;
   - agents and skills still have valid frontmatter.
4. **Finish or roll back:** if verification passes, run `kaizen-backup finish <change folder>`, which records the after-hashes undo uses to detect later edits. If it fails, run `kaizen-backup undo <change folder> --force`, report the failure, and skip the change.
5. **Ledger row** in `docs/kaizen/LEDGER.md`, with the backup folder, so `/agent-kaizen:undo` can reverse it.
6. **Summary at the end:** what was applied, what was skipped and why (hard stop, cap reached, missing permission), and what was rolled back.

## Permissions

The autonomy mode decides what the *skills* will do. Claude Code's own permission prompts still apply. To run without tool prompts:
- **Interactive:** use a permission mode that auto-accepts edits (`acceptEdits`, or auto mode if your plan has it) for the session. Some files, such as your settings, may still prompt; skills skip what they're not allowed to do and list it.
- **Scheduled:** `scripts/install-schedule --apply --auto` runs the weekly cycle in `auto` mode with `--permission-mode acceptEdits`. It uses:
  - `--tools`, which limits the available tools to Read, Grep, Glob, Edit, Write, WebFetch, WebSearch and Bash;
  - `--allowedTools`, which pre-approves Bash only for `jq`, `cp`, `mkdir`, `diff`, `shasum` and token-audit;
  - `--disallowedTools`, which denies git commit and push, `rm`, `mv`, curl, package managers, `launchctl`, crontab, `sudo` and `env`, even if your own settings allow them;
  - `--strict-mcp-config`, so no MCP servers load.

  It never uses `bypassPermissions`. Your settings' other allow rules still apply, so keep them narrow. `acceptEdits` covers files in the project. Claude Code treats files under `~/.claude/` (your global CLAUDE.md, agents, settings, even `.reviewed` markers) as sensitive, and refuses to edit them in an unattended run. Those changes are rolled back if they were started, and listed as "do interactively". Run `/agent-kaizen:cycle yolo` in a normal session to apply them, approving the prompts for `~/.claude` files there.

## Undo

- `/agent-kaizen:undo last` reverses the most recent applied change.
- `/agent-kaizen:undo <ledger row date or backup folder>` reverses a specific one.
- `/agent-kaizen:undo run` reverses everything from the last run.

`/agent-kaizen:undo` runs `kaizen-backup undo`. That command skips changes already reverted, and treats a file whose hash differs from the recorded after-hash as a conflict (nothing is restored without `--force`). It restores backups, deletes created files that are unchanged, and prints recorded actions' reverse commands without running them. The skill then marks the ledger row.
