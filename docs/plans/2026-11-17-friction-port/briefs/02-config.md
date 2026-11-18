# P02 Add typed friction config and pin config output

## Goal

Add typed friction config and pin config output. This packet is part of the Agent Kaizen friction port for 0.13.0.

- **Agent / model / effort** — `codex-dispatch` (`codex-engineer` fallback), terra, medium.
- **Risk** — low. Use green checks.
- **Group / dependencies** — A1. No friction dependencies.
- **Size target** — ~230 changed lines including focused tests.
- Changelog: Add typed friction config and pin config output.

## Context

`scripts/kaizen-scheduled:62–149,170–299,2086–2171` owns schema, effective precedence, locking and `config show`. `tests/test_runner.py:46–105,195–233,319–330` pins defaults, precedence and config output. `tests/test_config_keys.py` checks runtime config-key drift.

Use the 0.12.0 integration base for landing. The references above are from 0.11.0 main at d8a4cb7. Read `AGENTS.md` and `CLAUDE.md`. Locate symbols with `tools/codemap` if available, otherwise `rg -n` and narrow `sed` ranges. All runtime changes support Python 3.9 and stdlib only. Use `python3`. Keep hard stops, captured user changes, zero-token collection and public-repo privacy; keep real logs and fixtures private.

## Scope and archive references

Owned files: `scripts/kaizen-scheduled`, `tests/test_runner.py`, `tests/test_friction_config.py`. Record the changelog line in `docs/plans/2026-11-17-friction-port/changelog/P02.md`. Coordinate a split if the diff plus tests exceeds 400 changed lines. Changes outside these paths need a separate packet or a revised scope.

Read `git show wt/p03:scripts/kaizen-scheduled` for friction schema entries and `git show wt/p03:tests/test_friction_config.py` for cases. Reuse today's parser and `valid_relative_paths`; leave filesystem validation to each consumer. Keep the shared paths-helper block byte-identical. Inspect archive paths with `git show` and keep the current branch.

## Implementation and acceptance

1. Add `friction` on/off (default on), `frictionSlowCallSeconds` >=10 (120), `frictionHeavySeconds` >=5 (60), `frictionOutputDirs` array (project only, []), `frictionSampler` on/off (global only, on) and `hostActions` apply/suggest/off (apply). Implement project-only validation for output dirs through load and set; require an enrolled project; reuse effective `{value,source}` shape and warn on wrong source or invalid values. Keep `enabled` global and current retention keys. Pin `test_defaults_and_global_reports`, `test_precedence`, `test_set_global_boolean_and_multiple_settings`, `test_set_project_preserves_other_keys_order_and_format`, and `test_keys_and_reports_path` in full `tests/test_runner.py`. Test config formats with spaces, traversal, empty components and wrong types, and verify rejected writes preserve original JSON.
2. Verify its failure and compatibility cases with the narrow checks below. Disabled/unavailable inputs must leave existing workflows usable. Keep partial changes private or gated until this packet's checks pass.
3. Confirm that the diff is confined to the owned files and that the integrated Python 3.9 check is green.

## Verification

- `python3 -m unittest discover -s tests -p 'test_friction_config.py'`
- `python3 -m unittest discover -s tests -p 'test_runner.py'`
- `python3 -m unittest discover -s tests -p 'test_config_keys.py'`
- `tools/ci-local --python 3.9`

## Report

Report changed files and line counts, exact checks and outcomes, known uncertainty and any blocked verification. Label measurements with baseline/conditions. Redact paths and identifiers from shared output. Leave plugin version and release CHANGELOG to P27. Do not commit or push.
