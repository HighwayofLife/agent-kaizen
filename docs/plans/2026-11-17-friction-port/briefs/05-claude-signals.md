# P05 Report timeout, interrupt, lock and waiting signals

## Goal

Report timeout, interrupt, lock and waiting signals. This packet is part of the Agent Kaizen friction port for 0.13.0.

- **Agent / model / effort** — `codex-dispatch` (`codex-engineer` fallback), terra, medium.
- **Risk** — normal. Use green checks and the integration batch review.
- **Group / dependencies** — B. After P03.
- **Size target** — ~335 changed lines including focused tests.
- Changelog: Report timeout, interrupt, lock and waiting signals.

## Context

`scripts/token-audit:422–493,564–736,860–963,1327–1360,1466–1493` contains redaction, result matching, counters and reports. P03 added bounded per-call events and an additive extract field. Follow its scope and privacy rules.

Use the merged 0.12.0 token-audit file and the P03 integration result. Read `AGENTS.md` and `CLAUDE.md`. Locate symbols with `tools/codemap` if available, otherwise `rg -n` and narrow `sed` ranges. All runtime changes support Python 3.9 and stdlib only. Use `python3`. Keep hard stops, captured user changes, zero-token collection and public-repo privacy; keep real logs and fixtures private.

## Scope and archive references

Owned files: `scripts/token-audit`, `tests/test_friction_signals.py`. Record the changelog line in `docs/plans/2026-11-17-friction-port/changelog/P05.md`. Coordinate a split if the diff plus tests exceeds 400 changed lines. Changes outside these paths need a separate packet or a revised scope.

Read `git show wt/p01:scripts/token-audit` around `record_usage_limit`, `finalize_friction` and the Claude scan. Check the review's wait and redaction tests in `git show wt/p01:tests/test_friction.py`, and the final literal candidate rules in `git show wt/p13:scripts/allow-rule` only as a reference. Inspect archive paths with `git show` and keep the current branch.

## Implementation and acceptance

1. Keep existing canary/error summaries and report evidenced timeouts, interrupts, precise lock phrases, usage limit and user-question waits. A hint remains labeled as such. Derive waiting upper bounds only where the timing basis calls for them. Include affected window and thresholds for flags.
2. Emit private v1 `permission_acceptance` rows keyed by exact literal (`ls`, `ls -a`, `ls -l`) and opaque canonical `--cwd` member ID with integer `accepted`, `denied`, `ambiguous` counters. Only a distinct `(session_id, tool_use_id)` with an explicit host-recorded user permission acceptance, same scoped cwd, exact parsed literal and corresponding execution counts as accepted. An execution alone or model/tool text is insufficient. An explicit denial increments denied. Conflicting, incomplete or unverified decisions increment ambiguous when the pair can be attributed; unknown provenance cannot qualify. Never combine scopes or save arbitrary command strings or raw decision text.
3. Test repeated events, acceptance without genuine host decision, execution after denial, denials/ambiguity, foreign cwd, joins across worktrees, unrelated lookalikes and count isolation per literal. Test privacy and off behavior.


## Verification

- `python3 -m unittest discover -s tests -p 'test_friction_signals.py'`
- `python3 -m unittest discover -s tests -p 'test_friction_claude.py'`
- `python3 -m unittest discover -s tests -p 'test_format_canary.py'`
- `python3 tests/bench_token_audit.py --baseline "$FRICTION_BASE" --max-ratio 1.10` after capturing the pre-edit HEAD
- `tools/ci-local --python 3.9`

## Report

Report changed files and line counts, exact checks and outcomes, known uncertainty and any blocked verification. Label measurements with baseline/conditions. Redact paths and identifiers from shared output. Leave plugin version and release CHANGELOG to P27. Do not commit or push.
