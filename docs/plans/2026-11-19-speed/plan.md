# Plan: `speed` skill and `check-profile` script

## Summary

Add a zero-token stdlib profiler script (`scripts/check-profile`) and a user-invoked `/agent-kaizen:speed` skill (`skills/speed/SKILL.md`) that find what makes a project's test and check commands slow, distinguish measured time sinks from static file hints, propose or apply fixes under `docs/autonomy.md`, and wire regression checks into `projectCommands.<project>.speedReport`.

## Goal / non-goals

- **Goals:**
  1. Ship `scripts/check-profile` (Python 3.9+, stdlib only, executable, `--help`, Markdown + `--json`, outputs only under `--out` defaulting to `out/speed/`) with subcommands `probe`, `run`, `unittest`, `hints`, and `compare`.
  2. Ship fast deterministic unit tests in `tests/test_check_profile.py` (< 10 s total).
  3. Ship `skills/speed/SKILL.md` (plus `skills/speed/agents/openai.yaml`) following `docs/autonomy.md` and writing `docs/kaizen/speed-<date>.md`.
  4. Update `README.md`, `scripts/README.md`, `docs/scheduling.md`, `.claude-plugin/plugin.json` (`0.13.4` -> `0.14.0`), and `CHANGELOG.md` (`## 0.14.0 (2026-11-19)`).
  5. Dogfood `check-profile` on this repository (`probe` as detection evidence for slow tool shims, `unittest`, `hints`, `compare`) and on pre-0.13.3 commit `42efb34` in a temporary worktree (showing what `PATH` wrappers capture vs absolute-path calls that bypass them) and record the measured results in this plan.
- **Non-goals:**
  - Modifying `scripts/token-audit`, `scripts/kaizen-scheduled`, or `scripts/kaizen-project-report`.
  - Restructuring this repo's test runner or adding third-party dependencies.
  - Replacing `/agent-kaizen:friction` (host contention / tool-call friction) or `/agent-kaizen:test-loop` (game/engine test tiers).

## Context

- `scripts/kaizen-scheduled:83-96` and `scripts/kaizen-project-report:124-129` already support `projectCommands.<project>.slowTests` and `projectCommands.<project>.speedReport`, running the configured argv list with a 120-second timeout (`scripts/kaizen-project-report:22`) and embedding up to 15 stdout lines under `## Slow tests` and `## Speed`.
- `scripts/kaizen-project-report:25-27` treats any non-zero exit code from a configured command as `unavailable: exit <rc>` and ignores `stdout`. Therefore `check-profile compare` exits non-zero (`1`) on regression by default for CLI/CI use and accepts `--exit-zero` so `projectCommands.<project>.speedReport` renders the regression lines in `kaizen-project-report` without changing `kaizen-project-report`.
- `tests/test_kaizen_link.py:146-150` asserts that every file in `scripts/` (other than `README.md`, `__pycache__`, and dot-files) is registered in `SCRIPTS` in `scripts/kaizen-link:28-53`.
- `tests/test_repo.py:44-52,77-100,110-136` enforces the exact two-line `PREAMBLE` on every skill, `skills/<name>/agents/openai.yaml`, `${CLAUDE_PLUGIN_ROOT}/...` target existence, `README.md` skill listing parity, `plugin.json` / `CHANGELOG.md` version matching, and no personal home paths in any non-ignored file.
- `tools/ci-local:64-83` runs `tools/context_budget.py`, compiles every script in `scripts/`, and runs `<script> --help`.

## Approach

