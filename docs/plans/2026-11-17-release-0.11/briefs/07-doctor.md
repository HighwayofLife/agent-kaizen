# 07: Installation doctor

## Goal and why

Give actionable health checks and show transcript format drift in one zero-model command.

## Context

`scripts/kaizen-link` checks stale cache; `scripts/pricing.json:2-5` has checked date; `scripts/usage-db:341-355` has freshness; `scripts/kaizen-scheduled:168,193` validates config. Packet 06 persists `format_canary: v1 unknown_records=N missing_usage=N cli=X` in the `token-audit-headline` JSON comment as the `format_canary` string.

## Constraints
Read `AGENTS.md`. Python 3.9 stdlib only; scripts under `scripts/` are executable and answer `--help`. Hooks use macOS bash 3.2, shellcheck, bounded work and exit 0 even on errors; an intentional denial is JSON with exit 0. Do not edit `.github/workflows/ci.yml`. Use `rg -n` and narrow `sed` ranges (no `tools/codemap` exists). Propose a changelog bullet; on each packet landing the integrator bumps the manifest and adds a dated changelog entry before checks, as required by AGENTS.md. Do not edit these shared files in parallel worktrees. Skills require quoted description, matching name, `disable-model-invocation: true`, and README table row. Never commit or push. Stop and report wrong assumptions or if the packet exceeds ~400 changed lines; do not drop criteria.

## Scope / do not touch

Create executable `scripts/kaizen-doctor` and `tests/test_doctor.py`. Edit `scripts/kaizen-link` SCRIPTS and `scripts/install-schedule` MANAGED_NAMES to register the doctor. Do not edit other shared scripts, README, config or hooks.

## Steps

Implement bounded read-only checks for plugin root versus installed cache (reuse link check), expected hook registration and executable dependencies, jq/Python versions, optional scheduler status, pricing age, DB last ingest, config validity and latest format canary by reading the newest persisted report; older reports without the field and no reports produce WARN. Do not invoke an audit or write any state. Print PASS/WARN/FAIL with a concrete safe fix command on WARN/FAIL; optional scheduler absence is informational since hooks run automatically. Missing data, absent latest audit and unknown version show WARN, never fake PASS. Never install, run a model or modify state. Avoid exposing local paths or database contents in test output.

## Acceptance criteria

1. Isolated fake installations cover healthy, stale cache, missing/malformed hook, missing jq/old Python, optional scheduler absent, old pricing/database, bad config, and format drift/unknown.
2. Every warning/failure includes actionable fix; `--help` exits 0; no writes or network.

## Verification

```sh
python3 -m unittest discover -s tests -p 'test_doctor.py' -v
python3 -m unittest discover -s tests -p 'test_kaizen_link.py' -v
scripts/kaizen-doctor --help
```

## Reporting

Report files, results, limitations and baseline/after measurements where applicable. Do not commit or push.

Changelog: Add install and data health checks.

## Suggested agent / model / effort and risk

`codex-engineer` / Terra medium. Risk: **normal**.
