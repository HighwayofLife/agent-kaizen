# Plan review findings

## Sol high (codex-review plan): REVISE
**BLOCKING**
- Rollback — undo can overwrite plugin source through newly installed symlinks — evidence (`plan.md:104`; `scripts/kaizen-backup:135`) — unlink managed destinations before restoring backups; test that rollback leaves plugin sources unchanged.
- Packet 01 — `localScripts` protects reporting, but mutation behavior is unspecified; migration uses `--apply --replace` — evidence (`briefs/01-kaizen-link.md:22`; `briefs/12-owner-migration.md:18`) — explicitly skip LOCAL entries during mutations and test that Codex files and preambles remain byte-identical.
- Packet 13 — the due branch can run auto; the fallback lacks scheduler restrictions and never saves the expected cycle file — evidence (`briefs/13-end-to-end-gate.md:15`; `scripts/kaizen-scheduled:860`, `scripts/kaizen-scheduled:877`) — force propose-only in both branches, reuse `review_command` restrictions, and capture the resulting artifact.
- Packets 07/09 — allowing only `notes-ledger add` does not enforce append-only access when auto still permits direct Edit/Write — evidence (`briefs/09-scheduled-wiring.md:12`; `scripts/kaizen-scheduled:593`) — deny direct writes to configured ledger targets and test that append succeeds while rewrites fail.
- Packets 01/09 — copy installation omits runtime dependencies: `rules-lint.patterns`, canonical `token-audit` for usage tools, and their default `pricing.json` — evidence (`briefs/01-kaizen-link.md:10`; `briefs/09-scheduled-wiring.md:18`; `scripts/usage-series:18`, `scripts/usage-series:39`) — install dependencies under the expected names and test
- Packet 12 — the no-approval branch skips linking, retires the registry still used by old jobs, and omits backup finish — evidence (`briefs/12-owner-migration.md:10`, `briefs/12-owner-migration.md:19`; `~/.claude/bin/kaizen-token-audit:311`) — define a safe deferred branch that preserves operational dependencies and finishes its backup.
- Packet 12 — `--auto <project>` writes into New World despite its read-only scope, without covering that file in the backup — evidence (`briefs/12-owner-migration.md:21`, `briefs/12-owner-migration.md:26`; `scripts/install-schedule:81`) — remove this branch or explicitly authorize and back up the project-config change.
- Packet 05 — section-7-only scope cannot produce classifications and durations that collection currently discards — evidence (`briefs/05-ports.md:13`; `scripts/token-audit:585`, `scripts/token-audit:627`) — permit changes to `scan_codex` and collection initialization, retaining the existing single-pass pattern.
- Packet 13 — pasting real command output into the plan introduces absolute home paths that violate repository privacy checks — evidence (`briefs/13-end-to-end-gate.md:18`; `AGENTS.md:21`; `tests/test_repo.py:77`) — redact paths before insertion and rerun repository consistency tests afterward.
**ADVISORY**
- Packet 12 — bootout leaves the retired token-audit plist available for a future login; rollback also needs service actions — evidence (`briefs/12-owner-migration.md:21`; `scripts/install-schedule:151`; `docs/autonomy.md:74`) — rename the retired plist outside LaunchAgents and record explicit reverse launchctl commands.
- Packet 07 — CSV-first duplicate detection can leave the timeline missing after a partial failure; concurrent append behavior is untested — evidence (`briefs/07-notes-ledger.md:19`, `briefs/07-notes-ledger.md:28`) — specify serialization and retry recovery; test simultaneous adds and failure between destinations.
- Packet 07 — measurement proposals select reports by date without checking compatible scopes or windows — evidence (`briefs/07-notes-ledger.md:20`; `scripts/token-audit:1019`) — reuse the existing `previous_audit` scope-matching pattern and test incompatible reports.
- Packet 09 — expected exit 1 from drift/lint checks can be treated as unavailable, hiding actionable findings — evidence (`briefs/09-scheduled-wiring.md:10`, `briefs/09-scheduled-wiring.md:21`) — retain diagnostic stdout for finding exits and test actual drift/lint output.
VERDICT: REVISE — The approach is feasible, but installation, rollback, unattended permissions, and the final gate need concrete corrections before execution.

## sonnet-plan-reviewer: REVISE
Blocking:
1. The installed plugin is the stale cache copy 0.2.0 (`~/.claude/plugins/installed_plugins.json` installPath `.../cache/agent-kaizen-tools/agent-kaizen/0.2.0`), so `/agent-kaizen:cycle` runs the old skill.
   - Brief 12: after packet 11, run `/plugin marketplace update agent-kaizen-tools`, update the plugin, and verify 0.7.0 in `installed_plugins.json`.
   - Brief 13: make that a precondition.
   - Fix the claim "installed from this directory" in plan.md and context.md.
2. Brief 13 step 3: `~/.claude/audits/projects/` has no `index.json`. `kaizen-scheduled` `_run_audit` (~l.800) only reads the index; `_run_review` (~l.832) writes it. Either make brief 09's `audit` discover and write the index, or run `review` first. Add a criterion: a fresh config dir with no index.
3. Brief 12 rollback: `kaizen-backup undo` uses `shutil.copy2`, which follows symlinks, so it would overwrite plugin `scripts/`. `begin` rejects non-regular files, so the `prompts`/`preambles` dirs cannot be backed up.
   - Take the backup list from the `kaizen-link` dry-run plan.
   - Rollback order: `kaizen-link --unlink` first, then `kaizen-backup undo`. Test or check that order.
4. Brief 13 step 7: pasted outputs contain `/Users/<name>`, and `tests/test_repo.py:76` scans the untracked `docs/plans/`. Redact to `~`, then re-run the full suite.
5. Brief 12 step 8 says the audit is `kaizen-scheduled` while step 9 is deferred, but the old launchd jobs still run, now against the linked plugin `token-audit`, which lacks sections 9–11.
   - Keep `kaizen-token-audit` in `localScripts` until step 9, or record the gap.
   - Make the wording conditional.
   - Add the superseded CLAUDE.md item 7 wording to the owner's rules-lint list.

Advisory:
6. Routing: brief 11 docs that read code go to Terra medium, not haiku-engineer.
7. D = 11 → 12 is serial. Groups A and B share one tree, so use worktrees or filtered tests. Briefs 05 and 07 are probably over 300 lines, so split them if they are.
8. Brief 01: directory semantics (`prompts`, `preambles`) for compare, link, copy and `--replace` are unspecified.
9. Brief 07 `set`: define the timeline-row match: same date, and the timeline cell is contained in or a prefix of the CSV cell.
10. Brief 09 criterion 7 timing runs before the project commands and index exist. Add timing with and without `KAIZEN_SKIP_CHECKS` to brief 13, and exercise `notes-ledger add --dry-run` and the `auto` allow list there.
11. `install-schedule --apply --replace` on generic names in other users' bin dirs: print the plan first, or replace only files that came from the plugin.

## Orchestrator decisions (2026-11-04)
- Brief 09 (unattended permission allow list) goes to **Sol high**, risk high, per the security-sensitive routing row.
- Brief 11 goes to **Terra medium**.
- Every Codex packet runs in its own git worktree of agent-kaizen (`git worktree add ../agent-kaizen-wt-<id> -b kz-<id>`), so groups can run in parallel.
- Split 05 and 07 only if each half stays independently testable. Keep the total at 15 packets or fewer.
- Keep `kaizen-token-audit` in `localScripts` until the owner approves the launchd step (decision 3 is still pending).
