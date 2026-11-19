# FA5 r3: regressions versus the release branch (last round)

Fix-Origin: final-audit. Risk: high. Model: sol / xhigh.
Sol reason: last-round regression repair in race/durability code after two Sol/Terra rounds; effort raised per the retry rule.

## Goal
Your packet's earlier rounds (commits after `518da76`, briefs `fa5-*.md` in this directory) fixed audit findings but a review found these regressions — behaviour that works at `518da76` (the release branch) and breaks now. Fix exactly these items:

1. `scripts/kaizen_worktree_facts.py:230` — Python 3.13 treats a symlink loop as a missing submodule and runs the status scan — this bypasses the guard and breaks r1’s `clean=unknown` test on CI’s Python 3.13 jobs.
1. `scripts/dispatch-status:126` — Advisory selection compares path spellings case-sensitively — on case-insensitive macOS volumes, a valid path with different capitalization now reports `unknown` instead of showing the worktree facts.
1. `scripts/worktree-prune:1` — r1/r2 pinned the shebang to `/usr/bin/python3`, which breaks supported setups whose compatible Python lives elsewhere. Restore the `518da76` shebang (exactly `#!/usr/bin/env -S python3 -I`) and keep any in-script isolation that does not depend on the shebang; the PATH-interpreter audit item becomes deferred.

## Rules
- For each item: write a test that fails now and passes at `518da76` (or that pins the intended behaviour), then fix narrowly OR revert the hunk that caused it to the `518da76` behaviour (and name the original audit item that is then deferred). Prefer revert unless the fix is small and obviously safe.
- Fix nothing else, even if you notice other issues: list them in the report instead. Under ~150 changed lines. Stay in the files this packet already touched.
- Never weaken, skip or delete an existing test. Do not commit or push; do not touch plugin.json, CHANGELOG.md or the version.
- Report: per item FIXED / REVERTED (+ deferred original item), the test name, files changed, checks run.
