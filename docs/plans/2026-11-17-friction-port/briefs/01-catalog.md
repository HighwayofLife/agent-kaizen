# P01 Ship the friction process and action catalogue

## Goal

Ship the friction process and action catalogue. This packet is part of the Agent Kaizen friction port for 0.13.0.

- **Agent / model / effort** — `haiku-engineer`, haiku, high.
- **Risk** — low. Use green checks.
- **Group / dependencies** — A1. After P00.
- **Size target** — ~340 changed lines including focused tests.
- Changelog: Ship the friction process and action catalogue.

## Context

`scripts/pricing.json` and `tests/test_repo.py:29–36` show checked-in JSON conventions. There is no friction catalogue on main. The consumers will resolve the catalogue beside their real script path in source, linked, and copied installs.

Use the 0.12.0 integration base for landing. The references above are from 0.11.0 main at d8a4cb7. Read `AGENTS.md` and `CLAUDE.md`. Locate symbols with `tools/codemap` if available, otherwise `rg -n` and narrow `sed` ranges. All runtime changes support Python 3.9 and stdlib only. Use `python3`. Keep hard stops, captured user changes, zero-token collection and public-repo privacy; keep real logs and fixtures private.

## Scope and archive references

Owned files: `scripts/friction-catalog.json`, `tests/test_friction_catalog.py`. Record the changelog line in `docs/plans/2026-11-17-friction-port/changelog/P01.md`. Keep the scoped diff and tests within the assigned cap. Changes outside these paths need a separate packet or a revised scope.

Read `git show wt/p02:scripts/friction-catalog.json` and `git show wt/p02:tests/test_catalog.py` by range. Use the reviewed p02 tip for its process table, cloud roots, conservative output names and 15 action IDs, including low-disk. Keep code-free action entries and source references. Inspect archive paths with `git show` and keep the current branch.

## Implementation and acceptance

1. Publish valid v1 catalogue fields `processes`, `cloud_sync_names`, `output_dir_names`, `actions` and `source`. Land all 15 stable action IDs, supported OS scope, detector mapping, description, verify/undo metadata, automation level and sources with a minimal representative process/output set. Treat descriptive argv as data. P01b fills the remainder before integrated review.
2. Test version, shape and stable action IDs, including low-disk. P00 supplies the installed catalogue basename `kaizen-friction-catalog.json` for source basename `friction-catalog.json`. Consumers use the runner's prefixed-first `sibling()` convention, with repo/unprefixed fallback. Keep source JSON under the size target with compact per-entry objects.

## Verification

- `python3 -m unittest discover -s tests -p 'test_friction_catalog.py'`
- `python3 -m json.tool scripts/friction-catalog.json >/dev/null`
- `python3 -m unittest discover -s tests -p 'test_kaizen_link.py'`
- `tools/ci-local --python 3.9`

## Report

Report changed files and line counts, exact checks and outcomes, known uncertainty and any blocked verification. Label measurements with baseline/conditions. Redact paths and identifiers from shared output. Leave plugin version and release CHANGELOG to P27. Do not commit or push.
