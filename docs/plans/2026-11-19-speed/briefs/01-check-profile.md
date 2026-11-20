# Brief 01: `check-profile` script and unit tests

## Goal and why

Create `scripts/check-profile` (a zero-token, stdlib-only Python 3.9+ profiler for project test and check commands) and its unit test suite `tests/test_check_profile.py`, and register `check-profile` in `scripts/kaizen-link`. Today the plugin has no tool that measures why a project's test or check command is slow (such as macOS `/usr/bin/git` `xcrun` launcher overhead, subprocess storms, or slow `unittest` modules) or compares two timing baselines for `projectCommands.<project>.speedReport`.

## Context

- Follow `AGENTS.md`: Python 3.9+, standard library only, use `python3` (never `python`), no network access, no personal home paths (`/Users/...` or `/home/...`) in tracked files, scratch output in `out/`.
- Follow the CLI and output style of `scripts/flow-report:137-156` and `scripts/experiment-check:165-227`: `#!/usr/bin/env python3`, `argparse` subcommands, short Markdown output by default, `--json` for structured JSON, exit `0` on success, `1` on check/test failure or regression, `2` on usage or input file error.
- `tools/ci-local:72-83` compiles every script in `scripts/` and runs `<script> --help`.
- `tests/test_kaizen_link.py:146-150` (`test_all_scripts_are_registered`) asserts that every file in `scripts/` is registered in `SCRIPTS` in `scripts/kaizen-link:28-53`. Add `"check-profile": "check-profile"` to `SCRIPTS`.
- `scripts/kaizen-project-report:25-27` discards `stdout` when a `projectCommands` command exits non-zero. Therefore `check-profile compare` must exit non-zero (`1`) on regression by default, and also accept `--exit-zero` so `projectCommands.<project>.speedReport` can display regressions in `kaizen-project-report` without modifying `kaizen-project-report`.

## Scope / do not touch

Creates: `scripts/check-profile`, `tests/test_check_profile.py`
Modifies: `scripts/kaizen-link`

Do not touch `scripts/token-audit`, `scripts/kaizen-scheduled`, `scripts/kaizen-project-report`, `skills/`, `README.md`, `.claude-plugin/plugin.json`, or `CHANGELOG.md`.

## Steps

