# P04 Show optional Git worktree facts in dispatch status

## Goal

Show optional Git worktree facts in dispatch status. This packet is part of the Agent Kaizen friction port for 0.13.0.

- **Agent / model / effort** — `codex-dispatch` (`codex-engineer` fallback), terra, medium.
- **Risk** — normal. Use green checks and the integration batch review.
- **Group / dependencies** — A1. After P00.
- **Size target** — ~250 changed lines including focused tests.
- Changelog: Show optional Git worktree facts in dispatch status.

## Context

`scripts/dispatch-status:11–58,60–102` lists linked trees and reports dirty contents while ignoring `out`. Current `dirty_row` is a dispatch hint. A deletion check needs a separate stricter status path.

Use the 0.12.0 integration base for landing. The references above are from 0.11.0 main at d8a4cb7. Read `AGENTS.md` and `CLAUDE.md`. Locate symbols with `tools/codemap` if available, otherwise `rg -n` and narrow `sed` ranges. All runtime changes support Python 3.9 and stdlib only. Use `python3`. Keep hard stops, captured user changes, zero-token collection and public-repo privacy; keep real logs and fixtures private.

## Scope and archive references

Owned files: `scripts/dispatch-status`, `scripts/kaizen_worktree_facts.py`, `tests/test_dispatch_status.py`. Record the changelog line in `docs/plans/2026-11-17-friction-port/changelog/P04.md`. Coordinate a split if the diff plus tests exceeds 400 changed lines. Changes outside these paths need a separate packet or a revised scope.

Read `git show wt/p14:scripts/worktree-prune` at `worktrees`, `default_branch` and `check_idle`; read `git show wt/p14:tests/test_worktree_prune.py` cases for tricky worktree registrations. Port only read-only Git fact helpers. Inspect archive paths with `git show` and keep the current branch.

## Implementation and acceptance

1. Add a bounded shared reader in `kaizen_worktree_facts.py` using argv, no shell, no fsmonitor/optional locks, safe Git env, NUL records first and safe fallback. Return canonical path, branch/tip, primary/linked/locked/detached and tri-state strict cleanliness and merged-into-primary-branch facts. Resolve ancestry of the local primary checked-out branch without fetching. Missing/ambiguous data yields unknown. Add `dispatch-status --worktree-facts` with the current directory selection and preserve default output and its `out` filter. Test old Git fallback, unusual path boundaries, dirty/clean, locked, detached, unknown, ancestry and no Git. Use P00’s `kaizen_worktree_facts.py` identity mapping and the runner’s prefixed-first sibling convention for any catalogued siblings; absent helper must leave default command working.
2. Verify its failure and compatibility cases with the narrow checks below. Disabled/unavailable inputs must leave existing workflows usable. Keep partial changes private or gated until this packet's checks pass.
3. Confirm that the diff is confined to the owned files and that the integrated Python 3.9 check is green.

## Verification

- `python3 -m unittest discover -s tests -p 'test_dispatch_status.py'`
- `python3 scripts/dispatch-status --help`
- `python3 -m unittest discover -s tests -p 'test_kaizen_link.py'`
- `tools/ci-local --python 3.9`

## Report

Report changed files and line counts, exact checks and outcomes, known uncertainty and any blocked verification. Label measurements with baseline/conditions. Redact paths and identifiers from shared output. Leave plugin version and release CHANGELOG to P27. Do not commit or push.
