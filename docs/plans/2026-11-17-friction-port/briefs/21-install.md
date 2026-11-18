# P21 Install new friction commands through managed kaizen links

## Goal

Install new friction commands through managed kaizen links. This packet is part of the Agent Kaizen friction port for 0.13.0.

- **Agent / model / effort** — `codex-dispatch` (`codex-engineer` fallback), terra, medium.
- **Risk** — normal. Use green checks and the integration batch review.
- **Group / dependencies** — G. After P10, P11, P12b, P15b, P18b.
- **Size target** — ~290 changed lines including focused tests.
- Changelog: Install new friction commands through managed kaizen links.

## Context

`scripts/kaizen-link:26–51,169–242` owns managed names and conflict handling. `scripts/install-schedule:419–441` delegates real installation. `scripts/kaizen-scheduled:923–951` resolves stable siblings. Copied runners and symlinked plugin installs have different real script paths.

Use the 0.12.0 integration base for landing. The references above are from 0.11.0 main at d8a4cb7. Read `AGENTS.md` and `CLAUDE.md`. Locate symbols with `tools/codemap` if available, otherwise `rg -n` and narrow `sed` ranges. All runtime changes support Python 3.9 and stdlib only. Use `python3`. Keep hard stops, captured user changes, zero-token collection and public-repo privacy; keep real logs and fixtures private.

## Scope and archive references

Owned files: `scripts/install-schedule`, `tests/test_kaizen_link.py`, `tests/test_install_schedule.py`, `tests/test_schedule.py`. Record the changelog line in `docs/plans/2026-11-17-friction-port/changelog/P21.md`. Coordinate a split if the diff plus tests exceeds 400 changed lines. Changes outside these paths need a separate packet or a revised scope.

Read `git show wt/p08b:scripts/install-schedule` at the archived copy list and `git show wt/p08b:tests/test_schedule.py` for copy/refresh assertions. Use only the inventory and prefixed destinations. `git show wt/p08b:scripts/kaizen-scheduled` is a reference for the inventories, not permission flags. Inspect archive paths with `git show` and keep the current branch.

## Implementation and acceptance

1. Use P00’s already-registered prefixed command/data names `kaizen-host-probe`, `kaizen-host-fix`, `kaizen-allow-rule`, `kaizen-worktree-prune` and `kaizen-friction-catalog.json`. Add each to `install-schedule`’s `MANAGED_NAMES` and source alias inventory. Add identity-named `kaizen_worktree_facts.py` and `kaizen_friction_actions.py` to `MANAGED_NAMES`. The install-schedule alias inventory changes only for differing basenames. P20 and P24b each add the identity-named helper alongside its first CLI consumer. Leave the P00 linker map intact.
2. In a disposable plugin-cache installation and isolated scheduler fixture, run `python3 scripts/install-schedule --apply --scheduler cron` without `--review`, using a stub crontab harness, following `tests/test_schedule.py` for accepted arguments and setup. Assert copied commands see only actual installed names, modules import beside them and probe reads the prefixed catalogue via the runner’s sibling pattern. Compare linked, copied, repeated apply/check, upgrade, missing sources and collision/unlink behavior. Preserve default job commands and permissions.


## Verification

- `python3 -m unittest discover -s tests -p 'test_kaizen_link.py'`
- `python3 -m unittest discover -s tests -p 'test_install_schedule.py'`
- `python3 -m unittest discover -s tests -p 'test_schedule.py'`
- `python3 scripts/kaizen-link --help`
- `tools/ci-local --python 3.9`


## Report

Report changed files and line counts, exact checks and outcomes, known uncertainty and any blocked verification. Label measurements with baseline/conditions. Redact paths and identifiers from shared output. Leave plugin version and release CHANGELOG to P27. Do not commit or push.
