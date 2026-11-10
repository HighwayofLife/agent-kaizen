# Weekly waste fixes (2026-11-06)

Source: agent-field-notes `findings/weekly-review-2026-11-06.md`.

| # | Packet | Repo | Model | Risk | Status |
|---|---|---|---|---|---|
| 01 | codex-dispatch guards: require-change snapshot, dirty-tree warning, Sol reason | agent-kaizen | Terra medium | normal | done, green; in batch review |
| 02 | Bash burst hook (main session) | agent-kaizen | Terra medium | normal | done, green; in batch review |
| 03 | packet-report escalations + outcome-log `dispatch_models` | agent-kaizen | Terra medium | low | done, green; in batch review |
| 04 | Port 01 to the live local `~/.claude/bin/codex-dispatch` | ~/.claude | Terra medium | normal | done, installed live; 13/13 guard tests pass against ~/.claude/bin (backup in session scratchpad) |
| 05 | New World `packet_log.py` records `dispatch_models` | NewWorld worktree | Terra medium | low | done, green (worktree); in batch review |
| 06 | Rules text, agent context, MCP denies, version bump | various | orchestrator / haiku | low | done: rules, agent context, MCP denies, 0.8.0 + CHANGELOG, ledger rows |
| 07 | Batch-review fixes: snapshot crash on untracked dirs, -o logs in fingerprint, Sol guard on resolved model; then re-port live (08) | agent-kaizen, ~/.claude | Terra medium | normal | done, green: 17 guard tests + full suite, shellcheck, validate |
| 08 | Port 07 to the live `~/.claude/bin/codex-dispatch` | ~/.claude | Terra medium | normal | done, installed live; 17/17 guard tests pass against ~/.claude/bin (backup in session scratchpad) |

Packets 01-03 touch disjoint files and must not edit `.claude-plugin/plugin.json` or `CHANGELOG.md`; packet 06 bumps the version once.
Deferred: second Unity PlayMode slot / affected-only PlayMode (needs its own plan).


## Polish list

- packet-report escalation pairs use first->final model, so Terra->Sol->Terra reads "terra->terra". Label by distinct path or document it.
- codex-dispatch gives a bare `STATUS: CODEX FAILED` with no reason when `-C` is not a git repo; print the cause (Codex needs a git repo or `--skip-git-repo-check`).

Batch review 2026-11-06 (sonnet-verifier + Sol codex-review): 02, 03, 06 PASS; 01 findings fixed in 07; 05 nit (resume suffix in effort) fixed by the orchestrator in the worktree.