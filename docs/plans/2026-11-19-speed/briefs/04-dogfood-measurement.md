# Brief 04: Dogfood measurement and end-to-end verification

## Goal and why

Run `scripts/check-profile` end-to-end on this repository (`probe`, `unittest -s tests`, `hints tests`, `compare`) and on a temporary pre-0.13.3 worktree (`42efb34`), record the trimmed measured outputs in `docs/plans/2026-11-19-speed/plan.md`, clean up the temporary worktree, and run the full repository check suite.

## Context

- Depends on Packets 01, 02, and 03.
- Planner-guide end-to-end gate rule: a plan that adds tooling ends with a packet that runs the new tools end-to-end on real input and records the trimmed output in `plan.md`.
- Privacy rule (`tests/test_repo.py:129-136`): never write `/Users/...` or `/home/...` into `docs/plans/2026-11-19-speed/plan.md`. Because `check-profile probe` prints resolved real paths, sanitize any user home prefix to `~` before pasting into `plan.md` (system paths like `/usr/bin/git` or `/Library/Developer/CommandLineTools/usr/bin/git` are allowed) and check with `rg '/Users/|/home/' docs/plans`.
- Motivating case at `42efb34`: in pre-0.13.3 commit `42efb34`, `scripts/kaizen-backup` already invoked Git by absolute path (`TRUSTED_GIT`), while only the test harness's own `self.git()` (`tests/test_backup_commit.py:50`) invokes `git` via `PATH`. Consequently, `check-profile run --trace git` on `tests.test_backup_commit` at `42efb34` captures only the test's `PATH`-based `self.git()` calls and demonstrates that absolute-path calls in `scripts/kaizen-backup` bypass the `PATH` wrapper; it does **not** reproduce the 10 s backup step. Instead, `check-profile probe` on the host is the detection evidence that catches the slow macOS `/usr/bin/git` (`xcrun`) launcher.
- Full test suite runs (`check-profile unittest -s tests` and `python3 -m unittest discover -s tests`) each take 2+ minutes on this repository; run them in the background or with a raised timeout.

## Scope / do not touch

Modifies: `docs/plans/2026-11-19-speed/plan.md`

Do not modify any product code or tests unless a verification check uncovers a bug (if so, stop and report). All temporary profiler outputs and the temporary worktree must stay under `out/` (`out/speed/` and `out/wt-0132`), and `out/wt-0132` must be removed before finishing.

## Steps

1. Run `python3 scripts/check-profile probe --out out/speed` on this checkout and capture the output as the host detection evidence for tool startup times (such as `/usr/bin/git`).
2. Run `python3 scripts/check-profile unittest -s tests --top 15 --out out/speed` (with a raised timeout or in the background, as the full suite takes 2+ minutes) and capture total runtime, the top slowest tests, and the slowest test modules.
3. Run `python3 scripts/check-profile hints tests --out out/speed` and the zero-delta smoke check `python3 scripts/check-profile compare --exit-zero out/speed/unittest.json out/speed/unittest.json` (noting that the self-diff only verifies `compare` runs without crashing on real `unittest.json` output).
4. Check whether commit `42efb34` is available locally (`git cat-file -e 42efb34^{commit}`). If practical:
   - Create a temporary worktree: `git worktree add out/wt-0132 42efb34`
   - From `out/wt-0132`, run `python3 ../../scripts/check-profile run --trace git --out ../speed/wt-0132 -- python3 -m unittest tests.test_backup_commit`
   - Record what the `PATH` wrapper captures (untraced vs traced wall time, `git` call count, total ms, median ms, and top `argv[1]` subcommands from `tests/test_backup_commit.py:50`'s `self.git()`) and explicitly note that `scripts/kaizen-backup`'s `TRUSTED_GIT` calls use an absolute path and bypass the `PATH` wrapper, so the trace does not reproduce the 10 s step (`probe` is the detection evidence).
   - Remove the worktree: `git worktree remove --force out/wt-0132` and verify `out/wt-0132` is gone.
5. Update `docs/plans/2026-11-19-speed/plan.md` (`### Dogfood results` and the Packet 04 table row) with the trimmed measured outputs from Steps 1-4, sanitizing any user home paths to `~`.
6. Run `rg '/Users/|/home/' docs/plans` to confirm no personal home paths were introduced, then run the full repository verification gate (running `python3 -m unittest discover -s tests` with a raised timeout or in the background):
   - `python3 -m unittest discover -s tests`
   - `python3 tools/context_budget.py --root .`
   - `claude plugin validate .`

## Acceptance criteria

1. `check-profile probe`, `check-profile unittest -s tests`, `check-profile hints tests`, and the `check-profile compare` self-diff smoke check complete cleanly on this repository.
2. The pre-0.13.3 (`42efb34`) worktree trace is run (if `42efb34` is present), records the `PATH`-traced `self.git()` calls and the fact that absolute-path `TRUSTED_GIT` calls bypass the wrapper (without claiming the trace reproduces the 10 s step), and `out/wt-0132` is removed afterwards (`git worktree list` shows no `out/wt-0132`).
3. `docs/plans/2026-11-19-speed/plan.md` contains the trimmed measured outputs from `probe` (detection evidence), `unittest -s tests`, and the `42efb34` `run --trace git` check, and `rg '/Users/|/home/' docs/plans` finds no matches.
4. The full test suite (`python3 -m unittest discover -s tests`), `tools/context_budget.py`, and `claude plugin validate .` pass.

## Verification

Run the two full-suite commands (`check-profile unittest -s tests` and `python3 -m unittest discover -s tests`) with a raised timeout (or in the background) since each takes 2+ minutes:

```bash
python3 scripts/check-profile probe --out out/speed
python3 scripts/check-profile unittest -s tests --top 15 --out out/speed
! rg '/Users/|/home/' docs/plans
python3 -m unittest discover -s tests
python3 tools/context_budget.py --root .
claude plugin validate .
```

## Reporting

Report the trimmed measurements recorded in `docs/plans/2026-11-19-speed/plan.md`, confirmation that `rg '/Users/|/home/' docs/plans` returned no matches, and the final pass counts/runtime of `python3 -m unittest discover -s tests`. Do not commit or push.

## Suggested agent / model / effort and Risk

- **Agent / model / effort:** `haiku-engineer` / `haiku` / `high` (or orchestrator directly)
- **Risk:** `low`
