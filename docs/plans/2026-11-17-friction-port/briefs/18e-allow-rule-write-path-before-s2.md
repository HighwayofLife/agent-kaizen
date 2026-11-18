# P18e allow-rule write path, before S2 opens

Risk: high (security review before landing). Model: sol / high.
Sol reason: Publication rollback and crash recovery decide whether unverified or user-owned permissions are left live, deleted or leaked.
Depends on: P18d (landed). Blocks: opening gate S2 (exact `Bash(<literal>)` matching). Does NOT block P24 or the 0.13.0 release: the installed CLI stays proposal-only and every write path stays behind S2.
Changelog: none (no visible change while S2 is closed).

## Why this is separate

Three Sol high reviews of the write path (P18b, P18c, P18d) each found new rollback/recovery defects. 0.13.0 ships allow-rule as proposal-only. Run this packet only when the owner decides to open S2, and verify on macOS and Linux (the native atomic-exchange branch for Linux is unverified). If this round also finds new write-path defects, stop and escalate the publication design to `fable-architect` (owner OK needed for Fable) rather than another patch round.

## Findings (P18d review of 92a517a..0fd977e; line numbers approximate)

1. `scripts/allow-rule:699`: recovery skips rollback when the live inode differs from the recorded stage, so a crash after a last-instant swap can leave unverified permissions active after the journal cancels the grant.
2. `scripts/token-audit:1953`: an unsafe symlink can claim the canonical transcript path before safe-open, so a genuine denial is skipped and ten approvals can qualify for a signed grant. Signed evidence must be computed only when every transcript for the (project, literal) is accepted; any rejected candidate path blocks signing for that literal.
3. `scripts/allow-rule:456`: rollback can exchange away an editor save made after publication but before the first post-rename check, putting the newest user bytes at a staging name while stale settings become live.
4. `scripts/allow-rule:745`: recovery claims an exact rule the user added while the transaction was still staged, so managed undo can delete a permission the tool never installed.
5. `scripts/allow-rule:746`: an editor's atomic save before the receipt can leave the displaced preimage at `settings.kaizen-*.json` after recovery, keeping old settings (and any secrets) in an unexpected file.

Fix ALL five with a regression test each that fails before the fix. Prefer a simpler publication protocol (for example, refuse to publish unless the settings file is unchanged under an exclusive advisory lock held across stage, verify and rename, and never roll back over bytes the tool did not write) over more recovery branches.

Owned files: `scripts/allow-rule`, `scripts/token-audit`, `tests/test_allow_rule.py`, `tests/test_friction_signals.py`.

## Verification

- `python3 -m unittest discover -s tests -p 'test_allow_rule.py'`
- `python3 -m unittest discover -s tests -p 'test_friction_signals.py'`
- `python3 -m unittest discover -s tests -p 'test_runner.py'`
- Linux run of `test_allow_rule.py` (container or CI) before S2 opens.
- `git diff --check`

Do not commit or push. Do not edit `.claude-plugin/plugin.json` or `CHANGELOG.md`. Do not delete or weaken tests.

## Delta after P24b (second follow-up Sol high review, 0fefbc1..e6fd048; both GATED)

6. `scripts/kaizen_friction_apply.py` (displaced-ledger store, ~line 398 at e6fd048): displaced ledger copies are stored inside the checkout, where scheduled auto reviews keep project-wide write access, so a later review can overwrite the only copy of a displaced editor save. Fix: keep displaced copies outside every path a scheduled model run can write (for example under the private kaizen state directory next to the receipts), recorded by absolute path in the receipt, and test that a scheduled review's write scope cannot reach them.
7. `scripts/kaizen_friction_apply.py` (~line 451 at e6fd048): a crash after saving `apply-pending` but before starting the native grant leaves a reservation reconciliation cannot clear; once the audit generation changes, the old transaction key is rejected and fresh evidence cannot start a new attempt. Fix: reconciliation cancels a pending reservation whose native effect never started (proved by the native journal having no record of that transaction), without weakening P18d's replay refusal, so fresh signed evidence can start a new attempt. Test both with crash injection.
