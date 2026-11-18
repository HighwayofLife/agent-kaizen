# 03: Cache write forensics

## Goal and why

Show cache writes by gap and a headline, without claiming a cause the data cannot establish.

## Context

`scripts/usage-db:34-45,177-203,477-500,573-594` stores calls by session and agent, not spawn; `scripts/token-audit:445,721,1092` collects and renders audit data. `tests/bench_token_audit.py:56` compares scan speed.

## Constraints
Read `AGENTS.md`. Python 3.9 stdlib only; scripts under `scripts/` are executable and answer `--help`. Hooks use macOS bash 3.2, shellcheck, bounded work and exit 0 even on errors; an intentional denial is JSON with exit 0. Do not edit `.github/workflows/ci.yml`. Use `rg -n` and narrow `sed` ranges (no `tools/codemap` exists). Propose a changelog bullet; on each packet landing the integrator bumps the manifest and adds a dated changelog entry before checks, as required by AGENTS.md. Do not edit these shared files in parallel worktrees. Skills require quoted description, matching name, `disable-model-invocation: true`, and README table row. Never commit or push. Stop and report wrong assumptions or if the packet exceeds ~400 changed lines; do not drop criteria.

## Scope / do not touch

Edit `scripts/usage-db`, `scripts/token-audit`, `tests/test_usage_db.py`, `tests/test_usage.py`. Do not change schema, scheduler, scan or generator.

## Steps

Add `usage-db report --cache` honoring existing filters and table/CSV/JSON formats. Compute gap from previous timestamp per source/session/agent ordered by parsed UTC time and call ID, not raw SQLite timestamp text (fractional precision varies), over full history before applying date filters. Buckets: first, unknown, ≤5 minutes, >5–60, >60; classify full rewrite when write tokens >=80% of positive context. Main-session gaps are reliable; group subagent writes/counts but label merged-type gaps approximate. Add matching aggregated cache headline and structured audit fields from actual transcript sequence, without an extra scan. Handle ties, zero context, unavailable predecessor and Codex explicitly; no inferred cause or TTL recommendation.

## Acceptance criteria

1. Known main gaps, separate first and unknown buckets, exact boundary cases with whole and fractional seconds, full rewrite counts, filters, format outputs and interleaved subagent limitation are tested.
2. Audit headline and JSON match synthetic fixture; existing outputs remain compatible.
3. Benchmark before/after using baseline commit and report ratio; avoid material regression and report if unresolved.

## Verification

```sh
python3 -m unittest discover -s tests -p 'test_usage_db.py' -v
python3 -m unittest discover -s tests -p 'test_usage.py' -v
python3 tests/bench_token_audit.py --baseline 28b89c6
scripts/usage-db report --help
```

## Reporting

Report files, results, limitations and baseline/after measurements where applicable. Do not commit or push.

Changelog: Explain cache writes by idle gap.

## Suggested agent / model / effort and risk

`codex-engineer` / Terra medium. Risk: **normal**.
