# P18c allow-rule security residuals

Risk: high (security review before landing). Model: sol / high.
Sol reason: Evidence authentication, settings write atomicity and ownership-checked undo decide whether a persistent Claude permission grant can be forged, lost or wrongly removed.
Depends on: P18b (landed). Blocks: P24 (the packet that enables broker writes).
Changelog: `docs/plans/2026-11-17-friction-port/changelog/P18c.md`, one line, only if a fix changes visible proposal output; otherwise do not create it.

## Goal

P18b made exact allow-rule grants recoverable while keeping the installed CLI proposal-only behind gate S2. Its Sol high security review found eight defects. Fix ALL eight, each with a regression test that fails before the fix. Writes stay gated behind S2 and the installed CLI stays proposal-only; do not open the gate. Do not commit or push. Do not edit `.claude-plugin/plugin.json` or `CHANGELOG.md`. Do not delete or weaken tests.

Owned files: `scripts/allow-rule`, `scripts/kaizen-scheduled`, `scripts/token-audit`, `tests/test_allow_rule.py`, `tests/test_runner.py`, `tests/test_friction_signals.py`, `tests/test_schedule_security.py`.

## Findings (from the review of `f0d5558`; line numbers approximate)

1. `scripts/allow-rule:89`: grant authorization trusts unsigned counters from extract files whose ownership and parent directories are unchecked, so anyone who can write to an extract store can fabricate approvals. Fix: open extracts with the same safe pattern `token-audit` uses for samples (dir-fd walk, `O_NOFOLLOW`, file and every ancestor owned by root or euid, no group/other write without sticky bit, store dir mode 0700, `S_ISREG` on the fd). Reject and warn otherwise. If the extract writer can bind a keyed digest the way P18b binds transaction records, do so; otherwise document why ownership checks suffice.
2. `scripts/allow-rule:288`: settings and staged bytes can change between verification and `replace`/`unlink`. A concurrent save can lose user settings, and a staged-file swap can publish unverified permissions. Fix: hold the staged file by fd and write and verify through the fd; just before `replace`, re-stat the target and compare identity, size, mtime_ns and content digest with what was verified, refusing on mismatch; verify the staged file by fd identity (not by name) immediately before rename. Add a test that mutates settings between verify and replace and asserts a refusal with user bytes intact.
3. `scripts/allow-rule:446`: undo checks file identity and rule count, so an in-place revoke and re-add looks tool-owned and undo can remove a user-added rule or delete a tool-created settings file the user has since edited. Fix: record the exact rule entry and a digest of the full settings content after the tool's write; undo removes only that exact entry, and deletes the file only when its content digest still equals the tool's post-write digest. Otherwise remove just the entry or refuse with a reason. Tests: a revoke-then-re-add by the user survives undo; a user-edited tool-created file is not deleted.
4. `scripts/allow-rule:313`: broker IDs are checked for format and bound on first use without verifying their authenticated scope. Fix: an ID binds to the authenticated (canonical project, literal rule, scope) tuple from prepared evidence; a mismatched or unknown binding is refused and does not block reconciliation of other IDs. Test: an ID issued for another project/rule is refused.
5. `scripts/kaizen-scheduled:843`: an unenrolled nested checkout can pass the common-dir check with a copied `.git` pointer. Fix: require the checkout to appear in the enrolled project's `git worktree list --porcelain` (or be its main worktree) with matching gitdir back-pointer (`<common>/worktrees/<name>/gitdir` points at the checkout's `.git`). A copied pointer fails. Test it.
6. `scripts/allow-rule:475`: an interrupted add whose settings or evidence later changed has no cancellation path; the pending record blocks other transactions, including undo of earlier grants. Fix: on recovery, if evidence or settings no longer match the pending record, roll back to a recorded cancelled state (removing only the tool's own staged bytes) so later transactions and undos proceed. Expired pending grants (past their evidence window) cancel the same way. Test both.
7. `scripts/kaizen-scheduled:636`: scheduled discovery inherits Git tracing configuration, so ownership probes can append private paths to an external trace file. Fix: run every git subprocess in scheduled discovery with the same scrubbed env P18b uses proposal-side (unset `GIT_TRACE*`, `GIT_TRACE2*`, `GIT_CONFIG_*` injection, `GIT_DIR`/`GIT_WORK_TREE` overrides; pass `-c trace2.eventTarget= -c trace2.normalTarget= -c trace2.perfTarget=` or equivalent). Share one helper rather than duplicating it. Test with `GIT_TRACE=<tmpfile>` and `GIT_TRACE2_EVENT=<tmpfile>` set, asserting the files stay empty.
8. `scripts/token-audit:1480`: future-dated Codex context still changes cwd attribution, which can turn an unscoped tool pair into scoped friction evidence. Fix: ignore Codex turn-context and cwd records dated after the audit's `now` the same way future-dated Claude events are ignored. Test in `tests/test_friction_signals.py` or the Codex friction tests.

Also close the two residuals P18b reported itself: editors outside the project lock racing the final replacement (covered by item 2's re-stat and digest), and expired pending grants (item 6).

## Verification

- `python3 -m unittest discover -s tests -p 'test_allow_rule.py'`
- `python3 -m unittest discover -s tests -p 'test_friction_signals.py'`
- `python3 -m unittest discover -s tests -p 'test_schedule_security.py'`
- `python3 -m unittest discover -s tests -p 'test_runner.py'`
- `python3 -m unittest discover -s tests -p 'test_friction_codex.py'`
- `python3 tests/bench_token_audit.py --baseline d8a4cb7 --max-ratio 1.10`
- `git diff --check`; `tools/ci-local --python 3.9` (report which failures are sandbox-only: `ps`, lock writes)

## Report

Each finding: fixed or not, and its test name. Files changed with line counts. Check results. Anything still needing S2 live verification.
