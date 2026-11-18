# P22 Show one scoped open-action count in the session notice

## Goal

Show one scoped open-action count in the session notice. This packet is part of the Agent Kaizen friction port for 0.13.0.

- **Agent / model / effort** — `codex-dispatch` (`codex-engineer` fallback), terra, medium.
- **Risk** — normal. Use green checks and the integration batch review.
- **Group / dependencies** — H. After P11, P14c.
- **Size target** — ~240 changed lines including focused tests.
- Changelog: Show one scoped open-action count in the session notice.

## Context

`hooks/audit-notice.sh:8–45,128–176` has project key/config resolution, message assembly and atomic markers. Use the 0.12.0 host adapter and test its current Claude, Codex and Copilot output shapes. `tools/context_budget.py:83–111` charges literal context.

Wait for 0.12.0 P05 and the friction sampler packet to finish editing the context inventory. Read `AGENTS.md` and `CLAUDE.md`. Locate symbols with `tools/codemap` if available, otherwise `rg -n` and narrow `sed` ranges. All runtime changes support Python 3.9 and stdlib only. Use `python3`. Keep hard stops, captured user changes, zero-token collection and public-repo privacy; keep real logs and fixtures private.

## Scope and archive references

Owned files: `hooks/audit-notice.sh`, `tools/context-budget.json`, `tests/test_hooks.py`. Record the changelog line in `docs/plans/2026-11-17-friction-port/changelog/P22.md`. Coordinate a split if the diff plus tests exceeds 400 changed lines. Changes outside these paths need a separate packet or a revised scope.

Read `git show wt/p09:hooks/audit-notice.sh` around `host_actions` and per-project marker logic, and `git show wt/p09:tests/test_notice_actions.py`. Port the count and scoping logic; retain today's quiet/failure and other message paths. Inspect archive paths with `git show` and keep the current branch.

## Implementation and acceptance

1. Append one short count of open actions for the current project, at most daily per canonical project using a private atomic marker. Respect `enabled`, `friction`, `hostActions` and project notice opt-out; prevent count or action detail leaking across projects. Quiet on missing/corrupt/symlink or oversized private store. Limit new model-visible notice text including separators to 200 UTF-8 bytes, using the merged 0.12.0 823-byte baseline under the 1024-byte cap (see `git show multi-host:docs/plans/2026-11-17-multi-host/plan.md` at line 170). Show only count and a short route to the read-only list. Preserve startup/resume context schema, existing notices and marker retry behavior when emission fails. Verify existing golden fixtures, cumulative context budget, concurrent first starts and index variants. Update only the audit-notice inventory entry and hash.
2. Verify its failure and compatibility cases with the narrow checks below. Disabled/unavailable inputs must leave existing workflows usable. Keep partial changes private or gated until this packet's checks pass.
3. Confirm that the diff is confined to the owned files and that the integrated Python 3.9 check is green.

## Verification

- `python3 -m unittest discover -s tests -p 'test_hooks.py'`
- `python3 -m unittest discover -s tests -p 'test_context_budget.py'`
- `python3 -m unittest discover -s tests -p 'test_doctor.py'`
- `shellcheck -S warning hooks/audit-notice.sh`
- `python3 tools/context_budget.py --root .`
- `tools/ci-local --python 3.9`

## Report

Report changed files and line counts, exact checks and outcomes, known uncertainty and any blocked verification. Label measurements with baseline/conditions. Redact paths and identifiers from shared output. Leave plugin version and release CHANGELOG to P27. Do not commit or push.
