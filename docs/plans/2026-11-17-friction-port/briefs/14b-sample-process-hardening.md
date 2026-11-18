# P14b Bound and harden sampler process snapshots

## Goal

Bound and harden sampler process snapshots. This packet is part of the Agent Kaizen friction port for 0.13.0.

- **Agent / model / effort** — `codex-dispatch` (`codex-engineer` fallback), sol, high.
- **Risk** — high. Get a per-packet verifier and Sol high review before merge.
- **Group / dependencies** — D. After P01b, P14.
- **Size target** — ~255 changed lines including focused tests.
- Sol reason: Rate claims across concurrent hooks and process teardown must preserve the sampling deadline.
- Changelog: Bound and harden sampler process snapshots.

Sampler release gate S1 applies before default-on registration.

## Context

`hooks/hooks.json:29–50` gives synchronous Bash nudges on PostToolUse and PostToolUseFailure. `hooks/bash-burst.sh:8–45` returns context and cannot become async. `tools/context_budget.py:83–111` requires each registered hook's literal inventory and hash. `scripts/kaizen-scheduled:1231–1412` owns retention. Use the 0.12.0 host adapter's detection precedence and test `audit-notice`, `bash-burst` and default startup fixtures unchanged.

Wait for 0.12.0 P01, P02 and P05, and for the resolved host choice (including C1 if it lands). Re-read exact discovery and host detection before registering the new hook. Read `AGENTS.md` and `CLAUDE.md`. Locate symbols with `tools/codemap` if available, otherwise `rg -n` and narrow `sed` ranges. All runtime changes support Python 3.9 and stdlib only. Use `python3`. Keep hard stops, captured user changes, zero-token collection and public-repo privacy; keep real logs and fixtures private.

## Scope and archive references

Owned files: `scripts/kaizen_friction_sample.py`, `tests/test_friction_sampler.py`. Record the changelog line in `docs/plans/2026-11-17-friction-port/changelog/P14b.md`. Keep the scoped diff and tests within the assigned cap. Changes outside these paths need a separate packet or a revised scope.

Read `git show wt/p07:hooks/friction-sample.sh`, `git show wt/p07:hooks/hooks.json` and `git show wt/p07:tests/test_friction_hook.py`. Reuse record layout, optional fields and test shapes. Replace the archived size/stat/append and process-stamp races. Inspect archive paths with `git show` and keep the current branch.

## Implementation and acceptance

1. Add the optional `P` UTC timestamp/load/cores/basename row only at load1 ≥ cores, at most once per five minutes. Use the existing append lock for the claim and cap accounting. Release it before polling processes. Enforce a monotonic <=250 ms worker deadline and kill surviving process-query children. Store only catalogued basenames.
2. Resolve the catalogue beside the script using the runner's `sibling()` pattern, preferring `kaizen-friction-catalog.json` and falling back to `friction-catalog.json`. Test a copied worker with only the installed name. Missing/unknown input suppresses process rows; timing samples continue.
3. Test competing claims, failed process query, malformed and truncated output, cancellation and rollover. The worker stays unregistered until P14c lands retention and manifest/discovery checks together.


## Verification

- `python3 -m unittest discover -s tests -p 'test_friction_sampler.py'`
- `tools/ci-local --python 3.9`


## Report

Report changed files and line counts, exact checks and outcomes, known uncertainty and any blocked verification. Label measurements with baseline/conditions. Redact paths and identifiers from shared output. Leave plugin version and release CHANGELOG to P27. Do not commit or push.
