# P09 Pair Codex calls and outputs within the existing scan

## Goal

Pair Codex calls and outputs within the existing scan. This packet is part of the Agent Kaizen friction port for 0.13.0.

- **Agent / model / effort** — `codex-dispatch` (`codex-engineer` fallback), sol, medium.
- **Risk** — normal. Use green checks and the integration batch review.
- **Group / dependencies** — C. After P03.
- **Size target** — ~340 changed lines including focused tests.
- Sol reason: Codex call/output admission shares the single-pass format and accounting fast path.
- Changelog: Pair Codex calls and outputs within the existing scan.

## Context

`scripts/token-audit:83–134,142–245,748–859` includes record canary, fast-path admission, cutoff and Codex scope. Current Codex scanning prices `token_count`; error and tool fallbacks must leave that unchanged. P05 defines normalized friction events.

Use the merged 0.12.0 token-audit file and the P05 integration result. Read `AGENTS.md` and `CLAUDE.md`. Locate symbols with `tools/codemap` if available, otherwise `rg -n` and narrow `sed` ranges. All runtime changes support Python 3.9 and stdlib only. Use `python3`. Keep hard stops, captured user changes, zero-token collection and public-repo privacy; keep real logs and fixtures private.

## Scope and archive references

Owned files: `scripts/token-audit`, `tests/test_friction_codex.py`, `tests/bench_token_audit.py`. Record the changelog line in `docs/plans/2026-11-17-friction-port/changelog/P09.md`. Coordinate a split if the diff plus tests exceeds 400 changed lines. Changes outside these paths need a separate packet or a revised scope.

Read `git show wt/p04:scripts/token-audit` at `codex_call_row`, `scan_codex` and raw row admission. Compare `git show wt/p07:scripts/token-audit` at `codex_fields`/`codex_call_row` for bounded text extraction. Use `git show wt/p04:tests/test_friction.py` for call/response fixtures. Inspect archive paths with `git show` and keep the current branch.

## Implementation and acceptance

1. Pair by call ID within rollout, in matching cwd and window. Admit only recognized call/output rows through the same file traversal; parse command metadata under current byte budget and limit output evidence to the first 400 bytes, without decoding output bodies or reopening the file. Handle missing IDs, legacy envelopes, multi-turn overlap, malformed/unmatched/truncated/duplicate rows and cross-window pairs without fabricating duration. Label explicit finite wall time as measured. Count bounded timeout/lock/inotify signal evidence even when duration is missing. Preserve model, effort, totals and raw canary conventions. Extend `tests/bench_token_audit.py` fixture with call and large output rows while preserving comparisons across the pre-friction base; keep default and off paths independently inspectable.
2. Verify its failure and compatibility cases with the narrow checks below. Disabled/unavailable inputs must leave existing workflows usable. Keep partial changes private or gated until this packet's checks pass.
3. Confirm that the diff is confined to the owned files and that the integrated Python 3.9 check is green.

## Verification

- `python3 -m unittest discover -s tests -p 'test_friction_codex.py'`
- `python3 -m unittest discover -s tests -p 'test_friction_signals.py'`
- `python3 -m unittest discover -s tests -p 'test_format_canary.py'`
- `python3 -m unittest discover -s tests -p 'test_usage.py'`
- `python3 tests/bench_token_audit.py --baseline "$FRICTION_BASE" --max-ratio 1.10` versus a pre-edit HEAD and again versus the pre-friction 0.12.0 integration base
- `tools/ci-local --python 3.9`

## Report

Report changed files and line counts, exact checks and outcomes, known uncertainty and any blocked verification. Label measurements with baseline/conditions. Redact paths and identifiers from shared output. Leave plugin version and release CHANGELOG to P27. Do not commit or push.
