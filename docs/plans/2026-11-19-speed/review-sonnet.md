# Plan review (sonnet-plan-reviewer): REVISE

Decomposition, ownership split and references are sound. 02/03 touch disjoint files.

## BLOCKING

1. **01 trace wrapper shebang.** `#!{sys.executable}` breaks on interpreter paths with spaces or over Linux's shebang length limit. Write each wrapper as `#!/bin/sh` + `exec <shlex.quote(sys.executable)> <shlex.quote(helper.py)> <prog> <real> "$@"`, with one shared `helper.py` in the wrapper dir.
2. **01 wrapper paths.** Relative `--out` (default `out/speed`) breaks the PATH entry and log when CMD changes directory. `os.path.abspath` the wrapper dir and log; pass the log path to wrappers as an absolute path (env var or embedded). Truncate/create the log before the traced run so a stale `trace.tsv` is never aggregated.
3. **01 wrapper exec/exit semantics.** With `subprocess.run`, a signal death gives a negative returncode and `sys.exit(-9)` becomes 247. Map `rc<0` to `128+sig` (or re-raise the signal); inherit stdin/stdout/stderr; add a unit test for this. REAL is the `shutil.which` result resolved with the original PATH before any PATH change, NOT `realpath` (realpath breaks venv `python3` and multi-call binaries).
4. **01 `run` child output.** Inherited child stdout/stderr corrupts Markdown/`--json` stdout. Redirect child output to `<out>/run-untraced.log` and `<out>/run-traced.log`; acceptance test that `--json` stdout parses as JSON. Same for `unittest`: wrap the run in `contextlib.redirect_stdout/stderr`, not only the runner stream.
5. **01 `unittest` sys.path.** `python3 scripts/check-profile` puts `scripts/` at `sys.path[0]`, unlike `python3 -m unittest discover`; project modules importable via cwd won't import and `scripts/*.py` (`codex_common`, `kaizen_credentials`) can shadow project modules. Before discovery remove the script dir from `sys.path`, insert `os.getcwd()`, pass `top_level_dir=None`.
6. **02 and 03 speedReport guidance.** Say how NEW.json is produced: `kaizen-project-report` runs the command with a 120 s timeout (`kaizen-project-report:22`), so the profile run cannot happen inside `speedReport`. NEW comes from a separate step (CI, cron, or a manual `check-profile unittest|run --out ...`). argv is not `~`-expanded (`shell=False`) and the scheduler PATH is minimal (`kaizen-scheduled:654`). Example argv with absolute paths: `["<abs config dir>/bin/check-profile","compare","--exit-zero","<abs base.json>","<abs new.json>"]`. A stale NEW shows a stale result.
7. **04 motivating case.** At `42efb34`, `scripts/kaizen-backup` calls Git by absolute path (`TRUSTED_GIT`), only the test's own `self.git()` goes via PATH (`tests/test_backup_commit.py:50`). `--trace git` will not show the slow backup calls; `probe` is what catches the xcrun launcher. Reword: record what the wrapper shows and that absolute-path calls bypass it; add `probe` on that host as the detection evidence; don't claim the trace reproduces the 10 s step.

## Minor

- 01: don't patch `os.name` in tests (breaks pathlib on POSIX); use a module-level `IS_WINDOWS` and patch that. Guard `import resource` with try/except.
- 01: test runtime budget inconsistent (5 s vs 10 s): use under 10 s.
- 01: every test passes `--out <tmpdir>` so tests never write `out/speed/` (would clobber packet 04's dogfood outputs).
- 01: `probe` catches `subprocess.TimeoutExpired` and records the program as errored. `compare` exits 2 when the two files have different `kind`.
- 01: `compare` gets `--min-delta-ms` (default 50) so 5→10 ms isn't a regression; sort and cap output to fit the 15 lines `kaizen-project-report` shows.
- 01: note in the report that nested wrapper calls (git calling git through PATH) overlap in `total_ms`.
- 02: drop "10-step" (11 bullets listed).
- 04: plan.md already exists (fix "Creates"). Verify line runs two 2+ minute runs: run them in the background or with a raised timeout. `compare X X` self-diff only proves no crash; say so.
- 04: before finishing run `rg '/Users/|/home/' docs/plans` (probe output has real paths; sanitize).