1. Implement `scripts/check-profile` (`chmod +x scripts/check-profile`) with `argparse` subcommands and `--out DIR` (default `out/speed` in cwd; accept `--out` both on the top-level parser and on each subcommand so either position works; write files only under `--out`):
   - `probe [--programs git,python3,node,...] [--runs N] [--threshold-ms MS] [--out DIR] [--json]`:
     - Default `--programs`: `git,python3,node,npm,rg,fd,jq,shellcheck,claude,codex`; default `--runs`: `5`; default `--threshold-ms`: `100.0`.
     - For each program, resolve `which = shutil.which(prog)` and `real = os.path.realpath(which)` when found (record missing programs cleanly without failing). Run `[which, "--version"]` `N` times with `subprocess.run(..., stdin=subprocess.DEVNULL, capture_output=True, timeout=10)`, timing each run with `time.perf_counter()`. Compute `median_ms`, `min_ms`, `max_ms`, and set `flagged = median_ms > threshold_ms`.
     - Write `<out>/probe.json` and print Markdown (or JSON with `--json`) showing each program, resolved real path, median ms, and flagged slow programs. Exit `0`.
   - `run [--trace PROGS] [--junit PATH] [--out DIR] [--json] -- CMD...`:
     - Strip a leading `"--"` from `CMD` if present; if `CMD` is empty, exit `2`.
     - Run `CMD` once untraced: measure `wall_ms` (`time.perf_counter()`), child CPU seconds (`user_s`, `sys_s`) via `resource.getrusage(resource.RUSAGE_CHILDREN)` before/after when `resource` is available (`None` on Windows), and `returncode`.
     - If `--trace PROGS` (comma-separated program names) is given:
       - On Windows (`os.name == "nt"` or `sys.platform == "win32"`), skip tracing, include a clear note (`"tracing skipped on Windows"`) in JSON and Markdown, and do not fail.
       - On POSIX, resolve each program via `shutil.which(prog)` *before* changing `PATH`. Create a temporary wrapper directory inside `--out` (cleaned up in `finally`) and a trace log file `<out>/trace.tsv`. For each found program, create an executable Python script (`#!{sys.executable}` and mode `0o755`) that times `subprocess.run([REAL_BINARY, *sys.argv[1:]])`, truncates `argv[1]` (to 40 chars, tabs/newlines stripped, or `"-"` if absent), appends `prog\targv1\telapsed_ms\n` to `<out>/trace.tsv`, and exits with the child return code.
       - Run `CMD` once more with the wrapper directory prepended to `PATH`. Aggregate per program: `calls`, `total_ms`, `median_ms`, and top `argv[1]` values (up to 5 by `total_ms` / count).
       - State in both JSON (`notes`) and Markdown output that the traced run's wall time includes wrapper overhead (the untraced run is the baseline) and that calls by absolute path bypass the `PATH` wrappers.
     - If `--junit PATH` is given and `PATH` exists after the run, parse `<testcase>` elements with `xml.etree.ElementTree` (`classname`, `name`, `time` in seconds converted to `ms`) and list the slowest tests.
     - Write `<out>/run.json` (including `kind: "run"`, `total_ms` set to untraced `wall_ms`, `untraced`, `traced`, `programs`, `tests`, `notes`), print Markdown or `--json`, and exit with `untraced.returncode`.
   - `unittest [-s DIR] [-p PATTERN] [--top N] [--out DIR] [--json]`:
     - Defaults: `-s tests`, `-p test*.py`, `--top 15`, `--out out/speed`.
     - Discover tests with `unittest.defaultTestLoader.discover(start_dir=args.start_dir, pattern=args.pattern)` and run with a custom `unittest.TextTestResult` subclass (send runner stream output to `io.StringIO()` so stdout stays clean for Markdown/JSON) that times each test with `time.perf_counter()` in `startTest`/`stopTest`.
     - Record per-test `id`, `module`, `ms`, `status` (`ok`, `fail`, `error`, `skip`) and aggregate per-module totals (`module`, `tests`, `total_ms`) and overall `total_ms`. Write `<out>/unittest.json` (`kind: "unittest"`, `total_ms`, `tests`, `modules`, `counts`), print the slowest `--top N` tests and per-module totals in Markdown or `--json`, and exit `0` if `result.wasSuccessful()` else `1`.
   - `hints [PATHS...] [--out DIR] [--json]`:
     - Default `PATHS`: `["tests"]`. Walk text test files (`.py`, `.js`, `.ts`, `.sh`, skipping `.git`, `__pycache__`, `out`, `node_modules`).
     - Scan lines with regexes for: `sleep` (`time\.sleep\s*\(`, `\bsleep\s+[0-9.]`, `setTimeout\s*\(`), `large_timeout` (`timeout\s*=\s*([0-9]+(?:\.[0-9]+)?)` with value `>= 10`), `network` (`urlopen\s*\(`, `\brequests\.(?:get|post|put|delete|head|request)\b`, `https?://(?!localhost|127\.0\.0\.1|\[::1\])[A-Za-z0-9.-]+`), and `subprocess` (`\bsubprocess\.(?:run|Popen|call|check_call|check_output)\b`, `\bos\.system\b`, reporting per-file counts and line numbers).
     - Label output prominently as **hypotheses, not measured results** (`"basis": "hypotheses"` in JSON; `Hypotheses (unmeasured static hints, not measured results)` in Markdown). Write `<out>/hints.json` and exit `0`.
   - `compare BASE.json NEW.json [--threshold PCT] [--exit-zero] [--out DIR] [--json]`:
     - Default `--threshold`: `20.0`. Load both JSON files (exit `2` on missing/invalid JSON).
     - Compare `total_ms`, per-test `ms` (by test `id`/`name`), per-module `total_ms` (by `module`), and per-program `total_ms` and `median_ms` (by program name). Flag any item with `base > 0` and `(new - base) / base * 100.0 > threshold`.
     - Print Markdown or `--json` summary of regressions (or a clean no-regression line). Exit `1` when regressions exist (unless `--exit-zero` is set, which exits `0`), else `0`.
