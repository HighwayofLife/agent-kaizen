# P13 Measure overlapping heavy calls, polling and scoped regressions

## Goal

Measure overlapping heavy calls, polling and scoped regressions. This packet is part of the Agent Kaizen friction port for 0.13.0.

- **Agent / model / effort** — `codex-dispatch` (`codex-engineer` fallback), terra, medium.
- **Risk** — normal. Use green checks and the integration batch review.
- **Group / dependencies** — D. After P05, P09.
- **Size target** — ~320 changed lines including focused tests.
- Changelog: Measure overlapping heavy calls, polling and scoped regressions.

## Context

`scripts/token-audit:1279–1313` finds earlier same-scope reports. `:860–963,1327–1493` aggregates measurements. P03–P09 add canonical intervals, duration bases and common thresholds in the same traversal.

Use the merged 0.12.0 token-audit file and the P09 integration result. Read `AGENTS.md` and `CLAUDE.md`. Locate symbols with `tools/codemap` if available, otherwise `rg -n` and narrow `sed` ranges. All runtime changes support Python 3.9 and stdlib only. Use `python3`. Keep hard stops, captured user changes, zero-token collection and public-repo privacy; keep real logs and fixtures private.

## Scope and archive references

Owned files: `scripts/token-audit`, `tests/test_friction_timeline.py`. Record the changelog line in `docs/plans/2026-11-17-friction-port/changelog/P13.md`. Coordinate a split if the diff plus tests exceeds 400 changed lines. Changes outside these paths need a separate packet or a revised scope.

Read `git show wt/p04:scripts/token-audit` at `heavy_timeline`, `median_load_ratio`, `finalize_friction` and report comparisons; check p07's reviewed sweep fixes with `git show wt/p07:scripts/token-audit`. Reuse the bounded sweep rather than all-pairs comparisons. Inspect archive paths with `git show` and keep the current branch.

## Implementation and acceptance

1. Produce `parallel-heavy`, `contention`, polling and regression evidence. Use at least 3 comparable calls per side, ratio >=1.5, configurable heavy threshold, and half-open intervals; keep measured/estimated cohorts separate when comparing. Confirm overlap suspicion only when P17 supplies independent same-host load evidence (median load1/ncpu >=0.8 over matching spans); without it label the evidence `unconfirmed` and omit actionable flags. Regression requires previous same scope/window, threshold vector, signal basis and completed report, including n >=3 per side. Polling is report-only unless waiting is >=10 min in window and overlaps a slow sibling call. Test exact boundary, ties, high fan-out, scope mismatch and absence of load.
2. Verify its failure and compatibility cases with the narrow checks below. Disabled/unavailable inputs must leave existing workflows usable. Keep partial changes private or gated until this packet's checks pass.
3. Confirm that the diff is confined to the owned files and that the integrated Python 3.9 check is green.

## Verification

- `python3 -m unittest discover -s tests -p 'test_friction_timeline.py'`
- `python3 -m unittest discover -s tests -p 'test_friction_codex.py'`
- `python3 -m unittest discover -s tests -p 'test_format_canary.py'`
- `python3 tests/bench_token_audit.py --baseline "$FRICTION_BASE" --max-ratio 1.10` after capturing the pre-edit HEAD
- `tools/ci-local --python 3.9`

## Report

Report changed files and line counts, exact checks and outcomes, known uncertainty and any blocked verification. Label measurements with baseline/conditions. Redact paths and identifiers from shared output. Leave plugin version and release CHANGELOG to P27. Do not commit or push.
