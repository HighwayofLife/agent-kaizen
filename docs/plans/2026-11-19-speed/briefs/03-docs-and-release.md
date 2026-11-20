# Brief 03: Script docs, scheduling note, and 0.14.0 release bump

## Goal and why

Document `scripts/check-profile` in `scripts/README.md`, document how to wire `check-profile compare` into `projectCommands.<project>.speedReport` in `docs/scheduling.md`, and bump the plugin release version from `0.13.4` to `0.14.0` in `.claude-plugin/plugin.json` and `CHANGELOG.md`.

## Context

- `AGENTS.md` requires any change under `skills/` or `scripts/` to bump `version` in `.claude-plugin/plugin.json` and add a `## x.y.z (date)` section in `CHANGELOG.md`. `tests/test_repo.py:77-84` (`test_manifest_names_match`) and `tools/ci-local:41-47` enforce that `CHANGELOG.md` has a `## <version>` heading matching `.claude-plugin/plugin.json`.
- `scripts/kaizen-project-report:22,25-27,124-129` runs `projectCommands.<project>.speedReport` with `shell=False` and a 120-second timeout, and includes up to 15 lines of `stdout` under `## Speed` when the command exits `0` (a non-zero exit is rendered as `unavailable: exit <rc>`). `scripts/kaizen-scheduled:654` uses a minimal `PATH`. Therefore:
  - The profile run itself cannot happen inside `speedReport`; `NEW.json` must be produced by a separate step (CI, cron, or a manual `check-profile unittest|run --out ...`), and a stale `NEW.json` will report stale results.
  - `argv` is not `~`-expanded (`shell=False`) and cannot rely on user `PATH` entries, so `speedReport` must use absolute paths, e.g. `["<abs config dir>/bin/check-profile", "compare", "--exit-zero", "<abs base.json>", "<abs new.json>"]`.
- Follow `AGENTS.md` writing rules: plain, short sentences; no marketing language; no unmeasured numbers; no personal home paths (`/Users/...` or `/home/...`).

## Scope / do not touch

Modifies: `scripts/README.md`, `docs/scheduling.md`, `.claude-plugin/plugin.json`, `CHANGELOG.md`

Do not touch `README.md`, `skills/`, `scripts/check-profile`, or `tests/` (Packet 02 runs in parallel and owns `README.md` and `skills/speed/*`).

## Steps

1. In `scripts/README.md` (after `## kaizen-project-report` around line 691), add a `## check-profile` section documenting:
   - Usage and subcommands (`probe`, `run`, `unittest`, `hints`, `compare`), `--out DIR` (default `out/speed`), and `--json`.
   - `probe`: measures `<prog> --version` median startup time and resolved real path, flagging programs above `--threshold-ms` (default 100 ms).
   - `run`: untraced baseline (wall time, child CPU where available, exit code), optional `--trace PROGS` `PATH` timing wrappers on POSIX (noting that traced wall time includes wrapper overhead, untraced is the baseline, nested wrapper calls overlap in `total_ms`, calls by absolute path bypass wrappers, and Windows skips tracing with a note), and optional `--junit PATH` XML parsing.
   - `unittest`: stdlib discovery with per-test and per-module timings while preserving pass/fail exit code.
   - `hints`: static regex scan for sleeps, large literal timeouts, non-localhost network calls, and subprocess spawns per file, labeled as hypotheses.
   - `compare`: diffs two `run`/`unittest` JSON files and exits `1` when total, per-test, per-module, or per-program figures regressed by more than `--threshold PCT` (default 20%) and `--min-delta-ms` (default 50 ms), or `0` with `--exit-zero` (for `projectCommands.<project>.speedReport`).
2. In `docs/scheduling.md` (near the `projectCommands` table and configuration prose at lines 113-127), add a short paragraph explaining how to set `projectCommands.<project>.speedReport` in `<Claude config dir>/agent-kaizen.json`:
   - Use an absolute-path argv list such as `["<abs config dir>/bin/check-profile", "compare", "--exit-zero", "<abs base.json>", "<abs new.json>"]` (or with `"--threshold", "<pct>"`).
   - Explain how `<abs new.json>` is produced: `kaizen-project-report` runs `speedReport` with a 120 s timeout (`scripts/kaizen-project-report:22`), so the profile run cannot happen inside `speedReport`; `<abs new.json>` comes from a separate step (CI, cron, or a manual `check-profile unittest|run --out ...`), and a stale `<abs new.json>` shows a stale result.
   - Note that `argv` is executed with `shell=False` (no `~` expansion) and a minimal scheduler `PATH` (`scripts/kaizen-scheduled:654`), so all paths in the argv list must be absolute.
3. In `.claude-plugin/plugin.json:3`, bump `"version"` from `"0.13.4"` to `"0.14.0"`.
4. In `CHANGELOG.md` (above `## 0.13.4 (2026-11-19)` at line 5), add `## 0.14.0 (2026-11-19)` with an `### Added` section describing `scripts/check-profile` (`probe`, `run`, `unittest`, `hints`, `compare`) and `/agent-kaizen:speed` (`skills/speed/SKILL.md`), written in plain, short sentences.

## Acceptance criteria

1. `scripts/README.md` documents `check-profile` and all five subcommands, flags, output directory, wrapper/Windows notes, and exit codes.
2. `docs/scheduling.md` explains how to configure `projectCommands.<project>.speedReport` with `check-profile compare --exit-zero`, including how `NEW.json` is produced outside `speedReport` (120 s timeout), the stale-result caveat, and why absolute paths without `~` are required (`shell=False` and minimal scheduler `PATH`).
3. `.claude-plugin/plugin.json` version is `"0.14.0"` and `CHANGELOG.md` has a matching `## 0.14.0 (2026-11-19)` entry.
4. `python3 -m unittest tests.test_repo` and `claude plugin validate .` pass.

## Verification

```bash
python3 -m unittest tests.test_repo
claude plugin validate .
```

## Reporting

Report the files modified and the output of `python3 -m unittest tests.test_repo` and `claude plugin validate .`. Do not commit or push. Stop and report if an assumption is wrong.

## Suggested agent / model / effort and Risk

- **Agent / model / effort:** `codex-engineer` / `terra` / `medium`
- **Risk:** `low`
