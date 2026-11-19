# FA1 r3: regressions versus the release branch (last round)

Fix-Origin: final-audit. Risk: high. Model: sol / xhigh.
Sol reason: last-round regression repair in race/durability code after two Sol/Terra rounds; effort raised per the retry rule.

## Goal
Your packet's earlier rounds (commits after `518da76`, briefs `fa1-*.md` in this directory) fixed audit findings but a review found these regressions — behaviour that works at `518da76` (the release branch) and breaks now. Fix exactly these items:

1. `scripts/kaizen-backup:2274` — Shared-path snapshots treat writes through another hard-linked name as external edits — a run that previously rolled back both names now aborts after partially restoring the files.
1. `scripts/kaizen-backup:1136` — Legacy undo restores `0644` files as `0600` even when the backup and working file modes agree — a successful undo can revoke access for existing readers.

## Rules
- For each item: write a test that fails now and passes at `518da76` (or that pins the intended behaviour), then fix narrowly OR revert the hunk that caused it to the `518da76` behaviour (and name the original audit item that is then deferred). Prefer revert unless the fix is small and obviously safe.
- Fix nothing else, even if you notice other issues: list them in the report instead. Under ~150 changed lines. Stay in the files this packet already touched.
- Never weaken, skip or delete an existing test. Do not commit or push; do not touch plugin.json, CHANGELOG.md or the version.
- Report: per item FIXED / REVERTED (+ deferred original item), the test name, files changed, checks run.
