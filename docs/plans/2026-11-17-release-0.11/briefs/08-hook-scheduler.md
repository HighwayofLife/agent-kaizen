# 08: Asynchronous lifecycle scheduling

## Goal and why

Run the existing local audit loop asynchronously at session start without requiring an OS job.

## Context

`scripts/kaizen-scheduled` uses `<Claude config dir>/audits/.lock`, `audit_steps`, `_run_audit` / `_run_token_audit`, and `run_usage_db`; `_run_audit` already ingests the existing database. `tests/fixtures/hooks/sessionstart.json` is synthetic input; read it, do not create it. The registered SessionStart command hook uses `"async": true`; CLI timeout values are seconds and are not enforced for async workers.

## Constraints
Read `AGENTS.md`. Python 3.9 stdlib only; scripts under `scripts/` are executable and answer `--help`. Hooks use macOS bash 3.2, shellcheck, bounded work and exit 0 even on errors; an intentional denial is JSON with exit 0. Do not edit `.github/workflows/ci.yml`. Use `rg -n` and narrow `sed` ranges (no `tools/codemap` exists). Propose a changelog bullet; on each packet landing the integrator bumps the manifest and adds a dated changelog entry before checks, as required by AGENTS.md. Do not edit these shared files in parallel worktrees. Skills require quoted description, matching name, `disable-model-invocation: true`, and README table row. Never commit or push. Stop and report wrong assumptions or if the packet exceeds ~400 changed lines; do not drop criteria.

## Scope / do not touch

Edit `hooks/hooks.json`, `scripts/kaizen-scheduled`, `tools/context-budget.json`, `docs/scheduling.md`; create `hooks/session-audit.sh`, `tests/test_hook_schedule.py`. Read the SessionStart fixture. Do not add SessionEnd, change usage-db, or edit audit-notice.

## Steps

Register one async SessionStart command naming exactly one `hooks/session-audit.sh`; it prints nothing and its inventory maximum is zero. Read global `<Claude config dir>/agent-kaizen.json` key `autoAudit`, default true; false opts out. Worker acquires existing global lock once, checks due state inside it, and when no successful audit exists or it is older than three days runs the existing all-project `_run_audit` path (including checks and usage-db ingest), without model review. Per-project checks apply only to enrolled projects; new-user immediate value comes from `kaizen-scan`. Use existing scheduler subprocess timeout/process-group cleanup to enforce a worker deadline and clean up its child; if this exceeds about 400 changed lines, stop and split hook registration from due-state worker while keeping each slice working; async hook timeout alone does not enforce one. Store `last_audit_ok` as UTC ISO in `<audits>/auto-audit-state.json` using temp file plus `os.replace` under the same lock only when an unscoped audit exits 0 and its report exists. Failed or scoped runs do not update it; retry next session. A pre-existing database is appended to as by the OS job; document database/report locations and deletion, and config/opt-out in scheduling documentation. Preserve existing schedule behavior.

## Acceptance criteria

1. Due, fresh, absent, malformed, disabled, failed, missing-report and scoped cases work; failure/scoped state is unchanged and a subsequent session retries. Concurrent starts run at most one due audit under the global lock.
2. Hook prints nothing, uses only SessionStart async registration and reads the fixture; worker deadline kills child and error cases fail open.
3. All-project audit and ingest, enrolled-project checks, pre-existing database preservation, opt-out, and storage/deletion documentation are tested or verified. Update inventory and run its check.

## Verification

```sh
python3 -m unittest discover -s tests -p 'test_hook_schedule.py' -v
python3 -m unittest discover -s tests -p 'test_schedule_usage_db.py' -v
python3 -m unittest discover -s tests -p 'test_hooks.py' -v
shellcheck -S warning hooks/session-audit.sh
python3 tools/context_budget.py --root .
scripts/kaizen-scheduled --help
```

## Reporting

Report files, results, limitations and baseline/after measurements where applicable. Do not commit or push.

Changelog: Run local audits from SessionStart.

## Suggested agent / model / effort and risk

`codex-engineer` / Sol high (concurrency and subprocess lifecycle). Risk: **high**.
