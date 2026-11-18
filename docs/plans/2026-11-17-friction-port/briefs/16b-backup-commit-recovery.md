# P16b Harden local commit and inverse-ref recovery

## Goal

Harden local commit and inverse-ref recovery. This packet is part of the Agent Kaizen friction port for 0.13.0.

- **Agent / model / effort** — `codex-dispatch` (`codex-engineer` fallback), sol, high.
- **Risk** — high. Get a per-packet verifier and Sol high review before merge. Obtain security review before landing.
- **Group / dependencies** — F. After P16.
- **Size target** — ~390 changed lines including focused tests.
Sol reason: Ref compare-and-swap and interrupted reversal must recover without duplicate commits.
- Changelog: Harden local commit and inverse-ref recovery.

## Context

`scripts/kaizen-backup:49–155,157–203,217–247,303–390` has current manifest, after hashes, targets and undo preflight. P08 records an opt-in clean git start. `scripts/kaizen-scheduled:1650–1705` still uses file-only undo in recovery. Scheduled commit access belongs to a later broker.

Use the 0.12.0 integration base for landing. The references above are from 0.11.0 main at d8a4cb7. Read `AGENTS.md` and `CLAUDE.md`. Locate symbols with `tools/codemap` if available, otherwise `rg -n` and narrow `sed` ranges. All runtime changes support Python 3.9 and stdlib only. Use `python3`. Keep hard stops, captured user changes, zero-token collection and public-repo privacy; keep real logs and fixtures private.

## Scope and archive references

Owned files: `scripts/kaizen-backup`, `tests/test_backup_commit.py`. Record the changelog line in `docs/plans/2026-11-17-friction-port/changelog/P16b.md`. Keep the scoped diff and tests within the assigned cap. Changes outside these paths need a separate packet or a revised scope.

Read `git show wt/p15:scripts/kaizen-backup` at `checked_root`, `tree_from_files`, `write_commit`, `check_run`, `commit`, `checked_revert`, `revert_commit` and the focused tests in `git show wt/p15:tests/test_backup_commit.py`. Keep p15b checks and replace unsafe filters, trust and partial-failure paths. Inspect archive paths with `git show` and keep the current branch.

## Implementation and acceptance

1. Finish durable pending and completed identities around ref CAS for both commit and inverse operations. Verify original commit, trailer, tree and ref relationships. Revert by deriving an inverse tree from Git objects, preserve nonoverlapping later changes, and reject overlaps, moved/unowned/checked-out refs or forged manifests. Never stage the user's index or switch branches.
2. Inject failures before/after pending write, after ref CAS, before record completion, during inverse CAS, and when ref moves. Retries reconcile verified same-run refs without duplicate commit or revert. Existing file undo and failed scheduled-run recovery remain compatible. Keep write entry points dark until recovery works.
3. Accept the runner’s private action-ID transaction key only through its fixed internal invocation. Bind it to tool-owned state so P24 can reconcile after the effect, and refuse a conflicting key/scope without changes. Preserve direct interactive record/undo behavior.
4. Obtain security review before landing. Reference `wt/p15` changes 291 source + 756 test lines. Keep narrowly targeted fixtures shared with P08/P16, grouping equivalent refusals to fit the budgets.


## Verification

- `python3 -m unittest discover -s tests -p 'test_backup_commit.py'`
- `python3 -m unittest discover -s tests -p 'test_kaizen_backup.py'`
- `python3 -m unittest discover -s tests -p 'test_schedule_security.py'`
- `python3 scripts/kaizen-backup commit --help`
- `tools/ci-local --python 3.9`


## Report

Report changed files and line counts, exact checks and outcomes, known uncertainty and any blocked verification. Label measurements with baseline/conditions. Redact paths and identifiers from shared output. Leave plugin version and release CHANGELOG to P27. Do not commit or push.

## Delta from P16 security review (fix these first, in `scripts/kaizen-backup`)

P16 landed with CLI ref writes still unreachable; these findings are P16b's to fix before ref writes are enabled. Each gets a regression test in `tests/test_backup_commit.py`.

1. Bounded object verification (~line 488): Git object verification buffers the whole decompressed object before hashing; an oversized commit or tree can exhaust memory, and the private tree builder has the same exposure for unchanged blobs. Stream and hash in chunks, and refuse objects over a stated size cap (a named constant) with a controlled refusal.
2. Temp probe inside the checkout (~line 481): `tempfile.gettempdir()` writes and deletes a probe file before the code checks whether the directory is inside the checkout, so a checkout-local `TMPDIR` writes inside the worktree. Check the candidate directory against the checkout (canonical paths) **before** any write, and fall back to the backup store's own private scratch directory instead of `gettempdir()` where possible.
3. Symlink loop crash (~line 913): `Path.resolve()` raises `RuntimeError` on symlink loops in Python 3.9–3.12, so a backed-up path replaced by a loop after `finish` crashes the CLI. Catch it (and `OSError`) and return a controlled refusal.

Settled stance (do not reopen): clean_start is advisory; same-UID forgery and a user-writable git swapped between check and exec are accepted residuals; caller environment trusted. The security review will confirm these three and P16b's own scope.
