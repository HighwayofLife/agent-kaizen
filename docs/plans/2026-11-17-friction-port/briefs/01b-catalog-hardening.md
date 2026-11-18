# P01b Finish catalogue rows and pin validation against the archive

## Goal

Finish catalogue rows and pin validation against the archive. This packet is part of the Agent Kaizen friction port for 0.13.0.

- **Agent / model / effort** — `haiku-engineer`, haiku, high.
- **Risk** — low. Use green checks.
- **Group / dependencies** — B. After P01.
- **Size target** — ~350 changed lines including focused tests.
- Changelog: Finish catalogue rows and pin validation against the archive.

## Context

`scripts/pricing.json` and `tests/test_repo.py:29–36` show checked-in JSON conventions. There is no friction catalogue on main. The consumers will resolve the catalogue beside their real script path in source, linked, and copied installs.

Use the 0.12.0 integration base for landing. The references above are from 0.11.0 main at d8a4cb7. Read `AGENTS.md` and `CLAUDE.md`. Locate symbols with `tools/codemap` if available, otherwise `rg -n` and narrow `sed` ranges. All runtime changes support Python 3.9 and stdlib only. Use `python3`. Keep hard stops, captured user changes, zero-token collection and public-repo privacy; keep real logs and fixtures private.

## Scope and archive references

Owned files: `scripts/friction-catalog.json`, `tests/test_friction_catalog.py`. Record the changelog line in `docs/plans/2026-11-17-friction-port/changelog/P01b.md`. Keep the scoped diff and tests within the assigned cap. Changes outside these paths need a separate packet or a revised scope.

Read `git show wt/p02:scripts/friction-catalog.json` and `git show wt/p02:tests/test_catalog.py` by range. Use the reviewed p02 tip for its process table, cloud roots, conservative output names and 15 action IDs, including low-disk. Keep code-free action entries and source references. Inspect archive paths with `git show` and keep the current branch.

## Implementation and acceptance

1. Populate the remaining process, cloud and conservative output-directory data and source notes from `wt/p02`. Preserve the core schema, reviewed 15 action IDs and detector-to-action mappings. Use one stable, compact JSON row per entry or metadata member while keeping it readable. Measure the diff with `git diff --numstat -- scripts/friction-catalog.json tests/test_friction_catalog.py`.
2. Compare parsed values to the archived catalogue for every ported field and test duplicates, malformed templates, unknown versions and forbidden executable fields. Document intentional data-only differences. The archive has 613 data + 160 test lines; budget ~350 lines here after compact formatting and retaining representative tests.


## Verification

- `python3 -m unittest discover -s tests -p 'test_friction_catalog.py'`
- `python3 -m json.tool scripts/friction-catalog.json >/dev/null`
- `tools/ci-local --python 3.9`


## Report

Report changed files and line counts, exact checks and outcomes, known uncertainty and any blocked verification. Label measurements with baseline/conditions. Redact paths and identifiers from shared output. Leave plugin version and release CHANGELOG to P27. Do not commit or push.
