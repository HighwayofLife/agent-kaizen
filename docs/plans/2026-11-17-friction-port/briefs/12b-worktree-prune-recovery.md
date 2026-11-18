# P12b Harden prune journals, undo and late-change refusals

## Goal

Harden prune journals, undo and late-change refusals. This packet is part of the Agent Kaizen friction port for 0.13.0.

- **Agent / model / effort** — `codex-dispatch` (`codex-engineer` fallback), sol, high.
- **Risk** — high. Get a per-packet verifier and Sol high review before merge. Obtain security review before landing.
- **Group / dependencies** — E. After P12.
- **Size target** — ~385 changed lines including focused tests.
Sol reason: Recovery and compare-before-remove must handle late writes and forged records.
- Changelog: Harden prune journals, undo and late-change refusals.

## Context

`scripts/dispatch-status:11–58` has read-only worktree hints. P04 added stricter canonical facts. `docs/autonomy.md:56–82` protects user data and requires reversible actions. The main checkout and dirty/unmerged/unknown trees are outside this command's scope.

Use the 0.12.0 integration base for landing. The references above are from 0.11.0 main at d8a4cb7. Read `AGENTS.md` and `CLAUDE.md`. Locate symbols with `tools/codemap` if available, otherwise `rg -n` and narrow `sed` ranges. All runtime changes support Python 3.9 and stdlib only. Use `python3`. Keep hard stops, captured user changes, zero-token collection and public-repo privacy; keep real logs and fixtures private.

## Scope and archive references

Owned files: `scripts/worktree-prune`, `tests/test_worktree_prune.py`. Record the changelog line in `docs/plans/2026-11-17-friction-port/changelog/P12b.md`. Keep the scoped diff and tests within the assigned cap. Changes outside these paths need a separate packet or a revised scope.

Read `git show wt/p14:scripts/worktree-prune` at `apply`, `undo`, `check_idle`, `check_ignored_repositories` and the p14b tests from `git show wt/p14:tests/test_worktree_prune.py`. Keep its branch-retention and moved-tip protections. Record archived behavior changes in the report. Inspect archive paths with `git show` and keep the current branch.

## Implementation and acceptance

1. Finish the recoverable pending/removal/undo phases. Bind them to canonical repo identity, original empty restoration path, branch/tip and operation identity. Recreate only that tree on its retained branch. No-force removal only. Retry after interruption by re-reading Git and record state, refuse ambiguous outcomes, and never overwrite a replacement path or remove another worktree or any branch.
2. Exercise kills and injected failures before and after removal and after recreation, record-write failure, moved branch/ref, forged or stale records and races with newly dirty, ignored or untracked files. Prove the supported Git no-force safety boundary in disposable repos before enabling unattended removal. If it cannot be established, keep the unattended operation proposal-only. Only enable direct apply/undo after all always-on safety checks in P12 and this packet hold.
3. Accept the runner’s private action-ID transaction key only through its fixed internal invocation. Bind it to tool-owned state so P24 can reconcile after the effect, and refuse a conflicting key/scope without changes. Preserve direct interactive record/undo behavior.
4. Obtain security review before landing. Use focused state-transition fixtures across P12/P12b. The archive is 373 source + 589 test lines, so share setup and consolidate overlapping tests to fit the two caps.


## Verification

- `python3 -m unittest discover -s tests -p 'test_worktree_prune.py'`
- `python3 -m unittest discover -s tests -p 'test_dispatch_status.py'`
- `tools/ci-local --python 3.9`


## Report

Report changed files and line counts, exact checks and outcomes, known uncertainty and any blocked verification. Label measurements with baseline/conditions. Redact paths and identifiers from shared output. Leave plugin version and release CHANGELOG to P27. Do not commit or push.

## Delta from P12 security review (2026-11-18)

P12 fixed the preflight findings (hardened git runner, live-byte cleanliness, identity-bound registration and containment, cache-free ancestry, worktree-private refs and reflog). These review findings were deferred here and must be closed before apply or undo can write:

1. **Effect-boundary race.** Repeating preflight still leaves a window before deletion in which files, refs, locks and path identity can change, and Git's no-force removal check omits ignored files. Do not rely on `git worktree remove`'s own cleanliness check. Make removal compare-before-remove: move the target directory atomically to a private quarantine sibling (same filesystem, `rename` by dir fd), re-verify identity and live-byte cleanliness of the quarantined tree, and only then delete it or restore it on any difference. Remove the admin dir only after that.
2. **Journal authentication.** An environment-selected journal location and same-UID permissions do not authenticate a record. Fix the journal location (no env override for apply/undo), bind each record to the target's recorded identity, branch oid and primary oid, and refuse undo when the restore path exists, is outside the recorded project, or the branch tip no longer matches the record. A forged record must never select an unrelated restore path.
3. **Hooks during undo.** Undo's `worktree add` must run through the P12 hardened runner (`core.hooksPath=/dev/null`, fsmonitor off, fixed env, absolute git) with `--no-checkout` followed by a filter-free restore (write blobs from `cat-file` yourself, or `checkout` only after proving no filter/attribute drivers apply), so no `post-checkout` hook or filter can run.

## Delta 2 from P12 final verification review (2026-11-18), MUST before effects go live

P12 landed with removal and undo still refusing to write, so these preflight gaps were carried here; P12b's security review must confirm each:

1. MUST (`scripts/worktree-prune:431`): `git cat-file --batch-check` accepts a blob whose header is intact but payload is corrupt. For every blob whose only readable copy would be the checkout (live bytes match the blob id), read the object with `git cat-file --batch` through the hardened runner and hash `blob <len>\0<bytes>` in Python with the repo's object format; refuse on mismatch or read error. Stream in bounded chunks.
2. MUST (`:475`): blob checks accept objects borrowed through alternates inside the linked worktree's admin directory. Refuse when any alternates file reachable from the common dir or the worktree admin dir (including `objects/info/alternates` and `GIT_ALTERNATE_OBJECT_DIRECTORIES`, which the runner already scrubs) resolves inside the admin directory or the checkout being removed.
3. SHOULD (`:474`): the xattr scan skips the worktree admin directory. Include its files (index, HEAD, logs/HEAD and the rest) in the same no-follow xattr check before deleting it.

Regression test for each in `tests/test_worktree_prune.py`.
