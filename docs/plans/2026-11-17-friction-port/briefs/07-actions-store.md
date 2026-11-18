# P07 Track machine-local host actions and manual state changes

## Goal

Track machine-local host actions and manual state changes. This packet is part of the Agent Kaizen friction port for 0.13.0.

- **Agent / model / effort** — `codex-dispatch` (`codex-engineer` fallback), sol, high.
- **Risk** — high. Get a per-packet verifier and Sol high review before merge.
- **Group / dependencies** — C. After P01b, P02.
- **Size target** — ~350 changed lines including focused tests.
Sol reason: Stable scoped IDs and concurrent private-store writes are the action trust boundary.
- Changelog: Track machine-local host actions and manual state changes.

## Context

`scripts/kaizen-scheduled:158–170,662–746,2086–2152,2172–2270` owns project identity, lock and state conventions. `tests/test_runner.py:379–390` is the command-help pattern. Store actions in `<audits>/host-actions.json` as machine-local v1 with an `.actions` map. Each record has a stable ID, catalogue ID, subject, project keys, status, timestamps and bounded evidence. Flat project keys use the runner's existing canonical `key()`.

Use the 0.12.0 integration base for landing. The references above are from 0.11.0 main at d8a4cb7. Read `AGENTS.md` and `CLAUDE.md`. Locate symbols with `tools/codemap` if available, otherwise `rg -n` and narrow `sed` ranges. All runtime changes support Python 3.9 and stdlib only. Use `python3`. Keep hard stops, captured user changes, zero-token collection and public-repo privacy; keep real logs and fixtures private.

## Scope and archive references

Owned files: `scripts/kaizen_friction_actions.py`, `scripts/kaizen-scheduled`, `tests/test_host_actions.py`. Record the changelog line in `docs/plans/2026-11-17-friction-port/changelog/P07.md`. Coordinate a split if the diff plus tests exceeds 400 changed lines. Changes outside these paths need a separate packet or a revised scope.

Read `git show wt/p06:scripts/kaizen-scheduled` at `action_id`, `read_actions`, `write_actions`, `actions_mark`, `actions_command`; reuse reviewed tests from `git show wt/p06:tests/test_host_actions.py`. Extract focused store code into `kaizen_friction_actions.py` and import only in new paths so an old copied runner retains existing commands. Inspect archive paths with `git show` and keep the current branch.

## Implementation and acceptance

1. Add `kaizen-scheduled actions list --for DIR [--json]` and `done|dismiss|reopen ID --for DIR`. Derive stable IDs from an atomic owner-private machine key in the backup-root friction namespace protected by existing runner denies: `fa1_` plus lowercase hex HMAC-SHA256 over compact ASCII JSON array `[1, canonical_project, catalog_id, selector_key]` (UTF-8 bytes, ASCII escapes, no whitespace). Normalize paths by strict canonical resolved scope, and use closed canonical literal/enum or already-redacted flag key for other selectors. Reject collisions, unknown versions and unusable keys without regenerating IDs for existing rows. Test stable concurrent creation and distinct project/literal identities. Persist canonical project provenance. Use owner-private regular-file/no-symlink checks, bounded reads and atomic replacement under a lock shared by all writers. Windows/lock-unavailable writers must refuse or use an atomic ownership lock with tested recovery; missing store lists zero, invalid store fails writes closed. Avoid lost updates from simultaneous project writes and idempotently handle repeated transitions. Keep other projects' records out of scoped listings. New state cannot auto-act until an evidence-backed import marks it eligible.
2. Verify its failure and compatibility cases with the narrow checks below. Disabled/unavailable inputs must leave existing workflows usable. Keep partial changes private or gated until this packet's checks pass.
3. Confirm that the diff is confined to the owned files and that the integrated Python 3.9 check is green.

## Verification

- `python3 -m unittest discover -s tests -p 'test_host_actions.py'`
- `python3 -m unittest discover -s tests -p 'test_runner.py'`
- `python3 scripts/kaizen-scheduled actions --help`
- `python3 -m unittest discover -s tests -p 'test_kaizen_link.py'`
- `tools/ci-local --python 3.9`

## Report

Report changed files and line counts, exact checks and outcomes, known uncertainty and any blocked verification. Label measurements with baseline/conditions. Redact paths and identifiers from shared output. Leave plugin version and release CHANGELOG to P27. Do not commit or push.
