# Changelog

Versions follow `version` in `.claude-plugin/plugin.json`. A GitHub marketplace install only picks up a release when that number changes.

## 0.2.0 (2026-10-29)

- **Autonomy modes**: `propose` (default), `safe` and `auto` (alias `yolo`), set per run (`/agent-kaizen:cycle yolo`), per project or globally (`/agent-kaizen:autonomy`). Every applied change is backed up, verified, rolled back if verification fails, capped at 3 per run, and logged. The hard stops (secrets, spending, permissions, deletions, pushes, installs) always ask. See docs/autonomy.md.
- New skills: `autonomy` and `undo`.
- `install-schedule --auto`: the weekly cycle applies changes with `acceptEdits` and a narrow tool list (never `bypassPermissions`).
- CI: tests on Linux and macOS (Python 3.9 and 3.13), hook smoke tests, repo-consistency and privacy checks, shellcheck, JSON lint, `claude plugin validate`, and a version and changelog check on PRs.

## 0.1.0 (2026-10-29)

First public release:
- 18 skills: start, audit, cycle, review, roster, models, whats-new, trim-context, slim-instructions, lean-agents, codex-dispatch, tools-before-tokens, code-map, guardrails, batch-wakeups, planning, test-loop, schedule.
- The `kaizen-auditor` agent (propose-only).
- The SessionStart audit notice, plus opt-in guardrail hooks.
- Scripts: token-audit, codex-dispatch, codex-review, codex-run, dispatch-status, install-schedule.
- Templates for CLAUDE.md, the orchestrator file, Codex AGENTS.md and config, settings, agents, role context, plans and briefs.
