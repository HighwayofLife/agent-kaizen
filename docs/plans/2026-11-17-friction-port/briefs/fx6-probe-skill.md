# FX6: host-probe directory evidence, submodule filters, cycle audit lookup

Risk: high. Model: sol / medium.
Sol reason: subtle filesystem traversal fix and clean-filter execution in submodules.

## Items
1. `scripts/host-probe:355` — backtracking through `..` requires search permission on an empty child that can be listed with mode `0400`; if a sibling remains, the probe discards all directory evidence that `518da76` retains. Backtrack via the parent FD you already hold, not via `..`.
2. `scripts/host-probe:199` (FA5/FA6 clean-filter residual) — the filter check covers only the parent repository and runs separately from `git status`; status can still execute clean filters configured in submodules or added after the check. Run status with filters disabled by construction (no check-then-run), including submodules (or `--ignore-submodules` where submodule state is not needed).
3. `skills/cycle/SKILL.md:24` — linked worktrees write refreshed audits to the canonical checkout but never search it, so later runs reuse a stale audit and repeat the refresh. Make the lookup include the canonical checkout's audit dir. An earlier attempt was reverted because it made every interactive cycle run the full review dry run (scanning session logs); the lookup must be a cheap path lookup (a script helper is fine), with no extra review or log scan. Keep `python3 tools/context_budget.py` passing: SKILL.md must not grow its context cost.

## Checks
python3 -m unittest discover -s tests -p 'test_host_probe.py'; test_friction_host_probe.py; test_friction_skill.py; test_hooks.py; test_repo.py; python3 tools/context_budget.py.

## Rules
- Base: branch `release-0.13` (candidate 0.13.0). `518da76` is the 0.12-era base the friction work started from; `v0.12.0` is the last release. Background for each item: `docs/plans/2026-11-17-friction-port/plan.md` section "0.14 known issues" and `gate-results.md`.
- This is the **fix round for the release**: fix every item properly. Do not defer, do not revert a feature away, and do not report an item as accepted. If a race cannot be closed completely with portable Python on macOS and Linux, close it as far as the platform allows AND make the operation detect the conflict afterwards and keep the user's data (keep the displaced content as a recoverable copy, report it, exit non-zero). Losing user data silently is never acceptable.
- For each item: first a test that fails now (red), then the fix (green). Never weaken, skip or delete an existing test. If an existing test pins the unsafe behaviour, change it to pin the safe behaviour and say why in the report.
- Old/new compatibility matters: state written by `v0.12.0` and by `518da76` must still load, recover and undo after upgrading.
- Stay in the files named here plus their tests. Under ~400 changed lines if you can; say so if you must exceed it. Keep `python3 tools/context_budget.py` passing (the budget is nearly full: do not grow hook or skill context text).
- Python 3.9 compatible. Do not commit or push. Do not touch `.claude-plugin/plugin.json`, `CHANGELOG.md` or the version.
- Report: per item FIXED (test name) or PARTIAL (what remains and how it is detected and recovered), files changed, checks run with results.
