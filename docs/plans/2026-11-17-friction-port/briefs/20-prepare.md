# P20 Prepare bounded friction inputs and a deterministic new-signal gate

## Goal

Prepare bounded friction inputs and a deterministic new-signal gate. This packet is part of the Agent Kaizen friction port for 0.13.0.

- **Agent / model / effort** — `codex-dispatch` (`codex-engineer` fallback), terra, medium.
- **Risk** — normal. Use green checks and the integration batch review.
- **Group / dependencies** — H. After P10, P11, P17, P24a.
- **Size target** — ~380 changed lines including focused tests.
- Changelog: Prepare bounded friction inputs and a deterministic new-signal gate.

## Context

`scripts/kaizen-scheduled:662–746,935–962,1231–1245,2172–2270` has scoped audit destinations, project state and command discovery. P10 provides the probe, P11 actions reconcile, P17 the friction extract. Existing report names and v1 scope are stable.

Use the 0.12.0 integration base for landing. The references above are from 0.11.0 main at d8a4cb7. Read `AGENTS.md` and `CLAUDE.md`. Locate symbols with `tools/codemap` if available, otherwise `rg -n` and narrow `sed` ranges. All runtime changes support Python 3.9 and stdlib only. Use `python3`. Keep hard stops, captured user changes, zero-token collection and public-repo privacy; keep real logs and fixtures private.

## Scope and archive references

Owned files: `scripts/kaizen-scheduled`, `scripts/kaizen_friction_prepare.py`, `scripts/install-schedule`, `tests/test_friction_prepare.py`. Record the changelog line in `docs/plans/2026-11-17-friction-port/changelog/P20.md`. Keep the scoped diff and tests within the assigned cap. Changes outside these paths need a separate packet or a revised scope.

Read `git show wt/p08a:scripts/kaizen-scheduled` at `bounded_text`, `friction_extract`, `flag_fingerprints`, `probe_command`, `friction_prepare` and `friction_prepare_command`; read scoped and malformed-input tests from `git show wt/p08a:tests/test_runner.py`. Inspect archive paths with `git show` and keep the current branch.

## Implementation and acceptance

1. Implement `kaizen-scheduled friction prepare --for DIR [--report FILE]` and its runner callable. Under canonical enrollment select a fresh same-project audit or use the explicit report (canonical machine-local reports or the project's ordinary `docs/kaizen/token-audit-*.md`). Require the unique matching v1 extract in the audit extract directory and validated scope, report content/identity, thresholds, recent probe and bounded reads. Never substitute a stale usage report or change how cycle refreshes it.
2. Write a receipt under the backup-root friction namespace protected by existing tool denies with generation, project/scope, report/extract/probe identities and digests, policy and allowed rows; provide a separate bounded redacted `friction-inputs-*.json` model view. Show only display labels, numeric evidence and opaque IDs in the latter. Stable ID = `fa1_` and HMAC-SHA256 over compact ASCII JSON `[1, canonical_project,catalog_id,selector_key]` using the machine-private key. Keep target and permission provenance on the private side. Prep is read-only with respect to review/import and ack state.
3. Bind each flag bucket to exact scope, window definition, threshold vector and timing basis before comparing `(id,subject)` and `floor(log2(value))` for positive finite values. Rolling windows compare only at constant policy and lookback width, fixed windows at the exact UTC cutoff. Test same cohort unchanged/shrinking/increased flags, basis/window/threshold switches and switch back, and legacy fingerprint disregard. Suppress unchanged open suggestions, dismissed or observed terminal actions; retain valid unresolved imported candidates even while open. Return no path with exit 0 when disabled or empty. Test stale, forged, mismatched and unsupported inputs.

4. Add identity-mapped `kaizen_friction_prepare.py` to `install-schedule` `MANAGED_NAMES` in this packet. In `tests/test_friction_prepare.py`, use the stub cron pattern in `tests/test_schedule.py` and a temporary config home plus disposable copied plugin cache; run `python3 scripts/install-schedule --apply --scheduler cron`, then run the installed runner’s `friction prepare` with valid disposable evidence and assert its result, not just `--help`.

## Verification

- `python3 -m unittest discover -s tests -p 'test_friction_prepare.py'`
- `python3 -m unittest discover -s tests -p 'test_host_actions.py'`
- `python3 -m unittest discover -s tests -p 'test_runner.py'`
- `python3 -m unittest discover -s tests -p 'test_kaizen_link.py'`
- `python3 -m unittest discover -s tests -p 'test_schedule.py'`
- `python3 scripts/kaizen-scheduled friction prepare --help`
- `tools/ci-local --python 3.9`

## Report

Report changed files and line counts, exact checks and outcomes, known uncertainty and any blocked verification. Label measurements with baseline/conditions. Redact paths and identifiers from shared output. Leave plugin version and release CHANGELOG to P27. Do not commit or push.
