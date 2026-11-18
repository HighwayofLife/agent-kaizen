# P24b Record brokered effects and resolve undo by scoped action ID

## Goal

Record brokered effects and resolve undo by scoped action ID. This packet is part of the Agent Kaizen friction port for 0.13.0.

- **Agent / model / effort** — `codex-dispatch` (`codex-engineer` fallback), sol, high.
- **Risk** — high. Get a per-packet verifier and Sol high review before merge. Obtain security review before landing.
- **Group / dependencies** — K. After P24a, P23.
- **Size target** — ~365 changed lines including focused tests.
- Sol reason: Ledger recovery and fixed undo lookup must never adopt forged state.
- Changelog: Record brokered effects and resolve undo by scoped action ID.

Owner decisions O1–O2 apply to the two corresponding broker operations. Other operations can be implemented and tested independently.

## Context

`scripts/kaizen-scheduled:139–156,989–1057,1187–1220` pins permissions, `:1650–1876,1940–2048` handles recovery and the commit point. `tests/test_runner.py:1093–1245` pins the complete sandbox flags. P23 supplies the in-memory map and guarded success branch. `skills/start/SKILL.md:25–28` defines the project Markdown row and `skills/undo/SKILL.md:16–26` defines file backup undo. P12b, P15b/P19, P16b and P18b supply independent scoped undo primitives.

Use the 0.12.0 integration base for landing. The references above are from 0.11.0 main at d8a4cb7. Read `AGENTS.md` and `CLAUDE.md`. Locate symbols with `tools/codemap` if available, otherwise `rg -n` and narrow `sed` ranges. All runtime changes support Python 3.9 and stdlib only. Use `python3`. Keep hard stops, captured user changes, zero-token collection and public-repo privacy; keep real logs and fixtures private.

## Scope and archive references

Owned files: `scripts/kaizen-scheduled`, `scripts/kaizen_friction_apply.py`, `scripts/install-schedule`, `tests/test_friction_apply.py`. Record the changelog line in `docs/plans/2026-11-17-friction-port/changelog/P24b.md`. Keep the scoped diff and tests within the assigned cap. Changes outside these paths need a separate packet or a revised scope.

Read `git show wt/p08b:scripts/kaizen-scheduled` at `review_command` and the install assertions in `git show wt/p08b:tests/test_runner.py`. Reuse the explicit operation inventory and installed path tests. Replace the archived `Bash(python3 <script>:*)` grants with trusted runner calls. Inspect archive paths with `git show` and keep the current branch.

## Implementation and acceptance

1. Provide runner-only ledger append and lookup/reconciliation. The eight-column `docs/kaizen/LEDGER.md` row uses date, change with `[action:fa1_…]`, why/catalogue signal, expected effect, measured effect `pending`, keep/revert `pending`, fixed same-scope metric command and ISO review date no more than 30 days out. Store the exact action ID → operation, scope, tool record, verification and phase linkage in the existing protected backup-root friction namespace. Use fixed text and bounded numeric evidence. A Markdown row never confers undo authority.
2. Validate ledger scope, format, identity and write safety before a broker operation. Under the project lock, append once for each verified effect, re-read and verify. Retry after effect-before-row and row-before-journal failures, recording no duplicate row. Conflict or missing ledger prevents new applies; an effect already present stays unresolved until bookkeeping succeeds. Follow the existing six-column header extension in `skills/start/SKILL.md` under the same lock, and keep ordinary file-backup rows working.
3. Add explicit `kaizen-scheduled actions undo ID --for DIR` for P26 to use interactively. Resolve exactly one private scoped verified record and ledger row, call only its fixed undo helper with live checks, then mark that row `reverted (YYYY-MM-DD)`. Reject forged rows/IDs, foreign projects and changed targets, support after opt-out, and handle interruption after undo before marking. Once reverted, keep this action ID terminal for unattended apply. Explicit reopen returns it for human follow-up without authorizing the same automatic effect again. Test enabled/disabled cases and interrupted undo. There is no scheduled undo grant.
4. Add identity-mapped `kaizen_friction_apply.py` to `install-schedule` `MANAGED_NAMES` in this packet. In `tests/test_friction_apply.py`, use a stub crontab, temporary config home and disposable copied plugin cache; run `python3 scripts/install-schedule --apply --scheduler cron`, then invoke installed `actions undo` against a verified disposable scoped record and ledger and assert the inverse and reverted row. Obtain security review before landing. Leave automatic effect/row wiring dark until P24.

## Verification

- `python3 -m unittest discover -s tests -p 'test_friction_apply.py'`
- `python3 -m unittest discover -s tests -p 'test_runner.py'`
- `python3 -m unittest discover -s tests -p 'test_schedule_security.py'`
- `python3 -m unittest discover -s tests -p 'test_schedule_robustness.py'`
- `python3 scripts/kaizen-scheduled actions undo --help`
- `tools/ci-local --python 3.9`

## Report

Report changed files and line counts, exact checks and outcomes, known uncertainty and any blocked verification. Label measurements with baseline/conditions. Redact paths and identifiers from shared output. Leave plugin version and release CHANGELOG to P27. Do not commit or push.
