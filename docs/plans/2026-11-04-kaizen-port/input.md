# Input: make agent-kaizen the single home for self-improvement tooling (owner request 2026-11-04)

Mode: full (plan.md + briefs). Plan directory: `docs/plans/2026-11-04-kaizen-port/` in this repo.

## Owner's words (2026-11-04)
"All new audit tools/processes should always be added/ported to the plugin's audit. We want to make this agent-kaizen plugin the one-stop-shop for 'all things self-improving'. This means:
- improving the workflows;
- improving the configurations;
- reducing cost and usage;
- increasing efficiency;
- speeding up development.

Whenever we determine some new tool fits this, we add it to the plugin and run it periodically. Then also add notes to the notes repo to reflect what changes were made and why, and then measure if they worked."

## Current state (verify each claim before planning)
- The plugin keeps its own copies of scripts under `scripts/` (token-audit, codex-review, codex-dispatch, codex-run, dispatch-status, kaizen-backup, kaizen-scheduled, usage-series, usage-compare, …). These have diverged from the live copies under `~/.claude/bin/` that the owner's setup runs. Example: `diff -q scripts/codex-review ~/.claude/bin/codex-review` differs. The plugin is installed from this directory (`~/.claude/settings.json` marketplace `agent-kaizen-tools`).
- Added on 2026-11-03/04 in `~/.claude` only, not in the plugin:
  - `~/.claude/bin/token-audit` and `~/.claude/bin/kaizen-token-audit`: sections 9–11 (packet outcomes from each project's `out/packets.jsonl`, first-pass and fix rates by model×effort, calibration proposals up or down a rung, ledger measurement proposals), section 7 Codex durations, and the registry `~/.claude/project-repos.txt`.
  - `~/.claude/bin/rules-lint` with `~/.claude/bin/tests/test_rules_lint.py`: a stale-rule lint over instruction files, driven by a pattern list.
  - `~/.claude/bin/codex-review diff --paths`, and `dispatch-status` changes.
  - hooks `after-compact.sh`, `session-notes.sh` and `limit-big-read.sh`.
- Project-side tooling in New World (`~/github/highwayoflife/NewWorld/tools/`) that produces the data the audit reads:
  - `packet_log.py` writes `out/packets.jsonl`, whose keys are listed in `tools/packet_log.py`;
  - `packet_report.py`, `speed_report.py`, `test_timing_report.py --over`, `audit_slices.py`;
  - `review_batch.py --shadow-status` (shadow reviews: 1 batch in 4 gets per-packet reviews for 3 weeks; stop when batch review catches ≥90% of MUST-FIX).
  - The full history is in `docs/plans/2026-11-04-pipeline-speed/`: `plan.md`, `final-audit.md`.
- Process rules added on 2026-11-04 to `~/.claude/planning/planner-guide.md` (Packet principles) and `~/.claude/CLAUDE.md` item 8 (Kaizen rule):
  - speed and cost packets carry a before/after measurement;
  - a tooling plan ends with an end-to-end gate;
  - superseded wording goes into rules-lint.
- Notes repo: `~/github/highwayoflife/agent-field-notes`. Changes go in `data/changes.csv` (date, category, change, source, status, measured) and `findings/changes-timeline.md`; findings notes go under `findings/`. `tools/sync-config` copies config into `config/`.

## Goals (each needs testable acceptance criteria)
1. **One source of truth.** The plugin's scripts are canonical. Port every `~/.claude/bin` improvement listed above into the plugin, keeping the plugin generic: no personal paths, emails or New World names in code, since it has LICENSE and CONTRIBUTING. Then make `~/.claude/bin/<name>` a symlink or thin wrapper to the plugin copy, so the copies can no longer drift.
   - Say how the plugin's own installer or `start` skill sets that up for other users.
   - Every `~/.claude` edit takes a `kaizen-backup begin/finish`.
   - Add a drift check, run by the audit, that reports any `~/.claude/bin` script differing from its plugin source.
2. **Project data contract.** Document a generic outcome-log contract: `out/packets.jsonl` keys, the trailers, and an optional shadow-status command. Any enrolled project can then feed the audit. Project enrolment replaces `~/.claude/project-repos.txt`; reuse the plugin's per-project config and enrolment from 0.4.0.
3. **Periodic run.** The plugin's scheduled cycle (`kaizen-scheduled`, `install-schedule`, skills `cycle` and `audit`) runs all of the following, and the `kaizen-auditor` agent knows about them:
   - packet outcomes and calibration proposals;
   - rules-lint;
   - the drift check;
   - shadow-review status;
   - slow-test report hooks (a project command named in project config);
   - ledger measurement proposals.
4. **Change recording and measurement.** A plugin step records each applied change as a row in a configurable notes ledger: for this owner, `agent-field-notes/data/changes.csv` plus the timeline, with what, why, source, status and how it will be measured. On a later cycle it proposes the measured effect for rows still marked `measured=no` once enough data exists. It proposes; the owner approves. Owner-specific paths live in user config, not code.
5. **Process rules in the plugin's skills.** Put the three planning rules and the Kaizen rule in the relevant plugin skills (`planning`, `cycle`, `review`, …) so other users get them.
6. **Docs and release.** README, CHANGELOG, a version bump following the repo's existing practice, and `docs/what-we-learned.md` if that is where lessons go.

## Constraints
- Follow this repo's `AGENTS.md` and `CLAUDE.md`, and keep its tests green (`tests/`).
- Read `~/.claude/CLAUDE.md` for routing:
  - Codex (Terra medium by default) can write this repo but not `~/.claude`;
  - `~/.claude` packets go to `sonnet-engineer`, or to `haiku-engineer` when mechanical;
  - tag each packet low, normal or high.
- New World is another session's active repo. Do not plan edits there except, if needed, one small packet that points its tools at the plugin.
- Apply the planning rules from 2026-11-04: before/after measurement where speed or cost is claimed, an end-to-end gate as the last packet (run the scheduled cycle once for real and paste the trimmed output), and rules-lint updates when a contract changes.
- About 6–10 packets, each under ~300 changed lines. Use parallel groups of ≤4.
