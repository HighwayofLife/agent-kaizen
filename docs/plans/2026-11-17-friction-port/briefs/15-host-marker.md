# P15 Apply and undo eligible LocalSearch output markers

## Goal

Apply and undo eligible LocalSearch output markers. This packet is part of the Agent Kaizen friction port for 0.13.0.

- **Agent / model / effort** — `codex-dispatch` (`codex-engineer` fallback), sol, high.
- **Risk** — high. Get a per-packet verifier and Sol high review before merge. Obtain security review before landing.
- **Group / dependencies** — E. After P10, P11.
- **Size target** — ~370 changed lines including focused tests.
- Sol reason: No-follow directory operations and path revalidation protect the marker target.
- Changelog: Apply and undo eligible LocalSearch output markers.

## Context

`scripts/kaizen-backup:110–155,204–210,303–344` validates backups and prints action reversals. `scripts/kaizen-scheduled:989–1046,1187–1220` keeps settings and unscoped Bash writes gated. P10 and P11 provide candidate facts and action states.

Use the 0.12.0 integration base for landing. The references above are from 0.11.0 main at d8a4cb7. Read `AGENTS.md` and `CLAUDE.md`. Locate symbols with `tools/codemap` if available, otherwise `rg -n` and narrow `sed` ranges. All runtime changes support Python 3.9 and stdlib only. Use `python3`. Keep hard stops, captured user changes, zero-token collection and public-repo privacy; keep real logs and fixtures private.

## Scope and archive references

Owned files: `scripts/host-fix`, `tests/test_host_fix.py`. Record the changelog line in `docs/plans/2026-11-17-friction-port/changelog/P15.md`. Keep the scoped diff and tests within the assigned cap. Changes outside these paths need a separate packet or a revised scope.

Read `git show wt/p12:scripts/host-fix` at `eligible_path`, `checked_directory`, `remove_marker`, `apply` and `undo`; inspect p12c tests via `git show wt/p12:tests/test_host_fix.py`. Keep the reviewed restrictions, independent of what the probe or store says. Inspect archive paths with `git show` and keep the current branch.

## Implementation and acceptance

1. Add `host-fix apply --project DIR --catalog-id linux-localsearch --path DIR` and an undo interface with writes dark until P15b. Re-resolve project policy (most restrictive with nested worktrees, malformed is refusal), known open eligible action, independently proven Git ignore/untracked status and an ordinary regenerable subdirectory. Refuse active/worktree roots, sensitive names, nested Git, foreign paths and symlinks. Verify a benign scoped marker fixture and refusal cases.
2. Implement no-follow directory-FD and exclusive marker creation primitives with private identity-stamped content. An existing marker is a no-op before work starts. Derive operation in code, with no catalogue executable, privilege escalation or Mac effects. Resolve installed probe/catalogue siblings using the runner pattern. Use P00's mapping and run the registration regression.
3. Obtain security review before landing. Keep apply dark until P15b proves recovery and undo along with present-day Linux marker support.


## Verification

- `python3 -m unittest discover -s tests -p 'test_host_fix.py'`
- `python3 -m unittest discover -s tests -p 'test_friction_catalog.py'`
- `python3 -m unittest discover -s tests -p 'test_kaizen_link.py'`
- `tools/ci-local --python 3.9`


## Report

Report changed files and line counts, exact checks and outcomes, known uncertainty and any blocked verification. Label measurements with baseline/conditions. Redact paths and identifiers from shared output. Leave plugin version and release CHANGELOG to P27. Do not commit or push.
