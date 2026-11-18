# 09: Regression sentinel and notice

## Goal and why

Detect usage regressions locally and surface at most one concise notice daily.

## Context

`scripts/usage-db:34-45,430-500,573` contains daily call data and pricing. `hooks/audit-notice.sh:1-40,93-134` scopes notices and bounds checkers. The existing scheduled audit ingests usage data; database lacks spawn identity.

## Constraints
Read `AGENTS.md`. Python 3.9 stdlib only; scripts under `scripts/` are executable and answer `--help`. Hooks use macOS bash 3.2, shellcheck, bounded work and exit 0 even on errors; an intentional denial is JSON with exit 0. Do not edit `.github/workflows/ci.yml`. Use `rg -n` and narrow `sed` ranges (no `tools/codemap` exists). Propose a changelog bullet; on each packet landing the integrator bumps the manifest and adds a dated changelog entry before checks, as required by AGENTS.md. Do not edit these shared files in parallel worktrees. Skills require quoted description, matching name, `disable-model-invocation: true`, and README table row. Never commit or push. Stop and report wrong assumptions or if the packet exceeds ~400 changed lines; do not drop criteria.

## Scope / do not touch

Edit `scripts/usage-db`, `hooks/audit-notice.sh`, `tools/context-budget.json`; create `tests/test_usage_guard.py`, `tests/test_regression_notice.py`. Do not edit scheduler, shared hook tests, config schema, or fixtures owned by other packets.

## Steps

Add `usage-db guard` using last 3 active UTC days vs preceding 14 active UTC days, per comparable metric. Implement main average context, daily expensive agent calls (explicitly calls, not spawns), per-agent cost share when priced, output/call and full-rewrite share; use only reliable main gaps. Compare the arithmetic mean of the last three daily values to the median and unscaled MAD of the preceding 14; default threshold now > median + max(3*MAD, 20% of abs(median), metric-specific minimum), documented in help; allow CLI threshold overrides. Require at least 17 active days separately for each metric, and valid nonzero denominators; otherwise print insufficient data, never pretend no regression. Deterministic `REGRESSION <metric> <now> vs <baseline>` sorted by severity then name; safe zero-MAD and unpriced handling. Integrate bounded read-only checker into notice, combining with existing notices and atomic once-per-day marker only when a regression is emitted. No model call or persistent guard data. Update the registered audit-notice hook maximum in the inventory and run the budget check. If implementation exceeds ~400 changed lines, stop and split guard from notice integration before landing.

## Acceptance criteria

1. Deterministic SQLite fixtures cover sparse history, 3/14 window boundaries, zeros, missing pricing, MAD=0, one spike versus sustained drift and no regressions.
2. Concurrent notice calls emit at most one regression line per day, retain existing notices, and fail open on malformed data, missing tool, timeout and permission errors.
3. Show synthetic backtest results; owner database backtest is separate research, never copy personal figures.

## Verification

```sh
python3 -m unittest discover -s tests -p 'test_usage_guard.py' -v
python3 -m unittest discover -s tests -p 'test_usage_db.py' -v
python3 -m unittest discover -s tests -p 'test_schedule_usage_db.py' -v
python3 -m unittest discover -s tests -p 'test_regression_notice.py' -v
python3 -m unittest discover -s tests -p 'test_hooks.py' -v
shellcheck -S warning hooks/audit-notice.sh
python3 tools/context_budget.py --root .
scripts/usage-db guard --help
```

## Reporting

Report files, results, limitations and baseline/after measurements where applicable. Do not commit or push.

Changelog: Surface daily usage regressions.

## Suggested agent / model / effort and risk

`codex-engineer` / Sol high (concurrent notice state). Risk: **high**.
