---
name: schedule
description: "Schedule the usage audit (and optionally a propose-only review) to run locally every few days, with a session-start notice."
disable-model-invocation: true
argument-hint: "[propose|safe|auto|yolo]"
---

# Schedule the audit

Schedule a global audit and an optional weekly project review.

**Changes:** scheduled jobs and settings, after you approve. The plugin supplies the SessionStart notice.

**Autonomy:** follow `${CLAUDE_PLUGIN_ROOT}/docs/autonomy.md`. The mode comes from the skill argument (`propose`, `safe`, `auto` or `yolo`), else `docs/kaizen/config.json`, else `agent-kaizen.json` in your Claude config dir (`$CLAUDE_CONFIG_DIR` or `~/.claude`), else `propose`. In `safe` and `auto`, read every "wait for my OK" below as: apply it yourself if the mode allows (backup, verify, roll back on failure, ledger row), otherwise list it as a proposal. Hard stops always ask. At most `maxChangesPerRun` changes (default 3). End with a summary of what was applied, skipped and rolled back.

## Task

The global audit runs about every 3 days without tokens and writes `token-audit-<timestamp>.md` in `audits/` in your Claude config dir (`$CLAUDE_CONFIG_DIR` or `~/.claude`). The optional weekly review uses tokens: one headless Sonnet run per enrolled project with activity since its last review, with no project cap. It writes a `token-audit-<timestamp>.md` and `cycle-<yyyy-mm-dd>.md` per project in `audits/projects/<key>/` in that config dir. The SessionStart hook announces new reports. Jobs use launchd on macOS, or cron or systemd user timers on Linux. Windows users can run the scripts by hand.

Global `enabled` defaults to true; false turns off all scheduled work. Global or project `schedule` is `active` (default, review only after activity), `always`, or `off` (no review or notice). Global or project `scheduledAutonomy` is `propose` (default) or `auto`. Project values override global ones. Interactive `autonomy` is separate and is not read by scheduled runs.

Installing or changing scheduled jobs is a hard stop in `${CLAUDE_PLUGIN_ROOT}/docs/autonomy.md`. Even in `safe`, `auto` or `yolo`, ask each question in order and wait for its answer:

1. Install the 3-day audit (no tokens)?
2. Add the weekly review for every enrolled project with activity (uses tokens)?
3. If yes to 2, which projects may it change files in: none (default), all, or named ones?
4. Any project to leave out?
5. Turn all scheduled work off or back on globally?

Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kaizen-scheduled review --dry-run`, show its output, and ask for a final OK. After approval, if the audit was accepted, run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/install-schedule --apply` with `--review` if the weekly review was accepted and `--auto none`, `--auto all`, or `--auto <dir>...` for answer 3. `--auto` implies `--review`; omit both flags if the weekly review was declined. For each project excluded in answer 4, run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kaizen-scheduled config set --for <dir> schedule=off`. For answer 5, run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kaizen-scheduled config set enabled=false` or `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kaizen-scheduled config set enabled=true` as requested. Use absolute project paths, one command per Bash call. Never edit JSON by hand. Write `schedule` or `scheduledAutonomy` only as a direct result of answers here or in `/agent-kaizen:start`, and never in a `propose-only` run.

For scripted installs, `install-schedule` also accepts `--project-dir` (repeatable), `--model`, `--max-turns` and `--scheduler`; use `--remove` to remove jobs.

Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kaizen-scheduled audit` once by hand and check that the report appears in the audits folder. Start a new session and confirm the notice fires. Add a ledger row.

## Bundled resources

`${CLAUDE_PLUGIN_ROOT}/scripts/token-audit`, `${CLAUDE_PLUGIN_ROOT}/scripts/kaizen-scheduled`, `${CLAUDE_PLUGIN_ROOT}/scripts/install-schedule` (launchd, cron, systemd user timers), `${CLAUDE_PLUGIN_ROOT}/hooks/audit-notice.sh`, and `${CLAUDE_PLUGIN_ROOT}/docs/scheduling.md`.

## Done when

The approved jobs and settings are installed, the audit report appears, and the session notice fires.
