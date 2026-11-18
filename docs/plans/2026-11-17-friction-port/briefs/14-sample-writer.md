# P14 Sample Bash timing and host load in a bounded asynchronous hook

## Goal

Sample Bash timing and host load in a bounded asynchronous hook. This packet is part of the Agent Kaizen friction port for 0.13.0.

- **Agent / model / effort** — `codex-dispatch` (`codex-engineer` fallback), sol, high.
- **Risk** — high. Get a per-packet verifier and Sol high review before merge.
- **Group / dependencies** — B. After P00, P02.
- **Size target** — ~300 changed lines including focused tests.
- Sol reason: Concurrent writers must preserve private file identity, cap and hook deadline.
- Changelog: Sample Bash timing and host load in a bounded asynchronous hook.

Sampler release gate S1 applies before default-on registration.

## Context

`hooks/hooks.json:29–50` gives synchronous Bash nudges on PostToolUse and PostToolUseFailure. `hooks/bash-burst.sh:8–45` returns context and cannot become async. `tools/context_budget.py:83–111` requires each registered hook's literal inventory and hash. `scripts/kaizen-scheduled:1231–1412` owns retention. Use the 0.12.0 host adapter's detection precedence and test `audit-notice`, `bash-burst` and default startup fixtures unchanged.

Wait for 0.12.0 P01, P02 and P05, and for the resolved host choice (including C1 if it lands). Re-read exact discovery and host detection before registering the new hook. Read `AGENTS.md` and `CLAUDE.md`. Locate symbols with `tools/codemap` if available, otherwise `rg -n` and narrow `sed` ranges. All runtime changes support Python 3.9 and stdlib only. Use `python3`. Keep hard stops, captured user changes, zero-token collection and public-repo privacy; keep real logs and fixtures private.

## Scope and archive references

Owned files: `scripts/kaizen_friction_sample.py`, `tests/test_friction_sampler.py`. Record the changelog line in `docs/plans/2026-11-17-friction-port/changelog/P14.md`. Keep the scoped diff and tests within the assigned cap. Changes outside these paths need a separate packet or a revised scope.

Read `git show wt/p07:hooks/friction-sample.sh`, `git show wt/p07:hooks/hooks.json` and `git show wt/p07:tests/test_friction_hook.py`. Reuse record layout, optional fields and test shapes. Replace the archived size/stat/append and process-stamp races. Inspect archive paths with `git show` and keep the current branch.

## Implementation and acceptance

1. Add an unregistered stdlib worker and tiny silent launch entry point through the Python module. Apply the 0.12.0 host precedence (`KAIZEN_HOST`, then Copilot root, then Codex root, then Claude) and global `enabled`/`frictionSampler`. Accept bounded completed Claude Bash PostToolUse input with optional finite nonnegative duration and narrow session/tool IDs, load1 and core count. Append the six-field UTC-day record only.
2. Use owner-private no-symlink storage, a nonblocking local lock, exact 5 MiB cap under the lock and one O_APPEND write per record under 4 KiB. Time-budgeted silent skips keep the hook usable under contention. Prove invalid/large input, off, non-Claude, cap, lock busy, partial write and symlink refusal. P00 pre-registers the module. P14b adds rate-limited process rows. P14c owns live registration, retention, `tools/host-probe`, `tests/test_host_probe.py` and their Codex discovery check.


## Verification

- `python3 -m unittest discover -s tests -p 'test_friction_sampler.py'`
- `python3 -m unittest discover -s tests -p 'test_kaizen_link.py'`
- `tools/ci-local --python 3.9`


## Report

Report changed files and line counts, exact checks and outcomes, known uncertainty and any blocked verification. Label measurements with baseline/conditions. Redact paths and identifiers from shared output. Leave plugin version and release CHANGELOG to P27. Do not commit or push.
