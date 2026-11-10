---
name: undo
description: "Reverse a change Agent Kaizen applied: the last one, a specific change folder, or the whole last run."
disable-model-invocation: true
argument-hint: "[last|run|<change folder>]"
---

# Undo an applied change

Every change applied in `safe` or `auto` mode has a backup folder under `KAIZEN_BACKUP_DIR`, or `kaizen-backups/` in the Claude config dir, with a `manifest.json`, and a ledger row in `docs/kaizen/LEDGER.md` that points at it. See `${CLAUDE_PLUGIN_ROOT}/docs/autonomy.md`.

## Task

Use the script, not hand-copying: `<Claude config dir>/bin/kaizen-backup` if it exists, otherwise `${CLAUDE_PLUGIN_ROOT}/scripts/kaizen-backup`. Use one plain command per Bash call.

1. Run `kaizen-backup list` and show me the target:
   - `last` (the default): the newest change that hasn't been reverted;
   - `run`: every open change in the newest run;
   - otherwise the change folder I named.
2. Run `kaizen-backup undo <target>`.
   - If it prints `CONFLICT`, a file changed after the kaizen edit, or the change never finished and a file it was going to create now exists (`<path> was created by <change>, which was never finished`; exit 2). Show me the file and a diff against the backup copy in the change folder, then ask before re-running with `--force`.
   - It never runs the recorded actions' reverse commands; it only prints them. Ask me before running any of them, because an uninstall is a deletion.
3. Re-run the verification the change used (`jq` on settings, hook tests, `claude plugin validate`, frontmatter checks).
4. Mark the ledger row(s) `reverted (<date>)` with Edit. Keep the backup folders; I delete backups myself.
5. Report what was restored, removed and verified, in at most 10 lines.
