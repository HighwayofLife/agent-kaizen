# Brief 05: review fixes for `check-profile` and the `speed` skill

## Goal

A batch review of packets 01–03 (uncommitted in this checkout) found the defects below. Fix all of them in `scripts/check-profile`, `tests/test_check_profile.py`, `skills/speed/SKILL.md` and `docs/scheduling.md`. Keep the rules in `AGENTS.md`: Python 3.9+, stdlib only, `python3`, plain short sentences, no home paths. Don't commit or push. Don't touch other files. Don't run the full unittest suite (it takes 16 minutes) or `check-profile unittest -s tests`.

## Fixes

1. **`unittest --json` broken by child output** (`check-profile` around 196–203). A test whose subprocess writes to the inherited fd 1 (e.g. `subprocess.run(['echo','CHILD-NOISE'])`) puts that text into stdout before the JSON or Markdown. Redirect at the fd level: `os.dup2` fds 1 and 2 to `<out>/unittest.log` for the run (flush first), restore in `finally`. Keep the existing `contextlib` redirect too. Test: a fixture test that runs a subprocess `echo`; `--json` stdout must parse.
2. **`compare` writes files** (258–287, `main` ~321). `kaizen-project-report` runs `speedReport` with the project as cwd, so `compare` must not create `out/speed/` or write `compare.json` unless `--out` was given explicitly. Test it.
3. **unittest result statuses** (176–183). A failing `subTest` is recorded `ok`; `expectedFailure` too. Override `addSubTest` (status `fail`/`error` when the subtest has an error), `addExpectedFailure` (`expected_failure`), `addUnexpectedSuccess` (`unexpected_success`). Report fixture errors (setUpClass/module setup, i.e. `result.errors` entries with no recorded test) in the counts. Test subTest failure and expectedFailure.
4. **`script_dir`** (192): use `os.path.realpath(__file__)` so a symlinked install still drops the real `scripts/` dir from `sys.path`. Add a test that a module named like a `scripts/*.py` file in the cwd wins (shadowing check).
5. **Test identity in `compare`** (273–281): when a test row has `classname`, key it as `classname + '.' + name` so JUnit rows from different classes don't collide. Test it.
6. **Malformed input to `compare`** (263–281): `"tests": null` or a non-list collection must exit 2 with a one-line error, never a traceback. Validate with `isinstance`. Test it.
7. **Trace programs** (~129): `os.path.abspath` the `shutil.which` result. A `--trace` program that isn't found gets a note in the report, not silence.
8. **`--junit`** (146–150): if the file is older than the run start, add a "stale JUnit file" note; catch `ParseError`/`ValueError` as a note and still write `run.json` with the run result. Test both.
9. **`run` Markdown** (155–157): add a line with the traced wall time and traced exit code. In the JSON, map a negative traced returncode to `128+sig` the same way as the process exit.
10. **Thresholds test**: add a fixture where the delta is over `--min-delta-ms` but under the percent threshold, and one under the ms floor but over the percent, so each threshold is proven on its own.
11. **Tests hygiene**: give `cli()` a `timeout=` (e.g. 60 s); skip POSIX-shell fixtures on Windows; extend the trace test to use an `--out` path containing a space and a command that does `cd /` before calling the traced program.
12. **Skill and docs**: `skills/speed/SKILL.md` must not let the traced run overwrite the baseline: give each run its own `--out` (e.g. `out/speed/baseline`, `out/speed/traced`) and name the baseline file path exactly. State in the skill and in `docs/scheduling.md` (the `speedReport` note, ~line 122) that `compare` runs with the project as cwd and writes nothing without `--out`.

## Verify

```
python3 -m unittest tests.test_check_profile tests.test_kaizen_link tests.test_repo
python3 tools/context_budget.py --root .
```

`tests.test_check_profile` must stay under 10 s. Report what changed per item and the test runtime.
