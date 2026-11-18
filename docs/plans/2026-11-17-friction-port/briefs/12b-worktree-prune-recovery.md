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
