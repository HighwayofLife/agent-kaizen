---
name: undo
description: "Reverse a change Agent Kaizen applied: the last one, a specific ledger row or backup, or the whole last run."
disable-model-invocation: true
argument-hint: "[last|run|<backup folder or ledger date>]"
---

# Undo an applied change

Every change applied in `safe` or `auto` mode has a backup folder under `~/.claude/kaizen-backups/` with a `manifest.json`, and a ledger row in `docs/kaizen/LEDGER.md` that points at it. See `${CLAUDE_PLUGIN_ROOT}/docs/autonomy.md`.

## Task

1. Find the target:
   - `last` (the default): the newest backup folder whose manifest has `reverted: null`;
   - `run`: every not-yet-reverted backup folder with the newest `run_id`, undone in reverse `change` order;
   - otherwise, the backup folder or ledger row I named.
2. Show what will be restored and removed. For each file in the manifest, show the original path, the backup path, and whether the file was changed or created. Undo is the reverse of a change I asked for, so go ahead without waiting unless something looks wrong:
   - **Conflict:** a file's current sha256 differs from the manifest's `after_sha256`, meaning it changed after the kaizen edit. Show the diff, then ask.
   - **Missing backup:** a backup file listed in the manifest doesn't exist. Stop and ask.
3. Restore the backed-up files. Delete a file the manifest lists as created only if its hash still matches `after_sha256`; otherwise ask. For each recorded action (for example a package install), show its `undo` command and ask before running it. Re-run the same verification the original change used (`jq` on settings, hook tests, `claude plugin validate`, frontmatter checks).
4. Set `"reverted": "<date>"` in each manifest and mark the ledger row(s) `reverted (<date>)`. Keep the backup folder; I delete backups myself.
5. Report what was restored, removed and verified, in at most 10 lines.
