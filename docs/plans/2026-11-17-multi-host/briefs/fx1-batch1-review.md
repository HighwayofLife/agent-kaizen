# Fix brief fx1: batch-1 review findings (P01, P02, P03, P06)

Repo: Agent Kaizen (read AGENTS.md for rules). Review of the merged range found the items below. Fix all of them. Do not commit or push. Do not touch `.claude-plugin/plugin.json`, `CHANGELOG.md`, `hooks/`, or the hook tests (another packet is editing those).

## Items
1. **Blocking: tests leak `COPILOT_HOME`.** `tests/test_scripts.py` ~line 69, `StubCase.setUp`, pops `CLAUDE_CONFIG_DIR` and `CODEX_HOME` from the environment but not `COPILOT_HOME`. With `COPILOT_HOME` pointing at a folder that has `session-state/`, six `tests.test_scripts.AuditTests` fail on exact stderr (the new Copilot line from `token-audit`). Add `COPILOT_HOME` to that pop list. Then grep every other test that runs `token-audit`, `kaizen-scan` or `kaizen-doctor` as a subprocess (`rg -l "token-audit|kaizen-scan|kaizen-doctor" tests/`) and make the same fix wherever the test builds an env that drops `CODEX_HOME` but not `COPILOT_HOME`. Skip `tests/test_hooks.py`, `tests/test_hook_schedule.py`, `tests/test_regression_notice.py`, `tests/test_usage_guard.py` and `tests/test_schedule_robustness.py`; another packet edits those.
2. **Privacy scan misses `.yaml`.** `tests/test_repo.py` ~line 21: the text-suffix set has `.yml` but not `.yaml`, so `skills/*/agents/openai.yaml` is not scanned. Add `.yaml`.
3. **`kaizen-doctor` cache check too strict.** `scripts/kaizen-doctor` ~line 88: `versions == [version]` warns when an older cache folder sits next to the current one. PASS when `version in versions`; WARN only when the current version is missing. Add or adjust a test in `tests/test_doctor.py` covering "old + current cache → PASS" and "only old → WARN".
4. **`tools/host-probe --worktree` follows symlinks.** ~lines 66-71: file symlinks are followed (`is_file()` + `copy2`), so a link pointing outside the checkout gets copied into the export. Skip entries where `src.is_symlink()`. Add a test in `tests/test_host_probe.py`.
5. **`tools/host-probe` Copilot install after a skipped marketplace add.** ~line 174: when Copilot `marketplace add` is skipped as "needs sign-in" (or fails), `plugin install` still runs and turns a SKIP into a FAIL. Skip the dependent install in that case and report SKIP with the same reason. Add a test with the existing stub pattern.

## Sandbox
Use a writable temp dir: `export TMPDIR="$PWD/out/tmp"; mkdir -p "$TMPDIR"`. If a check fails only because of the sandbox (network, signals, process inspection), record `not run: <reason>`; don't change code to make it pass.

## Verify
```
PYTHONPATH=tests python3 -m unittest tests.test_scripts tests.test_repo tests.test_doctor tests.test_host_probe
COPILOT_HOME="$TMPDIR/cp" sh -c 'mkdir -p "$COPILOT_HOME/session-state" && PYTHONPATH=tests python3 -m unittest tests.test_scripts'
git status --short --untracked-files=all
```
Acceptance: all of the above pass; with `COPILOT_HOME` set as in line 2 the suite still passes; only the files named above (plus tests you found in item 1) change.
