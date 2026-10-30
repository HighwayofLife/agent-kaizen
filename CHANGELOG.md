# Changelog

Versions follow `version` in `.claude-plugin/plugin.json`. A GitHub marketplace install only picks up a release when that number changes.

## 0.3.0 (2026-10-29)

Four new audit measurements, inspired by Microsoft's [TokenEconomizer](https://github.com/microsoft/TokenEconomizer), which acts on the same signals live inside each session. Agent Kaizen measures them offline at zero token cost and turns them into proposals:
- **API-equivalent cost:** every message priced cache-aware (cache reads, 5-minute and 1-hour cache writes, uncached input, output) from published prices in `scripts/pricing.json`, including Haiku 5.5's higher rate above 100k prompt tokens. It is a weighting for comparing changes, not a bill.
- **Stuck turns:** the same failure (tool, command or file, and first error line) repeated three or more times in one turn.
- **Repeated failures across sessions:** candidates for one-line repo facts in CLAUDE.md, with a "worked instead" hint when a different launcher, environment variable or directory fixed it.
- **Unused tools and MCP servers** per project, one row per server. Deferred tools are summarised, since only their names are sent.

Also:
- Error lines in the report are normalised and secret-like strings redacted. The scan is faster than 0.2.1, despite the extra measurements.
- The audit, review, trim-context and guardrails skills and docs/autonomy.md use the new sections: repo facts apply in `safe` mode, deny rules only in `auto`.
- README: an animated teaser, the loop redrawn as a light/dark SVG, a new banner, tested versions, and a comparison with TokenEconomizer. The graphics are drawn by `assets/src/*.py`.
- AGENTS.md (also imported by CLAUDE.md and used as the subagent role context): commands and rules for coding agents working on this repo.

## 0.2.1 (2026-10-29)

Fixes from five end-to-end `yolo` test runs on a real project:
- **`kaizen-backup` script** (begin / finish / action / list / undo): backups, manifests, after-hashes and undo are now done by a tested script instead of model-followed steps. Undo refuses conflicts unless `--force`, and prints reverse commands without running them.
- **Scheduled runs:**
  - they can read `~/.claude` and `~/.codex` (`--add-dir`) and run read-only commands (ls, wc, head, tail, rg, git status/diff/log, jq);
  - every change in a run shares a `KAIZEN_RUN_ID`;
  - the audit copy is installed as `kaizen-token-audit`, so it never replaces another `token-audit`.
- **`auto` mode applies changes.** The cycle carries out its top proposals instead of stopping at a list, and docs/autonomy.md lists the reasons that don't justify skipping a change. Headless runs leave protected `~/.claude` files as "do interactively".
- README: the story behind the project.

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
