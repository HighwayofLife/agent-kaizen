# 10: Register scripts and release 0.11.0

## Goal and why

Verify copy and linked installations and run the mandatory real-input release gate for 0.11.0.

## Context

Each script-creating packet already registers its helper in `scripts/kaizen-link` SCRIPTS and `scripts/install-schedule` MANAGED_NAMES. `tests/test_kaizen_link.py:121` enforces registration. OS scheduling remains useful when sessions are infrequent or audits must run on a fixed schedule.

## Constraints
Read `AGENTS.md`. Python 3.9 stdlib only; scripts under `scripts/` are executable and answer `--help`. Hooks use macOS bash 3.2, shellcheck, bounded work and exit 0 even on errors; an intentional denial is JSON with exit 0. Do not edit `.github/workflows/ci.yml`. Use `rg -n` and narrow `sed` ranges (no `tools/codemap` exists). This release packet alone edits version and CHANGELOG on the unpublished integration branch. Skills require quoted description, matching name, `disable-model-invocation: true`, and README table row. Never commit or push. Stop and report wrong assumptions or if the packet exceeds ~400 changed lines; do not drop criteria.

## Scope / do not touch

Edit `scripts/README.md`, `skills/schedule/SKILL.md`, `tests/test_kaizen_link.py`, `tests/test_schedule.py`, `tests/test_install_schedule.py`, `scripts/rules-lint.patterns`, `tests/test_rules_lint.py`, `.claude-plugin/plugin.json`, `CHANGELOG.md`, `README.md`, `docs/scheduling.md`, and this plan Results. Verify registration and copy/linked installs; do not change registration lists or feature implementations.

## Steps

Verify helpers in copy and linked installs. Document `usage-db report --cache`, `usage-db guard`, `token-audit --no-write`, and their help/exit semantics in scripts README. Update schedule skill: the OS job is optional and remains useful for fixed schedules or infrequent interactive sessions. Document SessionStart autoAudit and retention. Fix superseded scheduler wording and add stale rules/tests only for wording that is actually false. Set version 0.11.0 and dated changelog from packet bullets. Execute all mandatory owner-run real-input commands listed below, keep output local, and record only sanitized statuses and timings in Results. No network or model review.

## Acceptance criteria

1. Copy and linked installs find all helpers and run demo; both registration lists already contain all new scripts.
2. Docs, skill, version and changelog agree; no automatic model review.
3. Every real-input gate below is run and its expected outcome verified. If input or required tools are unavailable, mark gate blocked; do not claim release complete. Output stays local and is never committed.
4. Release checks pass on Python 3.9; report missing tools without installing.

## Verification

```sh
python3 -m unittest discover -s tests -p 'test_kaizen_link.py' -v
python3 -m unittest discover -s tests -p 'test_schedule.py' -v
python3 -m unittest discover -s tests -p 'test_install_schedule.py' -v
python3 -m unittest discover -s tests -p 'test_repo.py' -v
python3 -m unittest discover -s tests -p 'test_rules_lint.py' -v
scripts/kaizen-scan --demo
tools/ci-local --python 3.9
claude plugin validate .
```

Owner runs on real local input, with outputs kept local:

- `time scripts/kaizen-scan`: scorecard and actionable finding or explicit insufficient data; record elapsed time only.
- `scripts/kaizen-doctor`: actionable PASS/WARN/FAIL; no state writes.
- `scripts/usage-db report --cache`: cache buckets and rewrite counts or explicit no data.
- `scripts/usage-db guard`: regression lines or explicit no regression/insufficient data.
- `scripts/token-audit`: report path; inspect its persisted `format_canary: v1` line locally, including drift/no-data state.
- `hooks/tier-guard.sh < tests/fixtures/hooks/pretooluse_agent.json`: with a scratch guardrails config and a matching exhausted allowance, exit 0 and JSON deny with reason; test allowed request too.
- `hooks/session-audit.sh < tests/fixtures/hooks/sessionstart.json`: with isolated scratch config and stubbed audit, exits 0 silently; due run writes success state and a second start skips it. Check child completion and cleanup locally.

Set `CLAUDE_CONFIG_DIR` to the scratch directory for the last two commands; prepare fixture config and stub executable there. Never paste local paths or report contents into tracked files.

## Reporting

Report files, results, limitations and baseline/after measurements where applicable. Do not commit or push.

Changelog: Release 0.11.0 with the first-five-minutes loop.

## Suggested agent / model / effort and risk

`codex-engineer` / Terra medium. Risk: **normal**.
