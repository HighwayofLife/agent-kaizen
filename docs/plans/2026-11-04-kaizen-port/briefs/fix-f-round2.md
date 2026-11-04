# fix-f round 2: close the rollback privilege escalation (risk high, Sol high)

Read `fix-f-final-audit-scheduler.md` first; this file is its delta. Your commit at HEAD (rebased) implemented runner-side rollback. The review returned REVISE with a reproduced exploit:

- The model is allowed `kaizen-backup begin`. It can back up a protected file, e.g. `~/.claude/settings.json`, and then Edit or Write the extensionless copy `<backup>/files/1`. No deny glob covers that copy. The runner's `undo --force` then copies the crafted bytes over the protected file.
- Ownership is decided from manifest fields (`run_id`, `session_id`, `created_at`) that the model can influence.

Owner decision, unchanged: the model's allow list does not grow and the model never gets undo or action. The runner rollback stays, but it must not give the model any write it lacks today. Required design:

1. **Tamper-proof backups during unattended runs.** The runner pins `KAIZEN_BACKUP_DIR` to its resolved backup root for the cycle subprocess. In auto mode it adds Edit/Write deny rules covering everything under that root, in both resolved and unresolved forms, like the ledger deny rules. Add a test asserting that the generated deny list covers `<root>/**`. Add a test asserting that no allowed Bash rule names a tool that writes files: the auto allow list stays `notes-ledger add` and `kaizen-backup begin|finish|list`, and the read-only REVIEW_TOOLS stay read-only.
2. **Runner-held ownership.** Before launching, the runner records the set of existing backup dirs, by resolved path and inode. After the run, only dirs that did not exist before are candidates for rollback. Manifest `run_id`/`session_id`/`created_at` may only narrow that set further, never widen it.
3. **Validate entries before any restore or delete** (`scripts/kaizen-backup` around l.68-90 and l.146-153):
   - Entry `path` must be absolute, normalised, and free of `..`.
   - Entry `backup` must resolve inside its own backup dir.
   - Refuse to write, restore or unlink when any component of the target path, the final one or any parent, is a symlink. This applies to `created` entries too.
   - On refusal, that change is not rolled back. The run is marked failed and the reason is reported. Never fall back to writing through the symlink.
4. **Fault isolation.** `undo <dir>` must not parse every historical manifest first. A malformed unrelated manifest must not block rolling back this run's dir.
5. **Ledger check covers parents** (`kaizen-scheduled` around l.704). Compare each ledger file's resolved path with the resolved path recorded at snapshot, and also reject a final symlink. A parent directory swapped for a symlink must be detected, restored or reported as `ledger-violation`.

Tests, each failing without its fix:
- the reviewer's exploit: begin on a protected file, edit `files/1`, leave the backup unfinished. The runner must not restore crafted bytes, and the deny list must block the edit;
- a forged manifest in a pre-existing dir is ignored;
- `created` entry through a symlinked parent;
- `..` and relative paths;
- one malformed old manifest;
- ledger parent symlink.

Do not commit, and do not bump versions. Verify: `python3 -m unittest discover -s tests`, `./scripts/rules-lint --repo .`, `git diff --check`.