- **Single stdlib script `scripts/check-profile`** structured like `scripts/flow-report` and `scripts/experiment-check`: `argparse` subcommands (`probe`, `run`, `unittest`, `hints`, `compare`), `--out DIR` (default `out/speed`), `--json` on all subcommands, and concise Markdown output by default.
  - `probe`: resolves each program (`--programs`, default `git,python3,node,npm,rg,fd,jq,shellcheck,claude,codex`) via `shutil.which` + `os.path.realpath`, times `<prog> --version` across `--runs N` (default 5), computes median/min/max ms, and flags programs above `--threshold-ms` (default 100 ms).
  - `run`: runs `CMD...` once untraced (`time.perf_counter()` wall time, child user+sys CPU delta via `resource.getrusage(resource.RUSAGE_CHILDREN)` where available, exit code). When `--trace PROGS` is given on POSIX, resolves each named program before changing `PATH`, places small timing wrappers first on `PATH` in a temporary subfolder under `--out`, runs `CMD...` once more, and aggregates calls, total ms, median ms, and top truncated `argv[1]` values per program from the wrapper log. Reports explicitly that traced wall time includes wrapper overhead (untraced is baseline), that nested wrapper calls overlap in `total_ms`, and that calls by absolute path bypass wrappers. On Windows (`os.name == 'nt'`), skips tracing with a clear note and exit code from the untraced run. Parses `--junit PATH` with `xml.etree.ElementTree` when provided.
  - `unittest`: runs `unittest.defaultTestLoader.discover(start_dir, pattern)` with a timing `unittest.TextTestResult` subclass that records per-test elapsed ms and aggregates per-module totals, printing the slowest `--top N` tests and modules while preserving pass/fail in the exit code.
  - `hints`: regex-scans test files under `PATHS...` (default `tests`) for sleeps (`time.sleep`, `sleep `, `setTimeout`), large literal timeouts (`timeout >= 10` s or `>= 10000` ms), non-localhost network calls (`urlopen`, `requests.`, `http://`/`https://` other than `localhost`/`127.0.0.1`/`[::1]`), and subprocess spawns per file. Labels all output as **hypotheses**, never measured results.
  - `compare`: diffs two `run` or `unittest` JSON files (`BASE.json`, `NEW.json`) across total wall time, per-test times, per-module totals, and per-program traced totals; prints items that regressed by more than `--threshold PCT` (default 20%) and `--min-delta-ms` (default 50 ms), capped to fit the 15-line `kaizen-project-report` budget, and exits `1` on regressions (`0` when `--exit-zero` is passed or when no item regressed; `2` on usage/file/kind-mismatch error).
- **Rejected alternatives:**
  - *`strace`/`dtrace`/`dtruss` for subprocess tracing:* requires root/SIP configuration on macOS and is non-portable; `PATH` wrappers are portable across macOS and Linux with zero privileges.
  - *Modifying `kaizen-project-report` to show stdout on exit 1:* unnecessary once `check-profile compare` provides `--exit-zero`, keeping `kaizen-project-report` and its existing failure tests untouched.

## Decisions needed

None. The design is settled in the brief.

## Assumptions

- `scripts/kaizen-link` may be updated with `"check-profile": "check-profile"` in Packet 01 so `tests/test_kaizen_link.py` continues to pass.
- `skills/speed/agents/openai.yaml` is created alongside `skills/speed/SKILL.md` in Packet 02 so `tests/test_repo.py` and `tools/context_budget.py` pass.
- `README.md` is updated in Packet 02 (rather than Packet 03) because `tests/test_repo.py:123-127` requires every `skills/*/SKILL.md` folder to be listed in `README.md` at all times.
- `check-profile compare` exits `1` on regression by default and supports `--exit-zero` for `projectCommands.<project>.speedReport`.

## Packets

