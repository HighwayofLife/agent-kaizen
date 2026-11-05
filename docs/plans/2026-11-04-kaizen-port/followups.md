# Follow-ups found during the port (not in a packet yet)

- 2026-11-04 kz-02: `codex-dispatch` printed `STATUS: DONE` when Codex stopped with a question and changed nothing. This is a false green, and the orchestrator nearly landed nothing. Proposal: when the tracked diff is empty and the final message contains a question or "stopped", report `STATUS: NEEDS-DECISION` (or `NO-CHANGE`). Add the check to the dispatch report, and add a test. The script is local (`localScripts`), so the change goes into `~/.claude/bin/codex-dispatch`, with a backup. Measure how often NO-CHANGE fires and how many wasted wake-ups it saves.

## notes-ledger set cannot update hand-written legacy rows (2026-11-04)

`set --match` requires the timeline row text to be equivalent to the CSV change text. Rows written by hand before notes-ledger existed use different wording, so set fails with "match must select exactly one timeline row" and nothing can be updated. Proposal: add `--timeline-match TEXT` to select the timeline row separately, still exactly one row.

## Scheduled release checks by runner precompute (2026-11-04)

Scheduled cycles lost WebFetch/WebSearch in 0.7.1. Model and release checks could instead be fetched by the runner, with curl and the generic User-Agent, into the checks report, the same way it precomputes other checks.
