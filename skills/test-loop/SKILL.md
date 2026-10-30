---
name: test-loop
description: "Design a tiered, fast test loop for a game or engine project: fast logic tests first, targeted engine tests, scheduled full suites, engine slots."
disable-model-invocation: true
argument-hint: "[propose|safe|auto|yolo]"
---

# A fast, tiered test loop (game projects)

Agents get feedback in seconds, not minutes, without losing safety. Run the cheapest checks first and the expensive engine runs only when they add something.

**Changes:** test scripts and project structure proposals, after you approve.

**Autonomy:** follow `${CLAUDE_PLUGIN_ROOT}/docs/autonomy.md`. The mode comes from the skill argument (`propose`, `safe`, `auto` or `yolo`), else `docs/kaizen/config.json`, else `agent-kaizen.json` in your Claude config dir (`$CLAUDE_CONFIG_DIR` or `~/.claude`), else `propose`. In `safe` and `auto`, read every "wait for my OK" below as: apply it yourself if the mode allows (backup, verify, roll back on failure, ledger row), otherwise list it as a proposal. Hard stops always ask. At most `maxChangesPerRun` changes (default 3). End with a summary of what was applied, skipped and rolled back.

## Task

Analyse how tests and checks run in this project and how long each stage takes. Use logs,
CI output or timed runs, not guesses. Write the baseline to
docs/kaizen/test-timing-<date>.md.

Then propose a tiered system, with an estimate of the time saved per item:
1. Logic outside the engine: where game logic can live in a plain library (no engine
   types), test it with a normal unit-test runner that finishes in seconds, without the
   editor. Agents run it on every change.
2. One check command per change: run the fast tests first and stop before launching the
   engine if they fail. Then run only targeted engine tests (the change's own tests plus
   a few named regression guards). A missing, empty or timed-out test report counts as a
   FAILURE, never as a pass.
3. Full suite on a schedule: the whole engine suite, a player build and a smoke test
   every 3–4 merges and at milestones, not per change. Split it into shards if one run
   takes too long.
4. Engine concurrency: a lock-based slot script (mkdir locks, holder PID, reclaiming
   slots held by dead processes) that limits engine instances machine-wide, for example
   to 2, so parallel agents queue instead of thrashing.
5. Fast worktrees: one git worktree per parallel task, created by a script that copies
   the engine's import cache with copy-on-write (APFS clonefile on macOS, reflink on
   Linux), so a new worktree doesn't reimport everything.
6. If the engine's test runner offers "run only affected tests", plan a short spike to
   prove it works on this repo before relying on it. Ours never selected anything, and
   we fell back to the tiers above.

Wait for my OK, then implement one tier at a time with tests for the scripts. Add a
ledger row per tier.

## Done when

most changes check in under a minute or two, the full suite runs on a fixed schedule, and no change can pass on an empty report.