| ID | Title | Depends on | Parallel group | Agent / model / effort | Risk | Size | Verify |
|---|---|---|---|---|---|---|---|
| 01 | `check-profile` script and unit tests | - | G1 | `codex-engineer` / `terra` / `medium` | `normal` | M | `python3 -m unittest tests.test_check_profile tests.test_kaizen_link tests.test_repo` |
| 02 | `speed` skill, sidecar, and README entry | 01 | G2 | `codex-engineer` / `terra` / `medium` | `low` | S | `python3 -m unittest tests.test_repo && python3 tools/context_budget.py --root . && claude plugin validate .` |
| 03 | Script docs, scheduling note, and 0.14.0 release bump | 01 | G2 | `codex-engineer` / `terra` / `medium` | `low` | S | `python3 -m unittest tests.test_repo && claude plugin validate .` |
| 04 | Dogfood measurement (`probe` detection evidence, `unittest`, and `42efb34` `PATH` vs absolute-path trace check) and end-to-end verification | 01, 02, 03 | G3 | `haiku-engineer` / `haiku` / `high` (or orchestrator) | `low` | S | `python3 scripts/check-profile probe --out out/speed && python3 scripts/check-profile unittest -s tests --out out/speed && python3 -m unittest discover -s tests` |

### Group file ownership

- **G1:** Packet 01 owns `scripts/check-profile`, `scripts/kaizen-link`, `tests/test_check_profile.py`.
- **G2 (parallel):**
  - Packet 02 owns `skills/speed/SKILL.md`, `skills/speed/agents/openai.yaml`, `README.md`.
  - Packet 03 owns `scripts/README.md`, `docs/scheduling.md`, `.claude-plugin/plugin.json`, `CHANGELOG.md`.
- **G3:** Packet 04 owns `docs/plans/2026-11-19-speed/plan.md` (and scratch output under `out/speed/`).

## Traceability

| Requirement | Packet |
|---|---|
| `scripts/check-profile` (`probe`, `run`, `unittest`, `hints`, `compare`, `--help`, `--out`, `--json`, stdlib only, Python 3.9+) | 01 |
| Fast deterministic unit tests in `tests/test_check_profile.py` (< 10 s) | 01 |
| `skills/speed/SKILL.md` + `skills/speed/agents/openai.yaml` + `README.md` table row & friction mention | 02 |
| `scripts/README.md` section, `docs/scheduling.md` `speedReport` note, `plugin.json` `0.14.0`, `CHANGELOG.md` entry | 03 |
| Dogfood `check-profile probe` (launcher detection evidence) & `unittest` on this repo + pre-0.13.3 `42efb34` worktree trace (showing `PATH` calls vs absolute-path bypass) + full test suite | 04 |

## End-to-end verification

Packet 04 runs the new tool end-to-end on this repository and pastes the trimmed outputs below:

1. `python3 scripts/check-profile probe --out out/speed` (primary detection evidence for slow tool launchers such as macOS `/usr/bin/git` `xcrun`)
2. `python3 scripts/check-profile unittest -s tests --top 15 --out out/speed`
3. Pre-0.13.3 worktree check (`git worktree add out/wt-0132 42efb34`, `python3 scripts/check-profile run --trace git --out out/speed/wt-0132 -- python3 -m unittest tests.test_backup_commit`, then `git worktree remove --force out/wt-0132`): records what the `PATH` wrapper captures (`self.git()` in `tests/test_backup_commit.py:50`) and that `scripts/kaizen-backup`'s `TRUSTED_GIT` calls use an absolute path and bypass the `PATH` wrapper (so the trace does not reproduce the 10 s backup step; `probe` is the detection evidence)
4. Full repository gate: `python3 -m unittest discover -s tests`, `python3 tools/context_budget.py --root .`, `claude plugin validate .`, and `! rg '/Users/|/home/' docs/plans`

### Dogfood results

Recorded under "Status (2026-11-19)" below (Packet 04 done).

## Risks and mitigations