2. Register `"check-profile": "check-profile"` in `SCRIPTS` in `scripts/kaizen-link`.
3. Write `tests/test_check_profile.py` covering `probe` (with a fake slow script that sleeps `0.05` s), `run --trace` + `--junit` + Windows skip via `unittest.mock.patch`, `unittest` (passing and failing tiny fixture suites), `hints` (sleeps, large timeouts, non-localhost URLs, subprocess calls labeled as hypotheses), and `compare` (below threshold, above threshold exiting `1`, and `--exit-zero` exiting `0`). Keep total test runtime under 5 seconds.

## Acceptance criteria

1. `scripts/check-profile` is executable, uses Python 3.9+ stdlib only, answers `--help` on the root command and all five subcommands (`probe`, `run`, `unittest`, `hints`, `compare`), and writes files only under `--out` (default `out/speed`).
2. `probe` measures median startup time and resolved real path of each found program and flags programs above `--threshold-ms` (default 100 ms).
3. `run` reports untraced baseline wall/CPU/exit code, traces named programs via `PATH` wrappers without recursion on POSIX, reports wrapper overhead and absolute-path bypass notes, skips tracing cleanly on Windows, and parses `--junit` XML when given.
4. `unittest` reports slowest tests and per-module totals and preserves pass/fail in its exit code.
5. `hints` detects sleeps, large timeouts, non-localhost network calls, and subprocess spawns per file, and labels all findings as **hypotheses**.
6. `compare` diffs two `run`/`unittest` JSON files and exits non-zero (`1`) with regressed items when slower by more than `--threshold` (default 20%), or `0` with `--exit-zero`.
7. `tests/test_check_profile.py` passes in under 10 seconds, and `tests.test_kaizen_link` and `tests.test_repo` pass.

## Verification

```bash
test -x scripts/check-profile
python3 scripts/check-profile --help
python3 -m unittest tests.test_check_profile tests.test_kaizen_link tests.test_repo
```

## Reporting

Report the files created/modified, the subcommands implemented, and the exact runtime and output of `python3 -m unittest tests.test_check_profile tests.test_kaizen_link tests.test_repo`. Do not commit or push. Stop and report if an assumption is wrong.

## Suggested agent / model / effort and Risk

- **Agent / model / effort:** `codex-engineer` / `terra` / `medium`
- **Risk:** `normal`

## Review delta (binding; overrides anything above that conflicts)

A plan review found gaps in this brief. Apply every item in `docs/plans/2026-11-19-speed/review-sonnet.md` marked for **01** (BLOCKING 1–5 and the 01 minor items): `/bin/sh` wrappers that exec a shared `helper.py` via `shlex.quote`d paths; absolute wrapper dir and log path, log truncated before the traced run; signal exit codes mapped to `128+sig`; REAL = `shutil.which` with the original PATH (no `realpath`); child stdout/stderr go to `<out>/run-untraced.log` / `<out>/run-traced.log` and `--json` stdout must parse as JSON; `unittest` subcommand redirects stdout/stderr and fixes `sys.path` (drop the script dir, insert cwd); module-level `IS_WINDOWS` for tests; guarded `import resource`; every test uses `--out <tmpdir>`; whole test file under 10 s; `probe` records `TimeoutExpired` as errored; `compare` exits 2 on mismatched `kind`, has `--min-delta-ms` (default 50) and sorts and caps its output to 15 lines; the trace report notes that nested calls overlap and that absolute-path calls bypass the wrappers. Each of these gets a unit test where it can be tested.
