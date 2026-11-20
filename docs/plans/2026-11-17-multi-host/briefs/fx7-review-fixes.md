# FX7: batch review fixes for FX5, FX6 and 639b7cc

Agent: Terra, effort medium. Risk: normal. Do not commit or push. Context: briefs fx5-vscode-agents-app.md and fx6-copilot-live-plugins.md in this folder.

## Fixes (each stated exactly)

1. `tools/host-acceptance` (~line 74) and `scripts/kaizen-doctor` (~line 46), in each `copilot_plugin` resolver: add `RuntimeError` to the except tuple. `Path("~gone/mp").expanduser()` raises RuntimeError for an unknown user, and a bad settings.json must never crash. Do the same for the `Path(os.environ.get('COPILOT_HOME') ...).expanduser()` calls (`check` ~line 197, kaizen-doctor ~line 92): on RuntimeError, fall back to the unexpanded path. Add a test in each test file: settings.json with `"path": "~nosuchuser-xyz/mp"` gives no crash and no install found.
2. `install` (~lines 158-162): before the uninstall/marketplace-remove step, delete the state file (`statefile.unlink(missing_ok=True)`), so a failed reinstall does not leave a stale `installed_at`.
3. Test the command order in the existing install test (the fake CLI logs to `$HOME/commands`): copilot is `plugin uninstall agent-kaizen@agent-kaizen-tools`, then `plugin marketplace remove agent-kaizen-tools`, then `plugin marketplace add ...`, then `plugin install agent-kaizen@agent-kaizen-tools`. Codex uses `plugin remove` and `plugin add`. Also test that a failing `marketplace add` leaves no state file.
4. hooks-live hint (~line 284): test that `check --host copilot-cli` with no state file gives a `hooks-live:sessionStart` detail starting with `install has not completed`. Append the VS Code chat-only suffix only when `state.get('installed_at')` is set.
5. VS Code copilot shim: VS Code ships `bin/copilot-shim/copilot`. Until the real CLI is installed it only prints "GitHub Copilot CLI was not found". So `shutil.which('copilot')` is not enough. For `install`, treat the CLI as missing when `copilot --version` exits non-zero or its output contains `not found` (case-insensitive). `--host vscode` then prints the manual steps, and `--host copilot-cli` prints the missing-CLI error. Test with a fake `copilot` that prints that text and exits 1.
6. `redact` (~line 208): match HOME case-insensitively, and also redact `[A-Za-z]:\\Users\\<name>` (backslash form) to `~`. Add a unit test.
7. `scripts/kaizen-doctor` (~line 118): when the Copilot install is live and the version mismatches or the manifest is unreadable, the fix hint is `update the local marketplace directory (see docs/hosts.md)`, not `copilot plugin install ...`. Cover it in tests/test_doctor.py.
8. `docs/testing/host-acceptance.md`: where it says removing an existing `agent-kaizen-tools` marketplace first is expected, add that it also uninstalls the plugin first. Move the "Local-directory marketplace installs are live" sentence under Troubleshooting. Also document that Copilot hides user-only skills from the model, and that headless `copilot -p` does not run slash commands. So `/agent-kaizen:scan --demo` must be typed in an interactive session (`/scan` without the prefix is unknown).
9. Add one test for `KAIZEN_VSCODE_DATA_DIRS` with two data dirs: the most recently modified agentPlugins install wins.

`scripts/kaizen-doctor` changes, so extend the existing FX6 bullet in the unreleased `## 0.12.0` CHANGELOG entry. No version bump.

## Scope

Allowed files: `tools/host-acceptance`, `scripts/kaizen-doctor`, `tests/test_host_acceptance.py`, `tests/test_doctor.py`, `docs/testing/host-acceptance.md`, `CHANGELOG.md`. Tests use temp dirs only. No home-directory paths in tracked files.

## Verify

```
PYTHONPATH=tests python3 -m unittest tests.test_host_acceptance tests.test_repo tests.test_host_probe tests.test_doctor
python3 tools/host-acceptance --help && python3 scripts/kaizen-doctor --help
```
