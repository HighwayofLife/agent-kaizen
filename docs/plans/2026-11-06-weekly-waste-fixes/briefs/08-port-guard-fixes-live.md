# 08: port the guard fixes (packet 07) to the live codex-dispatch

Risk: normal. Model: Terra medium. No commits.

## Goal

Packet 07 fixed three defects in the plugin's dispatch guards (`~/github/highwayoflife/agent-kaizen/scripts/codex-dispatch`). Packet 04 had already ported the original guards to the live copy at `~/.claude/bin/codex-dispatch`. Port the 07 fixes to the live copy too, and keep every live-only feature (`-p 3d`, `--mcp`, `--unity-project`, the model defaults, the `CODEX_DISPATCH_MODEL` default, the sibling `codex-run` preference).

**Working copy:** the live files are staged in the git repo `/private/tmp/claude-501/-Users-highwayoflife-github-highwayoflife-agent-visualization-plugin/350e6cbe-9fde-473d-93a0-8cfca3fd3d9e/scratchpad/live-bin` (this run's working directory) as `bin/codex-dispatch` and `bin/codex_common.py`. Edit those. The orchestrator copies them back after the checks pass.

## Inputs

- The 07 change as a patch against the plugin script: `~/github/highwayoflife/agent-kaizen/docs/plans/2026-11-06-weekly-waste-fixes/briefs/08-plugin-guard-fixes.patch`. Apply the same behaviour by hand where hunks don't apply cleanly.
- The 07 brief, which describes the three fixes: `~/github/highwayoflife/agent-kaizen/docs/plans/2026-11-06-weekly-waste-fixes/briefs/07-guard-fixes.md`.
- The tests: `~/github/highwayoflife/agent-kaizen/tests/test_dispatch_guards.py` (17 tests).

## Acceptance

1. `tree_snapshot` handles nested repos, directories and other non-regular entries without reading them as files. Any OSError gives `None` plus one `WARNING: tree snapshot failed: <reason>; require-change skipped` line.
2. The `-o` output directory is excluded from the fingerprint when it is inside cwd.
3. The Sol guard checks the resolved model, including the `CODEX_DISPATCH_MODEL` default and the 3d/engineer defaults, using the whole-token regex `(^|[^a-z0-9])sol([^a-z0-9]|$)`.
4. Messages and report lines match the plugin copy word for word.
5. The check below passes. It currently fails 3 of 17.

## Scope

- Edit only `bin/codex-dispatch`, plus `bin/codex_common.py` if a helper must live there.
- Do not edit anything in `~/github/highwayoflife/agent-kaizen` or `~/.claude`.
- No commits.

## Checks

- `python3 -m py_compile bin/codex-dispatch bin/codex_common.py`
- `LIVE_BIN=bin /private/tmp/claude-501/-Users-highwayoflife-github-highwayoflife-agent-visualization-plugin/350e6cbe-9fde-473d-93a0-8cfca3fd3d9e/scratchpad/live-guard-check.sh`
