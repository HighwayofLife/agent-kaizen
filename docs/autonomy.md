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

## Low-risk changes (`safe` applies these)

Reversible and local, with no effect on what agents are allowed to do:
- Creating `docs/kaizen/` files (ledger, baseline, model roster, reports) and git-ignore rules for audit reports.
- Shortening or deduplicating instruction files (CLAUDE.md, AGENTS.md, agent and skill descriptions), **as long as no rule is dropped**. Merged rules stay word-for-word in the diff.
- Adding a tools-before-tokens line, a code-map line or a topic-doc pointer to instructions.
- Setting `disable-model-invocation: true` on your own user-triggered skills.
- Switching a single routing row to a model already in your roster, as a one-row trial.
- Writing new scripts under `tools/` or `~/.claude/bin/` (new files only; nothing existing is replaced).

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

1. **Backup first.** Copy the original files to `~/.claude/kaizen-backups/<run_id>-<NN>-<skill>/`. `run_id` is the run's start time (`yyyymmdd-HHMMSS`), shared by every change in the run, and `NN` numbers the change within the run. Write a `manifest.json` there:
   ```json
   {"run_id": "20261029-101500", "change": 1, "skill": "trim-context", "ledger": "2026-10-29 deny unused MCP servers",
    "files": [{"path": "/abs/path", "backup": "files/1", "created": false, "after_sha256": "<filled after applying>"}],
    "actions": [{"did": "brew install fd", "undo": "brew uninstall fd"}],
    "reverted": null}
   ```
2. **Apply** the change, then record each file's `after_sha256` (`shasum -a 256`) in the manifest. Undo uses it to tell its own edits from later ones. Anything that isn't a file edit (a package install with `allowInstalls`) goes in `actions`, with its reverse command.
3. **Verify right away. No verification, no change:** if you can't run a change's verification (for example, the tool isn't permitted in this run), don't apply the change. List it as a proposal instead. Checks:
   - settings and other JSON parse with `jq`;
   - hooks pass their sample-input tests;
   - `claude plugin validate` or the project's checks pass where relevant;
   - agents and skills still have valid frontmatter.
4. **Roll back automatically** if verification fails. The failure is reported, and the change is skipped.
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

  It never uses `bypassPermissions`. Your settings' other allow rules still apply, so keep them narrow. `acceptEdits` covers files in the project. Edits elsewhere (for example `~/.claude/settings.json`) may be refused in a headless run; those changes are skipped and listed.

## Undo

- `/agent-kaizen:undo last` reverses the most recent applied change.
- `/agent-kaizen:undo <ledger row date or backup folder>` reverses a specific one.
- `/agent-kaizen:undo run` reverses everything from the last run.

Undo skips changes whose manifest already has `reverted` set. It treats a file whose current hash differs from `after_sha256` as a conflict and asks. It restores backed-up files, removes created files whose hash still matches, offers the reverse command for each recorded action (an uninstall is a deletion, so it asks), and then sets `reverted` in the manifest and marks the ledger row.
