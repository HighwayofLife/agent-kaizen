# Brief 06: final-audit fixes for `check-profile`

## Goal

A read-only final audit (Astra, high) of the uncommitted `check-profile` change found the issues below. Fix each in `scripts/check-profile`, `tests/test_check_profile.py`, `skills/speed/SKILL.md` and `scripts/README.md`. Add a regression test for each code item where practical. Rules: `AGENTS.md` (Python 3.9+, stdlib only, plain short sentences, no home paths). Don't commit or push. Don't touch other files. Don't run the full unittest suite (16 minutes) or `check-profile unittest -s tests`.

Expected fixes, one per finding:
1. Relative PATH entries: resolve each traced program's real path against the original cwd only if absolute; when `shutil.which` would return a relative-PATH hit, skip tracing that program with a note (don't pin a different binary).
2. Wrapper must not close inherited fds: use `close_fds=False` (or `os.execv` after logging start, recording end via a fork), so open descriptors pass through.
3. Duplicate JUnit identities: aggregate duplicates (sum and count) in both profiles before comparing, so a self-compare shows no regression.
4. `unittest` stream replacement: don't replace stdout/stderr with `StringIO`; rely on the fd-level redirect, with `sys.stdout`/`sys.stderr` pointing at real text streams over the log (keep `.buffer` and `.fileno()`).
5. Flush `sys.stdout`, `sys.stderr`, `sys.__stdout__`, `sys.__stderr__` before restoring fds.
6. JUnit with both runs: parse the JUnit file after the untraced run (before the traced rerun) and keep those per-test times.
7. Set `sys.dont_write_bytecode = True` (restore after) during `unittest` discovery so no `__pycache__` is written outside `--out`.
8. Concurrent traces: give each run a unique trace log name (pid + timestamp) inside `--out` and aggregate only that file.
9. Subtest status: precedence error > fail > ok > skip; a later skip never overwrites an earlier failure.
10. `compare`: non-numeric timing values exit 2 with a one-line error.
11. `compare`: non-string test ids exit 2 with a one-line error (no traceback, never exit 1).
12. Use an ASCII `->` instead of the Unicode arrow in Markdown output (Windows CP1252 pipes).
13. Trace log: write argv with `errors="surrogateescape"` / `backslashreplace` so non-UTF-8 argv never fails the wrapper; the wrapper's exit code must always be the real program's.
14. `skills/speed/SKILL.md`: before writing `docs/kaizen/speed-<date>.md`, replace the home directory with `~` in any resolved path (probe output) and say so.
15. `hints` network regex: treat `localhost`, `127.0.0.1` and `[::1]` followed by a quote, `/`, `:` or end as loopback.
16. `scripts/README.md` (~line 705): say `compare` writes `compare.json` only when `--out` is given.

## Verify

```
python3 -m unittest tests.test_check_profile tests.test_kaizen_link tests.test_repo
python3 tools/context_budget.py --root .
```

`tests.test_check_profile` must stay under 10 s. Report per item what changed and the test runtime.

## Audit text (verbatim)

- `scripts/check-profile:131` — Wrappers pin relative `PATH` entries to the profiler’s starting directory — with `PATH=.` and a later `cd`, tracing can execute a different binary from the baseline.
- `scripts/check-profile:81` — The wrapper closes inherited file descriptors before launching the real program — a command given an open descriptor succeeded directly and failed with `EBADF` under the helper.
- `scripts/check-profile:321` — Duplicate JUnit identities overwrite earlier baseline rows — comparing an identical profile to itself reported a 100% regression for two `C.same` observations of 200 and 100 ms.
- `scripts/check-profile:232` — Replacing stdout and stderr with `StringIO` removes `.buffer` and usable `.fileno()` — passing tests that write bytes or pass a stream to a subprocess fail under profiling.
- `scripts/check-profile:240` — Original streams are restored without flushing output buffered during the suite — a write through `sys.__stdout__` escaped the log and appeared before the JSON.
- `scripts/check-profile:155` — JUnit XML is read only after the traced rerun — when both runs write the same file, `run.json` pairs untraced wall time with wrapper-inflated per-test timings.
- `scripts/check-profile:234` — Discovery imports project modules with bytecode caching enabled — profiling can create `__pycache__` beside tests and source files outside `--out`.
- `scripts/check-profile:134` — Concurrent traces sharing `--out` truncate and append to the same `trace.tsv` — either report can lose its own calls or count another run’s calls.
- `scripts/check-profile:191` — A skipped subtest overwrites an earlier failure status — a reproduced fail-then-skip case exited 1 while reporting zero failures and one skip.
- `scripts/check-profile:308` — Invalid timing values are silently discarded — a new profile with `"total_ms":"bad"` produced an empty regression list and exit 0.
- `scripts/check-profile:321` — A list-valued test ID raises an uncaught `TypeError` — malformed input produces a traceback and exit 1, the status reserved for regressions.
- `scripts/check-profile:334` — The Markdown arrow cannot be encoded on a Windows CP1252 output pipe — a regression with `--exit-zero` returned 2, hiding it from `speedReport`.
- `scripts/check-profile:88` — Strict UTF-8 trace logging rejects valid non-UTF-8 POSIX filename arguments — the helper returned 1 after the real command succeeded.
- `skills/speed/SKILL.md:20` — The skill asks for resolved executable paths in a report under `docs/kaizen/` without home-path redaction — user-local tool installs can put a personal path into a tracked report.
- `scripts/check-profile:262` — A closing quote after bare `localhost` or `127.0.0.1` defeats the loopback exclusion — ordinary local fixture URLs are reported as external-network hints.
- `scripts/README.md:705` — The docs say every subcommand saves JSON by default — callers following the documented `compare` invocation will find no `out/speed/compare.json` unless they supply `--out`.
