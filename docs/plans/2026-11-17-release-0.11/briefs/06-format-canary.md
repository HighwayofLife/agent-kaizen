# 06: Transcript format canary

## Goal and why

Expose parser coverage changes by CLI version before silent undercounting becomes normal.

## Context

`scripts/token-audit:71-153` filters raw lines before decoding, and :445,721 scan; version may be absent. Packet 02 provides synthetic fixtures; :1176 renders report.

## Constraints
Read `AGENTS.md`. Python 3.9 stdlib only; scripts under `scripts/` are executable and answer `--help`. Hooks use macOS bash 3.2, shellcheck, bounded work and exit 0 even on errors; an intentional denial is JSON with exit 0. Do not edit `.github/workflows/ci.yml`. Use `rg -n` and narrow `sed` ranges (no `tools/codemap` exists). Propose a changelog bullet; on each packet landing the integrator bumps the manifest and adds a dated changelog entry before checks, as required by AGENTS.md. Do not edit these shared files in parallel worktrees. Skills require quoted description, matching name, `disable-model-invocation: true`, and README table row. Never commit or push. Stop and report wrong assumptions or if the packet exceeds ~400 changed lines; do not drop criteria.

## Scope / do not touch

Edit `scripts/token-audit`; create `tests/test_format_canary.py`. Do not edit doctor, scan, existing shared test modules or usage-db.

## Steps

Count unknown transcript record types and missing expected usage fields by observed CLI version, using `unknown` when absent. Define recognized types and eligible assistant usage rows explicitly so user/tool/metadata rows and synthetic non-usage records are not false positives. Account for records currently skipped by byte prefilter without decoding whole content indiscriminately; keep aggregate counts only. Add structured version counts and persist a `format_canary` string in the existing `token-audit-headline` JSON comment in every Markdown report, with this value form: `format_canary: v1 unknown_records=N missing_usage=N cli=X` (encode multiple CLI versions deterministically). Also show a concise `FORMAT-DRIFT` notice when counts are nonzero, distinguishing no data from zero drift. Preserve current JSON and regular report behavior additively.

## Acceptance criteria

1. Synthetic known/unknown types, malformed lines, missing/valid usage and multiple/unknown versions have exact counts; no prompt text is exposed.
2. Persisted metadata round-trips for clean and drift cases; format line appears for drift and no-data is not reported as clean.
3. Benchmark against baseline and report ratio; preserve parser speed and output compatibility.

## Verification

```sh
python3 -m unittest discover -s tests -p 'test_format_canary.py' -v
python3 -m unittest discover -s tests -p 'test_usage.py' -v
python3 tests/bench_token_audit.py --baseline 28b89c6
```

## Reporting

Report files, results, limitations and baseline/after measurements where applicable. Do not commit or push.

Changelog: Report transcript format drift.

## Suggested agent / model / effort and risk

`codex-engineer` / Terra medium. Risk: **normal**.
