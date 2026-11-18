# BF16 P24 review residuals (two Medium findings)

- **Risk** — normal. Lands on green checks and is reviewed with the next batch.
- **Fix-Origin** — batch-review (P24 final Sol high review, 2026-11-18). Fixes: P24.
- **Changelog** — none (internal hardening of unreleased code).
- **Depends on** — P25 landed (both touch `scripts/kaizen-scheduled`).

## Goal

Fix two Medium findings left by P24's final security review. Both are live in a proposal-only 0.13.0. Fix both, and give each a regression test that fails before the fix.

1. **`scripts/token-audit`, around the signed regression baseline (≈ line 2814 at 755874b).** The audit signs timing comparisons built partly from transcripts that its safe-open check rejected. Externally writable transcript data can then become an authenticated baseline and skew later regression proposals. Fix: comparisons only include rows from transcripts that passed the safe-open check. If any input to the comparison cohorts was rejected, the audit writes no regression MAC; an unsigned report is already skipped as a baseline. Test: a rejected transcript is present, so no `token-audit-friction-mac` line is written and the next run uses no baseline from it.
2. **`scripts/kaizen-scheduled`, interrupted-run recovery (≈ line 2406 at 755874b).** In a degraded proposal-only review, an error while recovering an interrupted run skips the cleanup of recordless legacy receipts. That unrelated error leaves those suggestions pending and blocks manual dismissal or completion. Fix: make the recordless legacy receipt cleanup independent of interrupted-run recovery. It needs no native effect and runs under proposal-review checks even when recovery fails. The recovery error itself still surfaces and still fails closed for native effects. Test: interrupted-run recovery raises, and a recordless legacy `linux-localsearch` receipt still becomes a terminal suggestion with no marker written.

3. **`scripts/kaizen-backup`, interactive undo metadata check (≈ line 1935 at d8d9fc3; P25 residual).** Undo refuses when restoring would drop macOS xattrs, but it does not check extended ACLs. Replacing the file can silently drop a deny ACL entry and widen access. Fix: on macOS, treat a non-empty extended ACL on the live target that the backup cannot reproduce like the xattr case: refuse with a clear message and leave the file and the Git ref untouched. Read the ACL without new dependencies (for example `ls -le`/`os.listxattr` of `com.apple.acl.text` is not reliable; prefer parsing `/bin/ls -lde`, or `acl_get_file` via `ctypes` if simpler); when the check cannot run, refuse. Test: patch the ACL probe to report an entry, then check that undo refuses and both the file and the ref stay unchanged. Add one real-ACL test (using `chmod +a`), skipped off macOS.
4. **`scripts/kaizen-backup`, undo of files the commit created (≈ line 2036 at d8d9fc3; P25 residual).** Undo skips the inode/file-flag checks for files the commit created. If such a file is immutable, the unlink fails only after the inverse Git ref has already been published, which leaves the worktree and the ref out of sync. Fix: run the same flag check (macOS `st_flags`, Linux `FS_IOC_GETFLAGS` as P25 added) on every created file before the inverse ref is published, and refuse the whole undo if any check fails. Test: with the flag probe patched to report immutable on a created file, undo refuses, the ref is unchanged and no files are removed.

## Scope

Owned files: `scripts/token-audit`, `scripts/kaizen-scheduled`, `tests/test_friction_timeline.py`, `tests/test_friction_review.py`, `tests/test_friction_prepare.py`, `scripts/kaizen-backup`, `tests/test_backup_commit.py`, `tests/test_kaizen_backup.py`. Do not touch the gated items recorded as G1–G10 in `plan.md`. Do not weaken or delete tests. Do not commit or push. Do not edit `.claude-plugin/plugin.json` or `CHANGELOG.md`. No changelog fragment is needed.

## Verification

- `python3 -m unittest discover -s tests -p 'test_friction_timeline.py'`
- `python3 -m unittest discover -s tests -p 'test_friction_review.py'`
- `python3 -m unittest discover -s tests -p 'test_friction_prepare.py'`
- `python3 -m unittest discover -s tests -p 'test_token_audit_fixes.py'`
- `python3 -m unittest discover -s tests -p 'test_backup_commit.py'`
- `python3 -m unittest discover -s tests -p 'test_kaizen_backup.py'`
- `git diff --check`
