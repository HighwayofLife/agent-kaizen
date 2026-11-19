# FA6 r2: regressions from r1 (final round)

Fix-Origin: final-audit. Risk: high. Model: sol / high.
Sol reason: escalation — two earlier rounds on this packet each introduced regressions in race/durability code; this round fixes or reverts them.

## Goal
A Sol review of your r1 commit (HEAD; briefs `fa6-r1-review-fixes.md` and the original `fa6-*.md` in this directory) found these regressions introduced by r1:

1. [scripts/host-probe:200] — The new full-index listing can exceed the 1 MiB command cap even in a clean repo with no submodules — the probe skips status and loses worktree cleanliness and regenerable-directory evidence.
1. [scripts/host-probe:326] — The scan reopens every ancestor for each queued directory, making traversal quadratic in a deep tree — a build tree below the entry cap can exhaust the probe deadline and discard all directory findings.
1. [scripts/host-probe:202] — `submodule foreach` fails on an embedded repository tracked as a gitlink without a `.gitmodules` entry — the new preflight drops regenerable-directory evidence even when ordinary `git status` succeeds. [Git source](https://github.com/git/git/blob/master/builtin/submodule--helper.c#L326-L333)
1. [skills/cycle/SKILL.md:24] — Every interactive cycle now runs the full review dry run, and stale cycles run it twice — a fresh audit lookup can trigger a scan of Claude and Codex session logs under the default activity policy.
1. [tests/test_friction_sampler.py:221] — The readiness assertion can fire after spawning the child but before returning its PID to the cleanup code — a slow CI worker can fail the test and leave the child running.

## Rules
- For each item: fix it narrowly, OR revert the r1 hunk that caused it and mark the original r1/audit item it addressed as DEFERRED (it goes to the 0.14 known-issues list). Prefer the revert when the fix is not small and obviously safe. Behaviour must be no worse than at the FA commit before r1 for every supported setup.
- No new features or hardening beyond these items. Under ~150 changed lines. Stay in the files r1 touched.
- Add a regression test for each fixed item where practical; never weaken, skip or delete an existing test.
- Do not commit or push. Do not touch plugin.json, CHANGELOG.md or the version.
- Report: per item FIXED / REVERTED (+ which original item is now DEFERRED) / REFUTED (evidence), files changed, checks run.
