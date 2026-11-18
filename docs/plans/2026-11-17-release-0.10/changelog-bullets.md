# Proposed changelog bullets for 0.10.0 (from packet reports; orchestrator-edited)

## Added
- 01 flow-event: `scripts/packet-event` appends one packet state event (queued, dispatched, round-N, checks, slot-wait, review, ready, landed, failed) to `out/packet-events.jsonl` with an atomic append; format in `docs/flow.md`.
- 02 experiment-check: `scripts/experiment-check` lists experiments past their review date with no measurement and ledger rows `pending` for more than N days; the efficiency ledger gains optional metric-command and review-date columns (old six-column rows still parse).
- 03 brief-lint: `scripts/brief-lint` checks dispatch briefs before they go out: required sections, named repo paths (paths a brief creates are declared), verify commands that resolve, size warnings; `--json`.
- 05 flow-report: `scripts/flow-report` reports packet lead time, time in each state, waits and work in progress from the packet event log.
- 06 experiment-notice: scheduled checks and the session notice surface overdue experiments; new `pendingDays` setting (default 10).
- 07 dispatch-preflight: opt-in `--brief-lint` preflight in `codex-dispatch` (off by default).
- 09 due-checks: completed checks (audit, models, roster, whats-new, cycle) are recorded per project (`kaizen-scheduled checks record`), and `experiment-check --checks` reports checks that are due or have never been recorded; the session notice mentions them at most once a day.
- 10 flow-skill: new `flow` skill for instrumenting packet states and reading flow reports.

## Changed
- 04 packet-quality: `packet-report` normalises model labels (aliases such as `gpt-6.1-terra` → `terra`; unknowns counted and listed), reports rows with missing tokens or cost instead of treating them as zero, and flags landed packets whose checks were failing.
- 08 review-economics: `packet-report` adds a review-economics section (fix packets per landed packet, fix-of-fix rate, fix packets without a MUST-FIX) and holds a calibration increase, with the reason, when the tier's fix packets are small.
- 11 registration: `install-schedule` and `kaizen-link` install the new scripts; `scripts/README.md` documents them. Scheduled-step output keeps its final summary line when truncated.

## Fixed
- The session-notice hook escalates a stuck checker from SIGTERM to SIGKILL, so SessionStart always finishes and prints its JSON; the once-a-day notice marker is created atomically, so two sessions starting together show it once.
- `experiment-check` stops reading the ledger table at its first non-table line, so prose containing `|` after the table is not reported as a malformed row.

## Notes
- The due-check nag fires in every project on its first day (no check has been recorded yet), at most once a day.
