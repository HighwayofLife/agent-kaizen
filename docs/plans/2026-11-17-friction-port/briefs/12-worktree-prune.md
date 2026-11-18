# P12 Remove and recreate eligible clean, merged Git worktrees

## Goal

Remove and recreate eligible clean, merged Git worktrees. This packet is part of the Agent Kaizen friction port for 0.13.0.

- **Agent / model / effort** — `codex-dispatch` (`codex-engineer` fallback), sol, high.
- **Risk** — high. Get a per-packet verifier and Sol high review before merge. Obtain security review before landing.
- **Group / dependencies** — C. After P04.
- **Size target** — ~360 changed lines including focused tests.
- Sol reason: Clean, merged worktree preflight must refuse hidden changes and unsafe topology.
- Changelog: Remove and recreate eligible clean, merged Git worktrees.

## Context

`scripts/dispatch-status:11–58` has read-only worktree hints. P04 added stricter canonical facts. `docs/autonomy.md:56–82` protects user data and requires reversible actions. The main checkout and dirty/unmerged/unknown trees are outside this command's scope.

Use the 0.12.0 integration base for landing. The references above are from 0.11.0 main at d8a4cb7. Read `AGENTS.md` and `CLAUDE.md`. Locate symbols with `tools/codemap` if available, otherwise `rg -n` and narrow `sed` ranges. All runtime changes support Python 3.9 and stdlib only. Use `python3`. Keep hard stops, captured user changes, zero-token collection and public-repo privacy; keep real logs and fixtures private.

## Scope and archive references

Owned files: `scripts/worktree-prune`, `tests/test_worktree_prune.py`. Record the changelog line in `docs/plans/2026-11-17-friction-port/changelog/P12.md`. Keep the scoped diff and tests within the assigned cap. Changes outside these paths need a separate packet or a revised scope.

Read `git show wt/p14:scripts/worktree-prune` at `apply`, `undo`, `check_idle`, `check_ignored_repositories` and the p14b tests from `git show wt/p14:tests/test_worktree_prune.py`. Keep its branch-retention and moved-tip protections. Record archived behavior changes in the report. Inspect archive paths with `git show` and keep the current branch.

## Implementation and acceptance

1. Implement strict preflight and a private transaction/undo interface for `worktree-prune apply --project DIR --path DIR` and `worktree-prune undo RECORD --project DIR`. Require registered stable linked worktree in the same canonical common dir, existing non-detached local branch merged into the live primary branch, 24 hours inactivity, clean visible untracked/ignored state, no sparse/hidden index flags, no locks, no nested repos or regenerable output. Repeat live identity/cleanliness immediately before proposed removal. Stage writes behind a refusal until P12b completes journal and undo recovery.
2. Refuse a target containing either the process's canonical invocation cwd or the supplied canonical project path, even if the other path is outside. Test direct invocation from the target and a nested cwd, and invocation from the primary tree with `--project` under the target. Cover a clean eligible tree plus hidden/ignored sensitive data and unsafe Git overrides. No force and no branch removal.
3. Obtain security review before landing. P00 pre-registers the new command. Run the registration regression.


## Verification

- `python3 -m unittest discover -s tests -p 'test_worktree_prune.py'`
- `python3 -m unittest discover -s tests -p 'test_dispatch_status.py'`
- `python3 -m unittest discover -s tests -p 'test_kaizen_link.py'`
- `tools/ci-local --python 3.9`


## Report

Report changed files and line counts, exact checks and outcomes, known uncertainty and any blocked verification. Label measurements with baseline/conditions. Redact paths and identifiers from shared output. Leave plugin version and release CHANGELOG to P27. Do not commit or push.
