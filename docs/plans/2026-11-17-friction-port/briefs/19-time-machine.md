# P19 Support verified sticky Time Machine exclusion and reversal

## Goal

Support verified sticky Time Machine exclusion and reversal. This packet is part of the Agent Kaizen friction port for 0.13.0.

- **Agent / model / effort** — `codex-dispatch` (`codex-engineer` fallback), sol, high.
- **Risk** — high. Get a per-packet verifier and Sol high review before merge. Obtain security review before landing.
- **Group / dependencies** — G. After P15b.
- **Size target** — ~365 changed lines including focused tests.
Sol reason: The native path-based operation must stay bound to one eligible directory through apply and undo.
- Changelog: Support verified sticky Time Machine exclusion and reversal.

Owner decision O2 and live gate S3 apply before native exclusions become live.

## Context

`docs/autonomy.md:56–82` requires a reversible action. P15 owns the private host-fix record, directory identity, nested policy and existing-marker behavior. The catalogue describes `timemachine-output`; action records and probe/LLM input cannot supply commands. The archived owner approved sticky Time Machine exclusions in scheduled auto through a wrapper.

Use the 0.12.0 integration base for landing. The references above are from 0.11.0 main at d8a4cb7. Read `AGENTS.md` and `CLAUDE.md`. Locate symbols with `tools/codemap` if available, otherwise `rg -n` and narrow `sed` ranges. All runtime changes support Python 3.9 and stdlib only. Use `python3`. Keep hard stops, captured user changes, zero-token collection and public-repo privacy; keep real logs and fixtures private.

## Scope and archive references

Owned files: `scripts/host-fix`, `tests/test_host_fix.py`. Record the changelog line in `docs/plans/2026-11-17-friction-port/changelog/P19.md`. Keep the scoped diff and tests within the assigned cap. Changes outside these paths need a separate packet or a revised scope.

Read `git show wt/p12:scripts/host-fix` at `fixed_apply`, `fixed_undo`, `run_argv` and relevant `apply`/`undo` sections. Review race cases in `git show wt/p12:tests/test_host_fix.py`. Reuse only the fixed sticky semantics and bounded test harness. Inspect archive paths with `git show` and keep the current branch.

## Implementation and acceptance

1. On real macOS, prove a no-root fixed `tmutil isexcluded`/`addexclusion`/`removeexclusion` path flow for the same validated directory with a reliable identity-bound invocation or equivalent safety guarantee. A before/after pathname stat by itself does not prove binding across rename. If proof holds, support `host-fix apply --project DIR --catalog-id timemachine-output --path DIR` via its existing scoped private record and verify `[Included]` before, `[Excluded]` after, identical target identity and safe rollback on failure. Undo removes only a recorded state transition on the same target and checks the result. Folder recreation is a flap/user action. No fixed-path `-p`, privilege elevation, arbitrary executable or existing/system-wide policy changes. If no safe verified path is available, implement the refusal and keep the catalogue user step under settled O2. Use the same tool-owned action-ID recovery binding as the Linux path. Test refusal/identity replacement and retry at each phase; report actual OS proof separately from stubbed unit tests.
2. Verify its failure and compatibility cases with the narrow checks below. Disabled/unavailable inputs must leave existing workflows usable. Keep partial changes private or gated until this packet's checks pass.
3. Secure an explicit security review before landing. Show the reviewer the independent scope validation, safe refusals, operation journal and undo/recovery checks.

## Verification

- `python3 -m unittest discover -s tests -p 'test_host_fix.py'`
- `python3 -m unittest discover -s tests -p 'test_friction_catalog.py'`
- `python3 scripts/host-fix --help`
- `tools/ci-local --python 3.9`

## Report

Report changed files and line counts, exact checks and outcomes, known uncertainty and any blocked verification. Label measurements with baseline/conditions. Redact paths and identifiers from shared output. Leave plugin version and release CHANGELOG to P27. Do not commit or push.
