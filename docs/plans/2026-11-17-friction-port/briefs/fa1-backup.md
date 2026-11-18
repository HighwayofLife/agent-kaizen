# FA1 Final-audit fixes: kaizen-backup

Fix-Origin: final-audit (0.13 range 2e0e643..6e63dba, Astra high, slice 1). Risk: high. Model: sol/high.
Sol reason: TOCTOU, durability (fsync ordering) and permission-restoring undo in the backup/undo transaction code.

## Goal
The read-only final audit of release 0.13 reported these findings. Line numbers refer to commit 6e63dba; the branch may have moved slightly (main 0.12.0 was merged in), so locate by content.

1. `scripts/kaizen-backup:1703` — MUST-FIX — `begin` resolves each input again after waiting for the lock and scanning Git. A symlink retargeted during that interval can put a credential file into the backup despite the earlier credential check.
1. `scripts/kaizen-backup:2008` — MUST-FIX — Ref-backed undo copies every permission bit from the backup, but verifies only the owner-execute bit. Changing a backup from `0600` to `0644` passes verification and makes the restored private file world-readable.
1. `scripts/kaizen-backup:2120` — MUST-FIX — During `undo run`, an editor save between restoring a shared path and taking this snapshot becomes the expected state. The next, older change can overwrite that save without `--force`.
1. `scripts/kaizen-backup:2029` — MUST-FIX — Renaming a committed backup folder makes its name-based journal lookup miss. Undo then restores the files and reports success while the Git ref still contains the change.
1. `scripts/kaizen-backup:1424` — MUST-FIX — Commit syncs the journal and publishes the ref without first syncing the finished manifest, backup copies, and their directory entries. A power loss can leave a durable commit whose required rollback material is missing.
1. `scripts/kaizen-backup:2017` — SHOULD-FIX — Replacing a hard-linked working file breaks the link. Undo reports success while another name for the original inode still exposes the edited bytes.
1. `scripts/kaizen-backup:1890` — SHOULD-FIX — Ref-backed undo requires the target’s parent directory to exist even with `--force`. Removing a nested directory after commit prevents undo from restoring its tracked file.

## Rules
- Audit severities are often inflated. For each item, first confirm or refute it against the code, with a failing test where practical (red first). Fix confirmed items at their cause. List refuted or not-reproducible items in the report with evidence; do not make speculative changes for them.
- MUST-FIX items take priority; do every confirmed item, SHOULD-FIX included, unless the fix would exceed ~400 changed lines in total — then fix all MUST-FIX items and list the remaining SHOULD-FIX items as deferred with a one-line reason.
- Supported hosts and platforms are in `docs/hosts.md`; do not add support for a platform the project does not claim (refute such items with the doc line).
- Never weaken, skip or delete an existing test. Keep the existing CLI, file formats and exit codes unless a finding requires a change.
- Stay inside the files this slice names plus their tests; if a fix truly needs another file, say so in the report instead of editing it.
- Do not touch `.claude-plugin/plugin.json`, `CHANGELOG.md` or the version. If a user would notice the fix, write a short changelog fragment to `docs/plans/2026-11-17-friction-port/changelog/FA1.md` (ID = this packet's id); otherwise none.
- Gated items G1–G10 in plan.md stay out of scope. Do not commit or push.
- Report: per item CONFIRMED+fixed / REFUTED (evidence) / DEFERRED (reason), files changed, checks run.

## Verify
- `python3 -m unittest discover -s tests -p 'test_backup_commit.py'`
- `python3 -m unittest discover -s tests -p 'test_kaizen_backup.py'`
- `python3 tools/context_budget.py`
- `git diff --check`
