# P18d allow-rule review residuals

Risk: high (security review before landing). Model: sol / high.
Sol reason: Evidence provenance, publication atomicity and recovery/cancellation state decide whether a persistent Claude permission grant can be forged, lost, stranded or wrongly blocked.
Depends on: P18c (landed, 54d563e). Blocks: P24 (enables broker writes). Items 7 and 8 affect live, unreleased proposal/audit paths and must land before P27.
Changelog: `docs/plans/2026-11-17-friction-port/changelog/P18d.md`, one line, only if a fix changes visible proposal or audit output; otherwise do not create it.

## Goal

P18c's Sol high security review (of 2400117..3f91e70) found eight defects. Fix ALL eight, each with a regression test that fails before the fix. Writes stay gated behind S2 and the installed CLI stays proposal-only; do not open the gate. Do not commit or push. Do not edit `.claude-plugin/plugin.json` or `CHANGELOG.md`. Do not delete or weaken tests.

Owned files: `scripts/allow-rule`, `scripts/token-audit`, `tests/test_allow_rule.py`, `tests/test_friction_signals.py`, `tests/test_friction_codex.py`, `tests/test_runner.py`.

## Findings (line numbers approximate)

1. `scripts/token-audit:2567`: approval counters are signed from Claude transcripts without checking the transcripts' ownership, write permissions or symlinks, so fabricated transcript rows become authenticated evidence once S2 opens. Fix: before counting a transcript toward signed allow-rule evidence, open it with the same safe pattern used for samples and extracts (dir-fd walk, `O_NOFOLLOW`, `S_ISREG` on the fd, file and ancestors owned by root or euid, no group/other write without sticky bit). Unsafe transcripts may still feed the ordinary audit but contribute nothing to signed evidence; record a reason count. Test: a group-writable or symlinked transcript yields no signed counter.
2. `scripts/allow-rule:398`: publication still unlinks/renames by pathname after the final check, so a concurrent save can be lost and a staged-file swap can publish unverified permissions before post-write verification notices. Fix: publish through the pinned directory fd (`os.replace(src, dst, src_dir_fd=, dst_dir_fd=)` on the held `.claude` dir fd), re-verify the staged file by fd identity (dev/ino) against the name immediately before the rename, and after rename confirm the target's identity equals the staged fd; on mismatch restore from the recorded preimage and refuse. Where an exact atomic compare-and-swap is impossible on the platform, document the residual window in a comment and the report. Tests: staged-file swap before rename is refused with no unverified rule published; settings mutated between final check and rename keep the user's bytes.
3. `scripts/allow-rule:609`: recovery cancels a grant when publication succeeded but an editor changed the file before the journal was finalized, leaving the permission installed with no usable managed undo record. Fix: on recovery, if the tool's exact entry is present in the current settings, finalize as applied (recording current digest and the exact entry) so undo can remove just that entry; cancel only when the entry is absent. Test.
4. `scripts/allow-rule:614`: an interrupted undo whose settings changed has no cancellation path; retrying refuses the changed preimage and the pending undo blocks every other transaction for the project. Fix: on recovery, if the tool's exact entry is already gone, finalize the undo as done; if it is present but the preimage changed, remove only that exact entry (as committed undo does) or record a cancelled-undo state that unblocks the project while keeping the grant record as applied. Never leave a pending undo blocking. Test both branches.
5. `scripts/allow-rule:536`: cancelling a grant after `.claude` was replaced retains the old directory identity, so later transactions stay blocked even when the project never had an applied grant. Fix: on cancel/reconcile, rebind (or drop) the recorded directory identity when no applied grant depends on it; a replaced directory with applied grants refuses with a reason but does not block unrelated new proposals. Test.
6. `scripts/allow-rule:630`: a cancelled broker ID permanently blocks the only ID accepted for that (project, rule, scope), so fresh authenticated evidence cannot restart the grant. Fix: derive the broker ID from the authenticated tuple plus the evidence generation (or allow a cancelled ID to be superseded by a new generation with newer evidence); a replayed old generation stays refused. Test: cancel, then fresh evidence produces an accepted new ID; replay of the cancelled one is refused.
7. `scripts/token-audit:2545` (live): `mkdir(..., exist_ok=True)` leaves pre-upgrade extract directories at their old mode, so a `0755` store loses proposals even after a fresh audit because the reader requires `0700`. Fix: after mkdir, open the dir with `O_NOFOLLOW|O_DIRECTORY`, verify owner is euid and it is not a symlink, then `fchmod` to 0700; if owner differs, warn and skip writing. Test: a pre-existing 0755 store becomes 0700 and proposals appear after one audit.
8. `scripts/token-audit:1707` (live): a future-dated Codex session header rejects the entire scoped rollout, dropping valid later tool pairs whose cwd is established independently by in-window turn context. Fix: a future-dated header contributes no cwd, but does not reject the rollout; later in-window turn-context cwd still scopes pairs. Test in `tests/test_friction_codex.py`.

## Verification

- `python3 -m unittest discover -s tests -p 'test_allow_rule.py'`
- `python3 -m unittest discover -s tests -p 'test_friction_signals.py'`
- `python3 -m unittest discover -s tests -p 'test_friction_codex.py'`
- `python3 -m unittest discover -s tests -p 'test_schedule_security.py'`
- `python3 -m unittest discover -s tests -p 'test_runner.py'`
- `python3 -m unittest discover -s tests -p 'test_friction_samples.py'`
- `python3 tests/bench_token_audit.py --baseline d8a4cb7 --max-ratio 1.10`
- `git diff --check`; `tools/ci-local --python 3.9` (report which failures are sandbox-only: `ps`, lock writes)

## Report

Each finding: fixed or not, and its test name. Files changed with line counts. Check results. Any residual atomicity window that needs S2 live verification.
