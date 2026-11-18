# P20b Re-derive interactive candidates before import and acknowledgement

## Goal

Re-derive interactive candidates before import and acknowledgement. This packet is part of the Agent Kaizen friction port for 0.13.0.

- **Agent / model / effort** — `codex-dispatch` (`codex-engineer` fallback), terra, medium.
- **Risk** — normal. Use green checks and the integration batch review.
- **Group / dependencies** — I. After P20.
- **Size target** — ~335 changed lines including focused tests.
- Changelog: Re-derive interactive candidates before import and acknowledgement.

## Context

`scripts/kaizen-scheduled:662–746,935–962,1231–1245,2172–2270` has scoped audit destinations, project state and command discovery. P10 provides the probe, P11 actions reconcile, P17 the friction extract. Existing report names and v1 scope are stable.

Use the 0.12.0 integration base for landing. The references above are from 0.11.0 main at d8a4cb7. Read `AGENTS.md` and `CLAUDE.md`. Locate symbols with `tools/codemap` if available, otherwise `rg -n` and narrow `sed` ranges. All runtime changes support Python 3.9 and stdlib only. Use `python3`. Keep hard stops, captured user changes, zero-token collection and public-repo privacy; keep real logs and fixtures private.

## Scope and archive references

Owned files: `scripts/kaizen-scheduled`, `scripts/kaizen_friction_prepare.py`, `tests/test_friction_prepare.py`. Record the changelog line in `docs/plans/2026-11-17-friction-port/changelog/P20b.md`. Keep the scoped diff and tests within the assigned cap. Changes outside these paths need a separate packet or a revised scope.

Read `git show wt/p08a:scripts/kaizen-scheduled` at `bounded_text`, `friction_extract`, `flag_fingerprints`, `probe_command`, `friction_prepare` and `friction_prepare_command`; read scoped and malformed-input tests from `git show wt/p08a:tests/test_runner.py`. Inspect archive paths with `git show` and keep the current branch.

## Implementation and acceptance

1. Land `kaizen-scheduled actions import FILE --for DIR --inputs FILE` only with the callable that validates the private preparation receipt and re-derives an exact current map from live scope, report/extract/probe digests, policy and evidence. The supplied model view/file carries no authority. Reject stale/expired, forged and cross-project views and mismatched candidate IDs. Accept only the v1 exact bounded block of `id` and `intent` described below. Interactive import records suggestions only, with no execution authority. Direct ticketed actions remain governed by their own CLI and mode checks.
2. Expose `friction acknowledge INPUTS --for DIR` for successful interactive work only. Require successful validated import receipt for that generation, including a parsed empty actions array when no action is proposed. Reject failed, stale/older, unmatched or empty-gate acknowledgement. A scheduled generation is runner-only and a pending scheduled write cannot be acknowledged through this CLI.
3. Test prepare→import→ack, interruption after preparation/import, retry, out-of-order ack, concurrent generation, disabled friction, and unchanged view comparison key. Acceptance includes refusing a valid-looking block with an ID copied from another project.
4. Using the P20-managed `kaizen_friction_prepare.py`, run `install-schedule --apply --scheduler cron` with a stub crontab, temporary config home and copied plugin cache in `tests/test_friction_prepare.py`; exercise installed prepare → `actions import` → acknowledge with valid disposable inputs and assert persisted results.
5. The standalone wire contract is one whole line `<!-- kaizen-host-actions {"v":1,"actions":[{"id":"fa1_<64 lowercase hex>","intent":"suggest"}]} -->`. At most 8 KiB and 16 distinct IDs. The only permitted keys are shown, and the only intents are `suggest` and `apply` (interactive import refuses `apply`). Use P11’s parser, never parse human prose.


## Verification

- `python3 -m unittest discover -s tests -p 'test_friction_prepare.py'`
- `python3 -m unittest discover -s tests -p 'test_host_actions.py'`
- `python3 -m unittest discover -s tests -p 'test_runner.py'`
- `python3 scripts/kaizen-scheduled actions import --help`
- `python3 scripts/kaizen-scheduled friction acknowledge --help`
- `tools/ci-local --python 3.9`


## Report

Report changed files and line counts, exact checks and outcomes, known uncertainty and any blocked verification. Label measurements with baseline/conditions. Redact paths and identifiers from shared output. Leave plugin version and release CHANGELOG to P27. Do not commit or push.
