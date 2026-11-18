# P17 Join bounded samples and confirm contention only with load evidence

## Goal

Join bounded samples and confirm contention only with load evidence. This packet is part of the Agent Kaizen friction port for 0.13.0.

- **Agent / model / effort** — `codex-dispatch` (`codex-engineer` fallback), terra, medium.
- **Risk** — normal. Use green checks and the integration batch review.
- **Group / dependencies** — G. After P13, P14c.
- **Size target** — ~350 changed lines including focused tests.
- Changelog: Join bounded samples and confirm contention only with load evidence.

## Context

`scripts/token-audit:142–245,564–736,860–963,1466–1565` gives scan, pairing and extract. P13 emits normalized intervals; P14/P14b write daily TSV under `<audits>/samples` and an independent process row. Read only validated private sample files.

Use the merged 0.12.0 token-audit base with P13, P14b and P14c landed in this integration branch. Read `AGENTS.md` and `CLAUDE.md`. Locate symbols with `tools/codemap` if available, otherwise `rg -n` and narrow `sed` ranges. All runtime changes support Python 3.9 and stdlib only. Use `python3`. Keep hard stops, captured user changes, zero-token collection and public-repo privacy; keep real logs and fixtures private.

## Scope and archive references

Owned files: `scripts/token-audit`, `tests/test_friction_samples.py`. Record the changelog line in `docs/plans/2026-11-17-friction-port/changelog/P17.md`. Coordinate a split if the diff plus tests exceeds 400 changed lines. Changes outside these paths need a separate packet or a revised scope.

Read `git show wt/p07:scripts/token-audit` at `read_samples`, `host_load_summary`, `median_load_ratio`, Claude pairing and `friction_sections`, plus `git show wt/p07:tests/test_friction_samples.py`. Keep samples bounded and separate from normal accounting. Inspect archive paths with `git show` and keep the current branch.

## Implementation and acceptance

1. Add `--samples-dir DIR` for an explicit source, defaulting to configured local audits. Scan only UTC days overlapping the window, with hard byte, row and cardinality limits, no symlinks, and tolerate incomplete/corrupt rows. Join duration by exact `(session_id, tool_use_id)` with completed-event timestamp near the tool-result row and refuse conflicts. Prefer measured duration for slow calls; compute prompted wait as a nonnegative gap less the measured duration where comparable, otherwise keep the upper bound. Load confirmation requires compatible samples within spans with local provenance, such as exact matching Claude session/tool IDs, and a minimum of 3 data points, median load/CPU >=0.8 and existing ratio/sample floors; never pair Codex IDs to Claude IDs or label estimates as runtime. A matching clock interval alone does not prove that a Codex rollout ran on the sampled host, so those intervals remain unconfirmed. Emit bounded catalogue categories and hit/hour counts, with no raw process names outside the catalogue. Test duplicates and conflicting IDs, early/late sample joins, missing days, retention race, mixed hosts, unavailable duration, and no sample flagging when off.
2. Verify its failure and compatibility cases with the narrow checks below. Disabled/unavailable inputs must leave existing workflows usable. Keep partial changes private or gated until this packet's checks pass.
3. Confirm that the diff is confined to the owned files and that the integrated Python 3.9 check is green.

## Verification

- `python3 -m unittest discover -s tests -p 'test_friction_samples.py'`
- `python3 -m unittest discover -s tests -p 'test_friction_timeline.py'`
- `python3 -m unittest discover -s tests -p 'test_format_canary.py'`
- `python3 -m unittest discover -s tests -p 'test_usage.py'`
- `python3 tests/bench_token_audit.py --baseline "$FRICTION_BASE" --max-ratio 1.10` after capturing the pre-edit HEAD, then versus the pre-friction 0.12.0 integration base
- `tools/ci-local --python 3.9`

## Report

Report changed files and line counts, exact checks and outcomes, known uncertainty and any blocked verification. Label measurements with baseline/conditions. Redact paths and identifiers from shared output. Leave plugin version and release CHANGELOG to P27. Do not commit or push.
