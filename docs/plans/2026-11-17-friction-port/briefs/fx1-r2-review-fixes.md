# FX1 r2: review findings on round 1

Risk: high. Model: sol / high.
Sol reason: second round on race, recovery and upgrade-compatibility code after a Sol review found gaps in round 1.

Round 1 (brief `fx1-backup.md` in this directory, committed as HEAD) was reviewed. Fix every finding below. Read `fx1-backup.md` first: its Rules section applies unchanged (red test first, no deferral, never weaken tests, keep user data recoverable, old/new compatibility, Python 3.9, no commit, no version/CHANGELOG change).

Priority: a finding marked as a regression versus the release candidate (HEAD~1) or as breaking `518da76`/`v0.12.0` state must be fixed outright, by fixing or by restoring HEAD~1 behaviour for that path. For residual races that no portable primitive can close, narrow the window and make the operation detect the conflict and keep the user's data (recoverable copy, reported, non-zero exit); say exactly what remains in the report as PARTIAL.

## Findings
- `scripts/kaizen-backup:2341` — Cleanup can discard a late editor save — an editor writing through an open descriptor after the displaced file’s final hash check loses the save when undo unlinks the recovery copy and exits successfully. The new test writes before the exchange.
- `scripts/kaizen-backup:1116` — A corrupt legacy journal can still lose its renamed backup — changing one inode digit leaves the name-based filename valid. After the original name is reused, undo can restore files without reversing the Git ref, and prune can delete the rollback copies. The new test covers malformed JSON and filename mismatches.
- `scripts/kaizen-backup:2449` — Undo can silently delete a concurrent save to a run-created file — a save between the snapshot and `unlink()` disappears, then the absence check passes and the manifest is marked reverted.
- `scripts/kaizen-backup:2298` — Ordinary undo regresses for untracked hard links — backing up just one name now makes undo fail where the release candidate restored both names through the shared inode. Earlier files in the same undo may already have been restored.
- `scripts/kaizen-backup:2275` — Ordinary undo now requires write access to the parent directory — a writable file in a searchable `0555` directory could be restored by the release candidate, but staging now fails with `EACCES`.
- `scripts/kaizen-backup:1173` — Undo of `518da76` state can silently change permissions — if the live file was deleted, forced undo restores a legacy `0644` backup as `0600`, breaking access for other users. This also affects `HEAD~1`.

Report per finding: FIXED (test name) or PARTIAL (what remains, how it is detected and recovered).
