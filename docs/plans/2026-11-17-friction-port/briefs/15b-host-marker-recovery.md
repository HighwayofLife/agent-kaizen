# P15b Harden LocalSearch marker apply, rollback and undo

## Goal

Harden LocalSearch marker apply, rollback and undo. This packet is part of the Agent Kaizen friction port for 0.13.0.

- **Agent / model / effort** — `codex-dispatch` (`codex-engineer` fallback), sol, high.
- **Risk** — high. Get a per-packet verifier and Sol high review before merge. Obtain security review before landing.
- **Group / dependencies** — F. After P15.
- **Size target** — ~390 changed lines including focused tests.
Sol reason: Marker apply/undo must recover safely around partial effects and replacement.
- Changelog: Harden LocalSearch marker apply, rollback and undo.

## Context

`scripts/kaizen-backup:110–155,204–210,303–344` validates backups and prints action reversals. `scripts/kaizen-scheduled:989–1046,1187–1220` keeps settings and unscoped Bash writes gated. P10 and P11 provide candidate facts and action states.

Use the 0.12.0 integration base for landing. The references above are from 0.11.0 main at d8a4cb7. Read `AGENTS.md` and `CLAUDE.md`. Locate symbols with `tools/codemap` if available, otherwise `rg -n` and narrow `sed` ranges. All runtime changes support Python 3.9 and stdlib only. Use `python3`. Keep hard stops, captured user changes, zero-token collection and public-repo privacy; keep real logs and fixtures private.

## Scope and archive references

Owned files: `scripts/host-fix`, `tests/test_host_fix.py`. Record the changelog line in `docs/plans/2026-11-17-friction-port/changelog/P15b.md`. Keep the scoped diff and tests within the assigned cap. Changes outside these paths need a separate packet or a revised scope.

Read `git show wt/p12:scripts/host-fix` at `eligible_path`, `checked_directory`, `remove_marker`, `apply` and `undo`; inspect p12c tests via `git show wt/p12:tests/test_host_fix.py`. Keep the reviewed restrictions, independent of what the probe or store says. Inspect archive paths with `git show` and keep the current branch.

## Implementation and acceptance

1. Add durable pending/verified states for apply and undo around the private identity-stamped marker. Bind the record to the exact project, directory identity and change-specific marker contents. Undo works after host actions are disabled or the user dismisses the candidate, handles an absent marker idempotently and refuses a foreign or replaced marker.
2. Inject crashes before/after exclusive creation and during record writes; reconcile the existing marker and never adopt foreign state. Test nested policy, symlink/directory replacement, concurrent apply/undo, forged records and changed marker. Enable direct Linux apply only after these checks and S3 live compatibility pass. Keep native macOS writes separate in P19.
3. Accept the runner’s private action-ID transaction key only through its fixed internal invocation. Bind it to tool-owned state so P24 can reconcile after the effect, and refuse a conflicting key/scope without changes. Preserve direct interactive record/undo behavior.
4. Obtain security review before landing. The shared `wt/p12` baseline is 404 source + 908 test lines across the two P15 packets and P19; reuse focused fixtures and combine redundant failure matrices.


## Verification

- `python3 -m unittest discover -s tests -p 'test_host_fix.py'`
- `python3 -m unittest discover -s tests -p 'test_friction_catalog.py'`
- `tools/ci-local --python 3.9`


## Report

Report changed files and line counts, exact checks and outcomes, known uncertainty and any blocked verification. Label measurements with baseline/conditions. Redact paths and identifiers from shared output. Leave plugin version and release CHANGELOG to P27. Do not commit or push.

## Delta (P15 security review, 2026-11-18)

P15 landed with apply/undo gated. Its Sol high review found these; fix all before ungating apply or undo, each with a red test first:
1. MUST-FIX: `scripts/host-fix` ~line 129 — policy validation splits each configured path and checks every prefix with no deadline; on Python 3.14 overlong prefixes return false from `is_symlink()`, so a config under 1 MiB can stall `apply` far past its 20-second deadline. Bound the work: cap path length and component count when loading policy (refuse over-limit configs) and check the deadline inside the prefix loop.
2. ~line 274 — directory revalidation leaves a rename window before the create: the open descriptor still points at the directory if it is moved outside the eligible tree. Create relative to the verified dir fd and re-verify, after the create, that the dir fd's path still resolves to the same device/inode inside the eligible tree; on mismatch remove the just-created marker (by dir fd) and refuse.
3. ~line 212 — nested worktrees inherit the innermost relative path for outer allowlist checks, so an outer policy can approve a different path from the one evaluated. Compute the relative path separately against each worktree root whose policy is consulted.
4. ~line 275 — the existing-marker check runs after policy, traversal and action validation, so an invocation can refuse instead of returning the required no-op. Check for an existing marker (no-follow, by the verified dir fd) first and return the no-op.
