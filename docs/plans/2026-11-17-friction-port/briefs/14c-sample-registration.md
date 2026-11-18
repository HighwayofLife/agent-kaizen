# P14c Register the bounded sampler with retention and host checks

## Goal

Register the bounded sampler with retention and host checks. This packet is part of the Agent Kaizen friction port for 0.13.0.

- **Agent / model / effort** — `codex-dispatch` (`codex-engineer` fallback), terra, medium.
- **Risk** — normal. Use green checks and the integration batch review.
- **Group / dependencies** — F. After P14b.
- **Size target** — ~390 changed lines including focused tests.
- Changelog: Register the bounded sampler with retention and host checks.

Sampler release gate S1 applies before default-on registration.

## Context

`hooks/hooks.json:29–50` gives synchronous Bash nudges on PostToolUse and PostToolUseFailure. `hooks/bash-burst.sh:8–45` returns context and cannot become async. `tools/context_budget.py:83–111` requires each registered hook's literal inventory and hash. `scripts/kaizen-scheduled:1231–1412` owns retention. Use the 0.12.0 host adapter's detection precedence and test `audit-notice`, `bash-burst` and default startup fixtures unchanged.

Wait for 0.12.0 P01, P02 and P05, and for the resolved host choice (including C1 if it lands). Re-read exact discovery and host detection before registering the new hook. Read `AGENTS.md` and `CLAUDE.md`. Locate symbols with `tools/codemap` if available, otherwise `rg -n` and narrow `sed` ranges. All runtime changes support Python 3.9 and stdlib only. Use `python3`. Keep hard stops, captured user changes, zero-token collection and public-repo privacy; keep real logs and fixtures private.

## Scope and archive references

Owned files: `hooks/friction-sample.sh`, `hooks/hooks.json`, `scripts/kaizen-scheduled`, `tools/context-budget.json`, `tools/host-probe`, `tests/test_friction_sampler.py`, `tests/test_housekeep.py`, `tests/test_host_probe.py`. Record the changelog line in `docs/plans/2026-11-17-friction-port/changelog/P14c.md`. Keep the scoped diff and tests within the assigned cap. Changes outside these paths need a separate packet or a revised scope.

Read `git show wt/p07:hooks/friction-sample.sh`, `git show wt/p07:hooks/hooks.json` and `git show wt/p07:tests/test_friction_hook.py`. Reuse record layout, optional fields and test shapes. Replace the archived size/stat/append and process-stamp races. Inspect archive paths with `git show` and keep the current branch.

## Implementation and acceptance

1. Add the silent async command under the existing Bash PostToolUse matcher after live S1/S5 verification on a disposable install. Existing sync nudges and event output remain intact. Scope sampling to successful PostToolUse only. Timeout/failure signals remain transcript-derived; keep PostToolUseFailure unchanged. Update only the new context-budget entry with zero literal bytes and `shasum -a 256 hooks/friction-sample.sh`.
2. By `git show multi-host:tools/host-probe` and `git show multi-host:tests/test_host_probe.py`, the four baseline Codex events are exact. Keep those required. Pin the extra sampler registration if observed (five total, two PostToolUse) or the verified omission (four total). Identify its command where exposed, reject unexpected extras/missing baseline, and test that Codex/Copilot execute no sampling. This change and its narrow host-probe test are required for the 0.12.0 `ci-local` host-probe stage. If the shared manifest breaks a supported host, keep the registration dark.
3. Add `samples` retention of 14 UTC days / 50 MiB through the existing retention planner. Protect the live UTC day and lock file, re-check identity and concurrent writers at apply. Check `retentionOverrides` via `tests/test_runner.py`. Run 50 warmed on/off measurements via the opt-in benchmark and report p50/p95 and installed Claude tool-return delta (<=10 ms added median). Compare to the same synchronous 0.12.0 nudge path. No synchronous process query.


## Verification

- `python3 -m unittest discover -s tests -p 'test_friction_sampler.py'`
- `python3 -m unittest discover -s tests -p 'test_housekeep.py'`
- `python3 -m unittest discover -s tests -p 'test_runner.py'`
- `python3 -m unittest discover -s tests -p 'test_host_probe.py'`
- `python3 -m unittest discover -s tests -p 'test_hooks.py'`
- `python3 -m unittest discover -s tests -p 'test_hook_schedule.py'`
- `python3 -m unittest discover -s tests -p 'test_doctor.py'`
- `shellcheck -S warning hooks/friction-sample.sh hooks/bash-burst.sh`
- `python3 -m json.tool hooks/hooks.json >/dev/null`
- `python3 tools/context_budget.py --root .`
- `python3 tests/test_friction_sampler.py --bench`
- `tools/host-probe --host codex --worktree`
- `tools/ci-local --python 3.9`


## Report

Report changed files and line counts, exact checks and outcomes, known uncertainty and any blocked verification. Label measurements with baseline/conditions. Redact paths and identifiers from shared output. Leave plugin version and release CHANGELOG to P27. Do not commit or push.
