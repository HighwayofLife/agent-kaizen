# 04: port the dispatch guards to the live codex-dispatch

Risk: normal. Model: Terra medium.

## Goal

Packet 01 added three guards to the plugin's `scripts/codex-dispatch` in `~/github/highwayoflife/agent-kaizen`:

- a `require-change` pseudo-check against a git tree snapshot taken before Codex runs, with `--allow-no-change` to turn it off;
- a WARNING when the tree is already dirty;
- a refusal of `-m sol` unless the brief has a `Sol reason:` line (skipped on `--resume`).

The live copy at `~/.claude/bin/codex-dispatch` is a local override. It has extra features the plugin copy lacks: `-p 3d`, `--mcp`, `--unity-project`, and a default of astra for 3d, else terra. Port the same three guards into the live copy and keep every live-only feature.

**Working copy:** the live files are staged in the git repo `/private/tmp/claude-501/-Users-highwayoflife-github-highwayoflife-agent-visualization-plugin/350e6cbe-9fde-473d-93a0-8cfca3fd3d9e/scratchpad/live-bin` (this run's working directory) as `bin/codex-dispatch` and `bin/codex_common.py`. Edit those; the orchestrator copies them back to `~/.claude/bin` after checks pass. Wherever this brief says `~/.claude/bin/...`, edit the staged copy instead.

## Inputs

- The plugin change as a patch: `~/github/highwayoflife/agent-kaizen/docs/plans/2026-11-06-weekly-waste-fixes/briefs/04-plugin-dispatch-guards.patch`. Apply the same behaviour by hand where the hunks don't apply cleanly.
- The plugin brief: `~/github/highwayoflife/agent-kaizen/docs/plans/2026-11-06-weekly-waste-fixes/briefs/01-dispatch-guards.md`.
- The tests: `~/github/highwayoflife/agent-kaizen/tests/test_dispatch_guards.py`.

## Acceptance

1. `~/.claude/bin/codex-dispatch` has all three guards, with the same flag names, report lines and messages as the plugin copy.
2. `require-change` is on by default for `-p engineer` and for `-p 3d`, the profiles that are meant to edit files, and off for `-p planner`. Match what the plugin does for engineer. 3d edits files too, so it gets the guard.
3. `-p 3d`, `--mcp`, `--unity-project` and the model defaults behave as before.
4. The check below passes. It currently fails 13 of 13.

## Scope

- Edit only `~/.claude/bin/codex-dispatch`, plus `~/.claude/bin/codex_common.py` if a helper must live there.
- Do not edit anything in `~/github/highwayoflife/agent-kaizen`.
- `~/.claude` is not a git repo. Do not run `git init` there.
- No commits.

## Check

`LIVE_BIN=bin /private/tmp/claude-501/-Users-highwayoflife-github-highwayoflife-agent-visualization-plugin/350e6cbe-9fde-473d-93a0-8cfca3fd3d9e/scratchpad/live-guard-check.sh`

It copies the plugin's scripts and tests to a temp dir, overlays the live `codex-dispatch` and `codex_common.py`, and runs `tests.test_dispatch_guards`.