- **Wrapper recursion in `run --trace`:** If a wrapper invokes the program name via `PATH`, it loops infinitely. Mitigation: resolve every traced program with `shutil.which` on the original `PATH` before prepending the wrapper directory, and pass the resolved binary path to the shared wrapper helper.
- **Absolute-path calls bypass `PATH` wrappers in `run --trace`:** Code that invokes a binary by absolute path (such as `TRUSTED_GIT` in `scripts/kaizen-backup` at `42efb34`, where only `tests/test_backup_commit.py:50`'s `self.git()` goes through `PATH`) bypasses `PATH` wrappers, so `run --trace git` does not capture those calls or reproduce the 10 s backup step. Mitigation: state the absolute-path bypass explicitly in `run --trace` reports and briefs, and use `check-profile probe` as the detection evidence for slow tool launchers (such as `/usr/bin/git` `xcrun`).
- **Windows compatibility for `run --trace`:** POSIX `/bin/sh` wrappers on `PATH` do not work reliably on Windows. Mitigation: detect `os.name == 'nt'` (or `sys.platform == 'win32'`), skip the traced pass with an explicit note in the JSON and Markdown report, and return the untraced baseline result.
- **Non-zero exit and timeout in `kaizen-project-report`:** `kaizen-project-report` runs `speedReport` with a 120 s timeout (`shell=False`, minimal `PATH`, no `~` expansion) and discards `stdout` on non-zero exit. Mitigation: generate `NEW.json` in a separate CI, cron, or manual `check-profile` step, and configure `speedReport` with absolute paths and `check-profile compare --exit-zero`.
- **Privacy test failure on plan/report files:** `tests/test_repo.py` rejects `/Users/...` or `/home/...` in any non-ignored file, and `probe` prints resolved paths. Mitigation: write all outputs from `check-profile` under `out/speed/` (git-ignored), sanitize any home-directory prefixes to `~` before pasting into `plan.md`, and check with `rg '/Users/|/home/' docs/plans`.

## Rollout / rollback

- All changes are additive (`scripts/check-profile`, `tests/test_check_profile.py`, `skills/speed/*`, docs, and version bump to `0.14.0`).
- Rollback is a single revert of the plan's commits (or removing the new files and restoring `scripts/kaizen-link`, `README.md`, `scripts/README.md`, `docs/scheduling.md`, `.claude-plugin/plugin.json`, and `CHANGELOG.md`).

## Open questions

None.

## Status (2026-11-19)

| ID | Status | Notes |
|---|---|---|
| 01 | done | Terra medium, 0 resumes; review delta applied |
| 02 | done | Terra medium, 0 resumes |
| 03 | done | Terra medium, 0 resumes; version 0.14.0 |
| 05 | done | Batch review fixes (sonnet-verifier + Sol cross-review, 12 minor, no blocking) |
| 06 | done | Final audit fixes (Astra high, 16 findings) |
| 04 | done (orchestrator) | Dogfood results below |

### Dogfood results (this repo, macOS, other agent jobs running at the same time)

- Full suite, plain `python3 -m unittest discover -s tests`: 1656 tests, 994 s, OK (skipped=3).
- `check-profile unittest -s tests`: 977 s total. Slowest tests: `test_friction_apply.BrokerLedgerTests.test_scheduled_local_commits` 77.6 s, `test_copied_install_undo_and_bookkeeping_recovery` 50.8 s, `test_backup_commit...test_backup_lifecycle_with_only_the_git_shim` 24.1 s. Slowest modules: `test_backup_commit` 175.6 s (91 tests), `test_friction_apply` 147.0 s (33 tests), `test_friction_review` 64.5 s (107 tests). About six timeout tests take about 5.4 s each.
- `check-profile run --trace git,python3,sh` on the slowest test: 74.2 s untraced; 1208 `git` calls through PATH took 9.4 s in total; 28 Python child processes took 2.1 s. Most of the time is in-process or in absolute-path calls (`kaizen-backup` runs Git by absolute path), which the wrappers do not see.
- `check-profile probe`: `/usr/bin/git` starts in 11 ms on this host, so the xcrun launcher problem does not reproduce here; `probe` is the check that would flag it on an affected host. The pre-0.13.3 worktree trace was skipped for that reason.
- Follow-up candidates (not in this plan): profile `test_scheduled_local_commits` in-process (cProfile) to find where the other ~60 s goes; shorten the 5 s timeouts in the timeout tests.
