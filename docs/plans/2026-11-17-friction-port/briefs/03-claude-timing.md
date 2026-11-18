# P03 Add bounded Claude timing to the audit extract

## Goal

Add bounded Claude timing to the audit extract. This packet is part of the Agent Kaizen friction port for 0.13.0.

- **Agent / model / effort** — `codex-dispatch` (`codex-engineer` fallback), sol, medium.
- **Risk** — normal. Use green checks and the integration batch review.
- **Group / dependencies** — A1. No friction dependencies.
- **Size target** — ~365 changed lines including focused tests.
- Sol reason: A one-pass scan change must preserve bounded parsing, existing metrics and scan speed.
- Changelog: Add bounded Claude timing to the audit extract.

## Context

`scripts/token-audit:142–245` prefilters transcript rows before decoding. `:422–493,564–736` already redacts and pairs Claude tools. `:860–963,1327–1493,1501–1565` collects and emits report/extract. Preserve `collect()` compatibility with callers that pass the current options dict and with the benchmark's standalone baseline source.

Wait for 0.12.0 P06's token-audit message change. Start from the merged file and preserve the Copilot detection line. Read `AGENTS.md` and `CLAUDE.md`. Locate symbols with `tools/codemap` if available, otherwise `rg -n` and narrow `sed` ranges. All runtime changes support Python 3.9 and stdlib only. Use `python3`. Keep hard stops, captured user changes, zero-token collection and public-repo privacy; keep real logs and fixtures private.

## Scope and archive references

Owned files: `scripts/token-audit`, `tests/test_friction_claude.py`. Record the changelog line in `docs/plans/2026-11-17-friction-port/changelog/P03.md`. Coordinate a split if the diff plus tests exceeds 400 changed lines. Changes outside these paths need a separate packet or a revised scope.

Read `git show wt/p01:scripts/token-audit` at `friction_signature`, `finalize_friction`, Claude pairing and `friction_sections`, plus `git show wt/p01:tests/test_friction.py`. Adapt these parts on top of 0.12.0 canary and existing de-duplication. Inspect archive paths with `git show` and keep the current branch.

## Implementation and acceptance

1. Add a keyword/value option for collection defaulting on, CLI `--no-friction`, `--friction-slow-seconds` and `--friction-heavy-seconds`. Use session + tool-use ID in the existing traversal, bound pending rows and aggregate by redacted signature, and distinguish row-gap estimates from measured durations. Skip ambiguous pairs, duplicate transcript rows, negative gaps, starts outside the window and unmeasured prompted calls from slow-call percentiles. Version 1 extract retains its existing fields and gets optional `friction` with version 1, thresholds, summary, window definition (rolling policy and duration, or exact UTC fixed cutoff), basis and bounded flags `{id,subject,detail,value,catalog_id?}`. Add concise `## Friction` with top 5, p50/p90, sample counts and basis; keep existing report scope and usage comparable, and leave no friction keys or section when off. Keep raw command, result, prompt and path data out of summaries. Preserve `--no-write`, existing stdout consumers and format-canary results.
   - Test rolling `--days` versus fixed `--since` metadata, legacy scope unchanged, and explicit off/threshold flags in global as well as scoped invocation. Runner adapters for scheduled routes belong to P23.
2. Verify its failure and compatibility cases with the narrow checks below. Disabled/unavailable inputs must leave existing workflows usable. Keep partial changes private or gated until this packet's checks pass.
3. Confirm that the diff is confined to the owned files and that the integrated Python 3.9 check is green.

## Verification

- `python3 -m unittest discover -s tests -p 'test_friction_claude.py'`
- `python3 -m unittest discover -s tests -p 'test_format_canary.py'`
- `python3 -m unittest discover -s tests -p 'test_usage.py'`
- `python3 tests/bench_token_audit.py --baseline "$FRICTION_BASE" --max-ratio 1.10` after `FRICTION_BASE=$(git rev-parse HEAD)` before edits
- `tools/ci-local --python 3.9`

## Report

Report changed files and line counts, exact checks and outcomes, known uncertainty and any blocked verification. Label measurements with baseline/conditions. Redact paths and identifiers from shared output. Leave plugin version and release CHANGELOG to P27. Do not commit or push.
