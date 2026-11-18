# P11 Import evidence-backed host actions and verify outcomes

## Goal

Import evidence-backed host actions and verify outcomes. This packet is part of the Agent Kaizen friction port for 0.13.0.

- **Agent / model / effort** — `codex-dispatch` (`codex-engineer` fallback), sol, high.
- **Risk** — high. Get a per-packet verifier and Sol high review before merge.
- **Group / dependencies** — D. After P05, P07.
- **Size target** — ~375 changed lines including focused tests.
Sol reason: Strict wire validation and an atomic import receipt are required for retry after interruption.
- Changelog: Import evidence-backed host actions and verify outcomes.

## Context

P07 implements `kaizen_friction_actions.py` and scoped state CLI. `scripts/kaizen-scheduled:707–746,1231–1245` currently defines project state write and retention. P06 supplies bounded host findings. Store changes stay machine-local.

Use the 0.12.0 integration base for landing. The references above are from 0.11.0 main at d8a4cb7. Read `AGENTS.md` and `CLAUDE.md`. Locate symbols with `tools/codemap` if available, otherwise `rg -n` and narrow `sed` ranges. All runtime changes support Python 3.9 and stdlib only. Use `python3`. Keep hard stops, captured user changes, zero-token collection and public-repo privacy; keep real logs and fixtures private.

## Scope and archive references

Owned files: `scripts/kaizen_friction_actions.py`, `scripts/kaizen-scheduled`, `tests/test_host_actions.py`. Record the changelog line in `docs/plans/2026-11-17-friction-port/changelog/P11.md`. Coordinate a split if the diff plus tests exceeds 400 changed lines. Changes outside these paths need a separate packet or a revised scope.

Read `git show wt/p06:scripts/kaizen-scheduled` at `actions_import`, `_action_verify_spec`, `_action_metric`, `actions_verify`; use tests from `git show wt/p06:tests/test_host_actions.py` that cover repeat imports, manual proof and flapping. Inspect archive paths with `git show` and keep the current branch.

## Implementation and acceptance

1. Implement private `import_actions(block, frozen_map, project, generation)` and the scoped `actions verify --for DIR` command. The input contract is one `<!-- kaizen-host-actions {"v":1,"actions":[{"id":"fa1_<64 lowercase hex>","intent":"suggest"}]} -->` line, at most 8 KiB and 16 distinct IDs, with strict types/keys and literal intents `suggest` or `apply` as permitted by the frozen row and mode. Reject malformed, duplicate, oversized, unknown or cross-scope data before any write. Match frozen rows to their stable IDs before deriving catalogue steps or scope. Test with explicit in-memory fixtures. P20b owns the real CLI once preparation can rederive a fresh candidate map.
2. Persist a generation-bound receipt and scoped action upserts atomically under the store lock. Imported apply intent remains open and pending resolution. Re-import of the same generation/ID is a no-op, preserves dismissal and never hides pending work. Mark suggestions terminal for that receipt while their underlying action stays open for the user. Test an import followed by interruption, then a repeated import.
3. Verify via fixed read-only probes or explicit human confirmation. Record `metric_at_done` and basis. Reopen only on genuinely changed evidence, keep repeated flaps manual, and never let the verification pass overwrite pending or journaled work. Leave old records readable and missing proof as unavailable.

## Verification

- `python3 -m unittest discover -s tests -p 'test_host_actions.py'`
- `python3 -m unittest discover -s tests -p 'test_runner.py'`
- `python3 scripts/kaizen-scheduled actions verify --help`
- `tools/ci-local --python 3.9`

## Report

Report changed files and line counts, exact checks and outcomes, known uncertainty and any blocked verification. Label measurements with baseline/conditions. Redact paths and identifiers from shared output. Leave plugin version and release CHANGELOG to P27. Do not commit or push.
