# 04a: No-write audit mode

## Goal and why

Add the no-write audit contract used by the first scan.

## Context

`scripts/token-audit:1336-1410` always writes report/extract today; packet 03 adds cache data. `scripts/kaizen-demo-fixtures` generates a temporary synthetic tree. `README.md:80-95,196` contains install and skill table.

## Constraints
Read `AGENTS.md`. Python 3.9 stdlib only; scripts under `scripts/` are executable and answer `--help`. Hooks use macOS bash 3.2, shellcheck, bounded work and exit 0 even on errors; an intentional denial is JSON with exit 0. Do not edit `.github/workflows/ci.yml`. Use `rg -n` and narrow `sed` ranges (no `tools/codemap` exists). Propose a changelog bullet; on each packet landing the integrator bumps the manifest and adds a dated changelog entry before checks, as required by AGENTS.md. Do not edit these shared files in parallel worktrees. Skills require quoted description, matching name, `disable-model-invocation: true`, and README table row. Never commit or push. Stop and report wrong assumptions or if the packet exceeds ~400 changed lines; do not drop criteria.

## Scope / do not touch

Edit `scripts/token-audit` and `tests/test_usage.py` only. Do not add a scan, skill, or registration.

## Steps

Add `token-audit --no-write` with `--json` returning the same structured data but null report/extract paths and no mkdir/write, including error paths. Keep existing JSON behavior unchanged without the flag.

## Acceptance criteria

1. Existing JSON remains compatible; no-write paths are null and no reports or extracts are created, including on errors.
2. Snapshot isolated Claude and Codex config roots before and after. Compare benchmark before/after.

## Verification

```sh
python3 -m unittest discover -s tests -p 'test_usage.py' -v
python3 tests/bench_token_audit.py --baseline 28b89c6
```

## Reporting

Report files, results, limitations and baseline/after measurements where applicable. Do not commit or push.

Changelog: Add a no-write audit mode.

## Suggested agent / model / effort and risk

`codex-engineer` / Terra medium. Risk: **normal**.
