# P23 Wire scheduled preparation and reconcile only successful reviews

## Goal

Wire scheduled preparation and reconcile only successful reviews. This packet is part of the Agent Kaizen friction port for 0.13.0.

- **Agent / model / effort** — `codex-dispatch` (`codex-engineer` fallback), terra, medium.
- **Risk** — normal. Use green checks and the integration batch review.
- **Group / dependencies** — J. After P20b, P21.
- **Size target** — ~375 changed lines including focused tests.
- Changelog: Wire scheduled preparation and reconcile only successful reviews.

## Context

`scripts/kaizen-scheduled:841–914,952–961,1187–1220,1877–2085` owns project gating, audit command, prompt, active marker, review and success state. `:1650–1876` is rollback/recovery. P20 prepares v1 model inputs and keeps the allow map private. P11 verifies/imports against prepared evidence and P20b re-derives that evidence for the interactive CLI.

Use the 0.12.0 integration base for landing. The references above are from 0.11.0 main at d8a4cb7. Read `AGENTS.md` and `CLAUDE.md`. Locate symbols with `tools/codemap` if available, otherwise `rg -n` and narrow `sed` ranges. All runtime changes support Python 3.9 and stdlib only. Use `python3`. Keep hard stops, captured user changes, zero-token collection and public-repo privacy; keep real logs and fixtures private.

## Scope and archive references

Owned files: `scripts/kaizen-scheduled`, `scripts/kaizen_friction_prepare.py`, `tests/test_friction_review.py`. Record the changelog line in `docs/plans/2026-11-17-friction-port/changelog/P23.md`. Coordinate a split if the diff plus tests exceeds 400 changed lines. Changes outside these paths need a separate packet or a revised scope.

Read `git show wt/p08a:scripts/kaizen-scheduled` at `audit_command`, `friction_prepare`, `review_command` and `_run_review`. Use `git show wt/p08a:tests/test_runner.py` for no-new-signal and success/failure prompts; use 0.11 and 0.12 runner code for actual flow. Inspect archive paths with `git show` and keep the current branch.

## Implementation and acceptance

1. Use one friction audit argv policy in both global `audit` and `auto-audit` and the scoped scheduled path. Global policy uses `effective()` without a project. Scoped policy retains project precedence. Verify off and explicit thresholds for all three, with existing report, usage-db and cadence unaffected.
2. After a valid scoped audit, pass one JSON-quoted `friction-inputs=` to Claude if the gate is open. Keep the report argument, dry run, permission flags, active marker, ledger/rollback gating and ordinary report/last-success behavior. P20 already added `kaizen_friction_prepare.py` to `install-schedule`’s `MANAGED_NAMES`; assert in `tests/test_friction_review.py` that a copied `install-schedule --apply` fixture (use the stub cron pattern in `tests/test_schedule.py`) runs preparation through the installed runner. P00 supplies its linker mapping.
3. On guarded success only, strip the v1 action comment from rendered output and use P11’s transactional import with the runner-retained map. Do not acknowledge a scheduled apply request in this packet. While broker is dark, preserve it pending without an effect. A suggestion-only packet can acknowledge after import, including explicit empty actions, with exact generation and comparison key; failed/noisy/malformed/terminated runs cannot ack. Test import without ack on a requested apply, retry, timeout and fallback when optional preparation fails.

## Verification

- `python3 -m unittest discover -s tests -p 'test_friction_review.py'`
- `python3 -m unittest discover -s tests -p 'test_runner.py'`
- `python3 -m unittest discover -s tests -p 'test_schedule_security.py'`
- `python3 -m unittest discover -s tests -p 'test_schedule_robustness.py'`
- `python3 -m unittest discover -s tests -p 'test_schedule.py'`
- `tools/ci-local --python 3.9`

## Report

Report changed files and line counts, exact checks and outcomes, known uncertainty and any blocked verification. Label measurements with baseline/conditions. Redact paths and identifiers from shared output. Leave plugin version and release CHANGELOG to P27. Do not commit or push.
