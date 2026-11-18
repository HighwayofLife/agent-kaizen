# P18 Add and revoke evidence-backed exact Claude project allow rules

## Goal

Add and revoke evidence-backed exact Claude project allow rules. This packet is part of the Agent Kaizen friction port for 0.13.0.

- **Agent / model / effort** — `codex-dispatch` (`codex-engineer` fallback), sol, high.
- **Risk** — high. Get a per-packet verifier and Sol high review before merge. Obtain security review before landing.
- **Group / dependencies** — E. After P05.
- **Size target** — ~380 changed lines including focused tests.
Sol reason: Persistent permissions require live exact matching and user acceptance provenance.
- Changelog: Add and revoke evidence-backed exact Claude project allow rules.

Owner decision O1 and live gate S2 apply before writes become live.

## Context

`scripts/kaizen-scheduled:139–156,970–1046,1187–1220` establishes empty general Bash allows and strong config/credential denies. `scripts/token-audit:1466–1560` writes v1 extracts with project filter names separate from real `scope.cwd`; P05 adds fixed command prompt-evidence counters. Read `docs/hosts.md` on the 0.12.0 base and honor its non-Claude proposal-only rule.

Use 0.12.0's `docs/hosts.md` rule. Complete live Claude exact-rule proof before allowing writes. Read `AGENTS.md` and `CLAUDE.md`. Locate symbols with `tools/codemap` if available, otherwise `rg -n` and narrow `sed` ranges. All runtime changes support Python 3.9 and stdlib only. Use `python3`. Keep hard stops, captured user changes, zero-token collection and public-repo privacy; keep real logs and fixtures private.

## Scope and archive references

Owned files: `scripts/allow-rule`, `tests/test_allow_rule.py`. Record the changelog line in `docs/plans/2026-11-17-friction-port/changelog/P18.md`. Keep the scoped diff and tests within the assigned cap. Changes outside these paths need a separate packet or a revised scope.

Read `git show wt/p13:scripts/allow-rule` at `validate_head`, `find_extract`, `check_evidence`, `add`, `undo` and p13c cases via `git show wt/p13:tests/test_allow_rule.py`. Reuse its bounded, strictly project-scoped evidence, merge and refusal patterns. Discard its prefix wildcard and denylist-first authority. Inspect archive paths with `git show` and keep the current branch.

## Implementation and acceptance

1. Add `allow-rule add --project DIR --command COMMAND` and an undo interface whose writes stay dark until P18b. Require current Claude live exact matching and deny precedence for fixed literals `ls`, `ls -a`, `ls -l`, the settled O1 vocabulary. The sole target is canonical project `.claude/settings.local.json`. Test extra operands, quoting, globs, redirects, chained commands, substitution and precedence. Keep proposal-only if runtime proof fails.
2. Require fresh (within seven days) v1 scoped `--cwd` evidence containing at least ten distinct, verified user acceptances for that exact literal in one canonical scope member of the enrolled project. Never combine counters across literals/worktree roots; deny or ambiguous observations for the selected literal/scope fail closed, and an unknown schema, global, substring, foreign or stale extract cannot qualify. Test ten acceptances, nine plus one denial, ten plus denial, ambiguous or repeated events, and ten split across roots. Use P00's installed name.
3. Seed the exact local rule in a disposable test fixture while the write path is still dark, exercise a fresh installed scheduled propose-only run and a separate auto run. Confirm effective no general Bash access, existing denies/approved helpers, and that the new local literal has not escaped the runner boundary. Repeat after real CLI apply in P18b/P28.
4. Obtain security review before landing. Validate no-write refusals and preparation of the narrow structured operation separately from P18b's recovery.

## Verification

- `python3 -m unittest discover -s tests -p 'test_allow_rule.py'`
- `python3 -m unittest discover -s tests -p 'test_friction_signals.py'`
- `python3 -m unittest discover -s tests -p 'test_schedule_security.py'`
- `python3 -m unittest discover -s tests -p 'test_kaizen_link.py'`
- `tools/ci-local --python 3.9`

## Report

Report changed files and line counts, exact checks and outcomes, known uncertainty and any blocked verification. Label measurements with baseline/conditions. Redact paths and identifiers from shared output. Leave plugin version and release CHANGELOG to P27. Do not commit or push.
