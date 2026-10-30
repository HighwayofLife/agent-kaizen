# Changelog

Versions follow `version` in `.claude-plugin/plugin.json`. A GitHub marketplace install only picks up a release when that number changes.

## 0.4.0 (2026-10-30)

- The optional weekly review runs only for enrolled projects (those with `docs/kaizen/`) that had a session or a commit since their last review. It finds projects from recent Claude Code and Codex sessions, treats a repository's worktrees as one project, and has no project cap. Activity during a successful review does not make the project due again.
- New settings: global `enabled`, and global or project `schedule` (`active`, `always`, `off`) and `scheduledAutonomy` (`propose`, `auto`). A project value overrides the global one. `scheduledAutonomy` is separate from the interactive `autonomy` setting. `install-schedule --auto all|none|DIR...` sets it, and the `schedule` and `start` skills ask before writing it.
- New `scripts/kaizen-scheduled` runner: `audit`, `review [--dry-run]` and `config show|set`. `install-schedule --apply` installs it, and the jobs call it. One project's failure no longer stops the others, and a failed retry keeps the day's earlier proposal.
- token-audit: `--cwd` selects sessions by their recorded project path, including Codex sessions. Reports carry a scope line and are compared only with earlier reports of the same scope. The scan skips files older than the window. Built-in tools are no longer prune candidates.
- Scripts, hooks and skills honor `CLAUDE_CONFIG_DIR` and `CODEX_HOME`, including in scheduled jobs. Jobs use absolute paths and leave other crontab lines alone. On Linux, systemd user timers are used when cron is not available.
- `codex-review` defaults to `origin/HEAD`. `codex-review` and `codex-dispatch` keep `out/` out of git. The image and big-read guards degrade when the image agent or `jq` is missing. The audit notice uses the config directory, per-project reports, `enabled` and `schedule`.
- codex-dispatch: a repo may route check commands through an executable `tools/rewrite_check` (argv[1] is the command, stdout its replacement, empty means unchanged; worktrees fall back to the main checkout's copy). The docs now say to give `-k` the narrowest check.
- `templates/settings.example.json` no longer registers the audit-notice hook, because the plugin already does. If you copied that entry into your settings, delete it to avoid duplicate notices.
- Upgrading from 0.3.x: re-run `install-schedule --apply` (add `--review` for the weekly review). Existing launchd and cron jobs are replaced in place. Before moving to systemd, run `install-schedule --remove`. Three behaviour changes:
  - `--project-dir` no longer defaults to the current directory. Without it, every enrolled project with activity is reviewed, and a `--project-dir` without `docs/kaizen/` is skipped.
  - Auto mode is now the `scheduledAutonomy` setting. Re-installing without `--auto` makes the review propose-only.
  - Proposals are written per project in `audits/projects/<key>/`. Old reports are not compared with new ones.

## 0.3.2 (2026-10-29)

- token-audit: report Claude and Codex brief sizes and flag median growth between audits.
- codex-dispatch: checks that were not re-run in the final round are marked as such in the report.

## 0.3.1 (2026-10-29)

- codex-dispatch: resume rounds re-run only the failing checks, then confirm the checks that were skipped, once. Checks see `DISPATCH_ROUND` and `DISPATCH_PASS` (`initial`, `retry`, `final`) so project tooling can run cheaper checks while iterating.

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
