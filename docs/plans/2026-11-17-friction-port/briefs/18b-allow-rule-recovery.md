# P18b Harden exact grant transactions and removal-only undo

## Goal

Harden exact grant transactions and removal-only undo. This packet is part of the Agent Kaizen friction port for 0.13.0.

- **Agent / model / effort** — `codex-dispatch` (`codex-engineer` fallback), sol, high.
- **Risk** — high. Get a per-packet verifier and Sol high review before merge. Obtain security review before landing.
- **Group / dependencies** — F. After P18.
- **Size target** — ~390 changed lines including focused tests.
- Sol reason: Locked settings transactions and ownership-preserving undo change persistent permissions.
- Changelog: Harden exact grant transactions and removal-only undo.

Owner decision O1 and live gate S2 apply before writes become live.

## Context

`scripts/kaizen-scheduled:139–156,970–1046,1187–1220` establishes empty general Bash allows and strong config/credential denies. `scripts/token-audit:1466–1560` writes v1 extracts with project filter names separate from real `scope.cwd`; P05 adds fixed command prompt-evidence counters. Read `docs/hosts.md` on the 0.12.0 base and honor its non-Claude proposal-only rule.

Use 0.12.0's `docs/hosts.md` rule. Complete live Claude exact-rule proof before allowing writes. Read `AGENTS.md` and `CLAUDE.md`. Locate symbols with `tools/codemap` if available, otherwise `rg -n` and narrow `sed` ranges. All runtime changes support Python 3.9 and stdlib only. Use `python3`. Keep hard stops, captured user changes, zero-token collection and public-repo privacy; keep real logs and fixtures private.

## Scope and archive references

Owned files: `scripts/allow-rule`, `tests/test_allow_rule.py`. Record the changelog line in `docs/plans/2026-11-17-friction-port/changelog/P18b.md`. Keep the scoped diff and tests within the assigned cap. Changes outside these paths need a separate packet or a revised scope.

Read `git show wt/p13:scripts/allow-rule` at `validate_head`, `find_extract`, `check_evidence`, `add`, `undo` and p13c cases via `git show wt/p13:tests/test_allow_rule.py`. Reuse its bounded, strictly project-scoped evidence, merge and refusal patterns. Discard its prefix wildcard and denylist-first authority. Inspect archive paths with `git show` and keep the current branch.

## Implementation and acceptance

1. Under a project settings lock and no-follow checks, merge only the evidenced literal with guarded atomic write, durable pending state, then verified terminal record. Preserve unrelated keys and denies. Undo only the exact recorded managed rule, preserve unrelated edits and pre-existing rules, and remove a tool-created file only if it still contains solely managed data. Handle prior revocation idempotently. Scheduled undo stays unavailable.
2. Inject failure before/after write, journal loss/forgery, path swap, settings replacement and concurrent operations; retry without duplicate grant or provenance adoption. Enable the write only after P18's live matching evidence and these checks pass. Review the matched runtime rule as well as the JSON diff. Repeat the fresh scheduled propose-only and auto boundary check after applying through the installed CLI.
3. Accept the runner’s private action-ID transaction key only through its fixed internal invocation. Bind it to tool-owned state so P24 can reconcile after the effect, and refuse a conflicting key/scope without changes. Preserve direct interactive record/undo behavior.
4. Obtain security review before landing. The archive is 329 source + 692 test lines; replace the prefix and duplicate tests with focused fixtures for literal evidence, provenance and recovery across P18/P18b.

## Verification

- `python3 -m unittest discover -s tests -p 'test_allow_rule.py'`
- `python3 -m unittest discover -s tests -p 'test_friction_signals.py'`
- `python3 -m unittest discover -s tests -p 'test_schedule_security.py'`
- `tools/ci-local --python 3.9`

## Report

Report changed files and line counts, exact checks and outcomes, known uncertainty and any blocked verification. Label measurements with baseline/conditions. Redact paths and identifiers from shared output. Leave plugin version and release CHANGELOG to P27. Do not commit or push.
