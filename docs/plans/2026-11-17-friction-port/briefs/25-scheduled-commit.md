# P25 Permit verified local kaizen commits after a successful scheduled review

## Goal

Permit verified local kaizen commits after a successful scheduled review. This packet is part of the Agent Kaizen friction port for 0.13.0.

- **Agent / model / effort** — `codex-dispatch` (`codex-engineer` fallback), sol, high.
- **Risk** — high. Get a per-packet verifier and Sol high review before merge. Obtain security review before landing.
- **Group / dependencies** — M. After P16b, P24.
- **Size target** — ~385 changed lines including focused tests.
Sol reason: Brokered commits must bind trusted pre-review Git state to current-run backups.
- Changelog: Permit verified local kaizen commits after a successful scheduled review.

## Context

`scripts/kaizen-scheduled:1650–1876,1877–2085` captures run identity and owns rollback, guard verification and outcomes. `scripts/kaizen-backup:157–203,303–390` plus P08/P16 validates opt-in clean baseline, finish hashes and local refs. P24 provides the post-review broker and `maxChangesPerRun` accounting.

Use the 0.12.0 integration base for landing. The references above are from 0.11.0 main at d8a4cb7. Read `AGENTS.md` and `CLAUDE.md`. Locate symbols with `tools/codemap` if available, otherwise `rg -n` and narrow `sed` ranges. All runtime changes support Python 3.9 and stdlib only. Use `python3`. Keep hard stops, captured user changes, zero-token collection and public-repo privacy; keep real logs and fixtures private.

## Scope and archive references

Owned files: `scripts/kaizen-scheduled`, `scripts/kaizen_friction_apply.py`, `tests/test_friction_apply.py`, `tests/test_backup_commit.py`. Record the changelog line in `docs/plans/2026-11-17-friction-port/changelog/P25.md`. Keep the scoped diff and tests within the assigned cap. Changes outside these paths need a separate packet or a revised scope.

Read `git show wt/p15:scripts/kaizen-backup` at `git_start`, `check_run`, `commit` and the p15b manifest tests in `git show wt/p15:tests/test_backup_commit.py`. Reuse the existing validated backup commit procedure, not an expanded Bash allow rule. Inspect archive paths with `git show` and keep the current branch.

## Implementation and acceptance

The v1 `ledger_attestation` in the scheduled-baseline JSON is null (no ledger exception) or an exact object: `v` integer 1; `run_id`, `session_id` strings; `ledger_relpath` string exactly `docs/kaizen/LEDGER.md`; `before_b64` base64 of bounded pre-launch bytes; `before_sha256`, `after_sha256` lowercase 64-hex SHA-256 strings; `manifest_ids` array of distinct nonempty strings. Reject duplicate/unknown fields, invalid types, encoding or bounds. P24a derives this from protected runner state, P25 passes it unchanged on fixed private stdin, and P16 rechecks matching IDs, canonical non-symlink scope, unstaged-only status, both hashes against decoded pre-launch and live bytes, unchanged byte prefix, valid appended rows and exact independently verified finished current-run manifests. Reject mismatches; the ledger is excluded from the commit. Hashes alone do not authenticate the source.

1. Before Claude starts, use P08 to capture clean canonical root/common-dir/HEAD and index identity in protected runner state, along with generated run and session IDs, start time and pre-existing backup folders. Model inherits the existing run/session environment only. When friction gate is already open, permit one reserved per-run local-commit candidate ID (private selector is runner run ID); the model requests only that ID. The private fixed `local-commit` tag is code-only, separate from the public host catalogue.
2. After child exit, healthy guards and P24a accounting, select exactly one new verified mutation-bearing file manifest from that run, made by ordinary `begin` and `finish` without `--repo`. Revalidate bounded file/hashes, no stale, unrelated or conflicting manifest/HEAD/root/index, and one available shared budget slot. Pass P16 the v1 JSON tuple on stdin of fixed `kaizen-backup commit --scheduled-baseline-stdin CHANGE_DIR`, with the timed, validated current-run folder as the sole operand. Handle the project ledger bookkeeping exception using only P24a’s independently verified before/after evidence and exclude it from the commit. Refuse no manifest or ambiguous groups; file backups and ordinary review remain usable.
Use the ledger attestation defined in [Approach and contracts](../plan.md#approach-and-contracts), under Shared mutation quota and trusted Git baseline: pass P24a’s proof unchanged in the private stdin tuple. Consume the P16-owned `tests/fixtures/ledger_attestation_v1.json` unchanged and test valid, missing, forged and mismatched proofs end to end.
3. After recovery of older journals, process the new commit request before other new effects in that review. Journal and reserve before the ref effect, verify finished commit, then use the action-ID ledger/ack path. Recover an interrupted ref CAS or ledger write without duplicate commit, with no new selection authority from an old report or run. Test ordinary scheduled backup with inherited IDs all the way to ref and interactive undo. Include forged opt-in stamp, wrong run/session/pre-launch folders, no backup, dirty baseline, changed HEAD/index, insufficient budget, timeout and no writes on propose-only.
4. Obtain security review before landing.

## Verification

- `python3 -m unittest discover -s tests -p 'test_friction_apply.py'`
- `python3 -m unittest discover -s tests -p 'test_runner.py'`
- `python3 -m unittest discover -s tests -p 'test_schedule_security.py'`
- `python3 -m unittest discover -s tests -p 'test_schedule_robustness.py'`
- `python3 -m unittest discover -s tests -p 'test_backup_commit.py'`
- `python3 scripts/kaizen-backup commit --help`
- `tools/ci-local --python 3.9`

## Report

Report changed files and line counts, exact checks and outcomes, known uncertainty and any blocked verification. Label measurements with baseline/conditions. Redact paths and identifiers from shared output. Leave plugin version and release CHANGELOG to P27. Do not commit or push.

## Delta (P16b residuals, 2026-11-18)

P16b landed after three Sol high rounds. Carry into this packet, which extends the same commit/undo code in `scripts/kaizen-backup`:
1. Ref-backed undo restores require the target's parent directory to exist and can drop filesystem flags or extended attributes. Refuse a restore when the backup recorded xattrs/flags that cannot be reapplied, or reapply them, with a test; a missing parent stays a clear refusal.
2. Accepted same-UID residuals, do not reopen: a symlink planted under `refs/` that resolves into `refs/kaizen/`, a concurrent move of the undo target's directory during the descriptor-bound copy, and the final POSIX rename race after the fd-bound recheck.
3. Scheduled commits must reuse P16b's journal, pins and Git re-trust path; do not add a second recovery mechanism.

## Delta (after P24 landed, 2026-11-18)

1. P24 landed after five Sol high rounds (merge 755874b). Reuse its broker mechanisms and do not add parallel ones: the reservation, native journal and per-action cancellation; receipt binding and terminal-suggestion downgrade; the policy stamp built from config identity and digest; and `scheduled_action_refusal`.
2. S7 stays closed in 0.13.0. `scheduled_marker_refusal()` refuses broker effects because there is no verified stream version, so a scheduled commit must also be refused, or downgraded to a proposal, through the same gate. Build and test the commit path with the gate opened in tests via `patch`, as P24's tests do. In the shipped code a scheduled run never commits while S7 is closed. Add a test for that too.
3. The P16b delta item 1 changes `scripts/kaizen-backup`, so the owned files add `scripts/kaizen-backup` and `tests/test_kaizen_backup.py`.
4. The gated items G1–G8 in `plan.md` are out of scope. Line references in this brief may be stale; find code with `rg`.
