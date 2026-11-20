---
name: speed
description: "Profile test and check commands, rank measured time sinks, and verify speed improvements."
disable-model-invocation: true
argument-hint: "[propose|safe|auto|yolo]"
---

# Speed: profile and speed up tests and checks

**Plugin root:** `${CLAUDE_PLUGIN_ROOT}`. If that is still a `${...}` placeholder, use the folder that contains `skills/` (this file is `skills/<name>/SKILL.md`), and substitute that path, in quotes, wherever this skill uses `CLAUDE_PLUGIN_ROOT`.
**Not in Claude Code?** Read `docs/hosts.md` in the plugin root first. Skip steps that only work in Claude Code, and follow its propose-only rule before changing any host configuration.

**Changes:** test and check speed proposals, and fixes allowed by the selected autonomy mode.

**Autonomy:** follow `${CLAUDE_PLUGIN_ROOT}/docs/autonomy.md`. The mode comes from the skill argument (`propose`, `safe`, `auto` or `yolo`), else `docs/kaizen/config.json`, else `agent-kaizen.json` in your Claude config dir, else `propose`. Apply only changes the mode allows. Hard stops always ask. Respect `maxChangesPerRun` and summarize what was applied, skipped and rolled back.

## Task

1. Find the project's test and check commands in `AGENTS.md`, `CLAUDE.md`, `.github/workflows/*.yml`, `package.json`, `Makefile` or `pyproject.toml`.
2. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check-profile" probe --out out/speed` to measure tool startup. Record the median `<prog> --version` time and real path. Flag slow shims over 100 ms, such as the macOS `/usr/bin/git` `xcrun` launcher.
3. Take an untraced baseline with `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check-profile" run --out out/speed/baseline -- <check-cmd>`. Add `--junit <path>` before `--` when JUnit XML is available. For Python `unittest` suites without a durations flag, use `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check-profile" unittest -s tests --out out/speed/baseline`. The baseline file is `out/speed/baseline/run.json` for `run` or `out/speed/baseline/unittest.json` for `unittest`.
4. Trace programs the suite spawns with `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check-profile" run --trace <progs> --out out/speed/traced -- <check-cmd>`, using a comma-separated list such as `git,python3,node`. Traced wall time includes wrapper overhead; use the untraced run as the baseline. Calls by absolute path bypass `PATH` wrappers.
5. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check-profile" hints <test-directory>` to collect static hypotheses: sleeps, large literal timeouts, non-localhost network calls and subprocess spawns per file. When CI logs exist, compare per-test or job times across platforms. Use `gh run view --log` if `gh` is available and authenticated; otherwise skip it.
6. Rank findings by **measured seconds saved**, stating the basis and sample count. Keep **hypotheses** from `hints` strictly separate from measured findings. Direct host contention, such as indexers, antivirus or tool-call stalls, to `/agent-kaizen:friction`. Direct game or engine suite tier restructuring to `/agent-kaizen:test-loop`. Before writing the report to `docs/kaizen/speed-<date>.md`, replace the home directory with `~` in all resolved paths from probe output.
7. Apply fixes only as allowed by `${CLAUDE_PLUGIN_ROOT}/docs/autonomy.md`. Back up each change with `kaizen-backup`, verify it immediately, and take before and after `check-profile` measurements for every applied fix. Roll back on verification failure or no improvement. Add a row to `docs/kaizen/LEDGER.md` with the before and after measurements, metric command and review date.

Suggest setting `projectCommands.<project>.speedReport` in the global `agent-kaizen.json` to an absolute-path argv list, for example:

```json
["<abs config dir>/bin/check-profile", "compare", "--exit-zero", "<abs base.json>", "<abs new.json>"]
```

`kaizen-project-report` runs `speedReport` with the project as its cwd, `shell=False` and a 120-second timeout. `compare` writes nothing without an explicit `--out`. It does not expand `~`, and the scheduler uses a minimal `PATH`. Run the profile separately in CI, cron, or manually with `check-profile unittest|run --out ...` to produce `<abs new.json>`. A stale new JSON file produces a stale result.
