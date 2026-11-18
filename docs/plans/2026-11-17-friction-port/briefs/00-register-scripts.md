# P00 Pre-register friction commands and helpers with kaizen-link

## Goal

Pre-register friction commands and helpers with kaizen-link. This packet is part of the Agent Kaizen friction port for 0.13.0.

- **Agent / model / effort** — `haiku-engineer`, haiku, high.
- **Risk** — low. Use green checks.
- **Group / dependencies** — A. No friction dependencies.
- **Size target** — ~95 changed lines including focused tests.
- Changelog: Pre-register friction commands and helpers with kaizen-link.

## Context

`scripts/kaizen-link:28–48,183–213` maps names and skips absent sources. `tests/test_kaizen_link.py:138–142` checks every shipped script source is registered. This packet lands before any friction source file.

Use the 0.12.0 integration base for landing. The references above are from 0.11.0 main at d8a4cb7. Read `AGENTS.md` and `CLAUDE.md`. Locate symbols with `tools/codemap` if available, otherwise `rg -n` and narrow `sed` ranges. All runtime changes support Python 3.9 and stdlib only. Use `python3`. Keep hard stops, captured user changes, zero-token collection and public-repo privacy; keep real logs and fixtures private.

## Scope and archive references

Owned files: `scripts/kaizen-link`, `tests/test_kaizen_link.py`. Record the changelog line in `docs/plans/2026-11-17-friction-port/changelog/P00.md`. Keep the scoped diff and tests within the assigned cap. Changes outside these paths need a separate packet or a revised scope.

Use `git show multi-host:scripts/kaizen-link` to confirm the same registration contract on the integration base. Archived p08b used a separate copying path and supplies no registration code.

## Implementation and acceptance

1. Add these fixed `SCRIPTS` pairs as a single mechanical change, using installed name → source name. Map `kaizen-friction-catalog.json` → `friction-catalog.json`, `kaizen-host-probe` → `host-probe`, `kaizen-worktree-prune` → `worktree-prune`, `kaizen-host-fix` → `host-fix`, and `kaizen-allow-rule` → `allow-rule`. Register `kaizen_worktree_facts.py`, `kaizen_friction_actions.py`, `kaizen_friction_sample.py`, `kaizen_friction_prepare.py` and `kaizen_friction_apply.py` as identity mappings.
2. Test the full mapping and run default `--apply` and `--check` on isolated fixtures while the future files are absent. Absent sources create no links or copies and do not disturb unrelated local files. The existing all-scripts test continues to reject a missing mapping once a source lands.
3. This is the sole `SCRIPTS` registration packet. P21 installs those registered names whose source has landed, while P24 adds its broker helper to the schedule inventory when it enables that helper.

## Verification

- `python3 -m unittest discover -s tests -p 'test_kaizen_link.py'`
- `tools/ci-local --python 3.9`

## Report

Report changed files and line counts, exact checks and outcomes, known uncertainty and any blocked verification. Label measurements with baseline/conditions. Redact paths and identifiers from shared output. Leave plugin version and release CHANGELOG to P27. Do not commit or push.
