# FX8: `install --host vscode` registers the plugin in VS Code settings

Risk: normal. Branch `mh-vscode-settings` (from `multi-host`). Do not commit or push.

## Why

When the Copilot CLI is missing, `tools/host-acceptance install --host vscode` only prints UI steps ("run Chat: Install Plugin from Source"). An agent running the acceptance kit cannot do that UI step, so the install fails in practice. VS Code's own install-from-source for a local folder only writes two user settings:

```jsonc
"chat.plugins.enabled": true,
"chat.pluginLocations": { "<absolute plugin folder>": true },
```

Writing those settings by hand was tested on 2026-11-18 with VS Code Insiders on macOS. VS Code picked up the change at once and synced the plugin into `<data dir>/agentPlugins/<id>/<hash>/`, which is the location `vscode_installs()` already detects. The install command should write those settings itself.

## Change (tools/host-acceptance)

1. Factor the data-dir list out of `vscode_installs()` into `vscode_roots()`, which honours `KAIZEN_VSCODE_DATA_DIRS` the same way. `vscode_installs()` then uses it.
2. In `install`, on the existing `manual` path (`--host vscode` with no working `copilot` CLI), after `export_source`:
   - For each root that exists as a directory, edit `<root>/User/settings.json`. Create the file, and the `User` folder, if missing. Skip roots that do not exist.
   - Before changing an existing file, copy it to `settings.json.bak-agent-kaizen-<UTC yyyymmddHHMMSS>` next to it. Write no backup when nothing changes.
   - The file is JSONC: `//` and `/* */` comments, and trailing commas. Use the standard library only. To read values, use a small scanner that is aware of strings, strips comments and trailing commas, then calls `json.loads`. To write, insert text into the original file so that comments, ordering and formatting survive. Never rewrite the file through `json.dumps`.
   - Write JSON strings with `json.dumps(...)` so Windows backslashes are escaped. The plugin path is the absolute exported `source` folder.
   - `chat.plugins.enabled` absent at top level: insert it. Present and `true`: leave it. Present with any other value: do not change it; print one line telling the human to set it to true in that file.
   - `chat.pluginLocations` absent: insert it as an object holding the one path. An object that already maps the path to `true`: leave it. An object without the path: insert `"<path>": true` as its first member, keeping the other entries. An object mapping the path to something else, or a non-object value: do not change it; print one line.
   - Insert new top-level members right after the top-level `{`. Add a comma only when the object already has members. Use 4-space indentation for inserted lines.
   - If the file does not parse as JSONC, or its top level is not an object, leave it untouched and print one line with the manual setting text.
   - Running it twice changes nothing the second time and writes no second backup.
   - Print the changed or unchanged state for each file, with the backup path. Pass paths through `redact()` so home paths print as `~`. Add one line saying that VS Code may ask to trust the folder, because `chat.pluginLocations` is a restricted setting.
   - If no VS Code data dir exists, print the current manual instructions, which stay as the fallback.
   - Keep the existing "VS Code Agents app … Install GitHub Copilot CLI" line in every case. Do not claim the Agents app now works.
3. Add `--print-only` to `install`: on the vscode manual path it skips the settings edit and prints today's instructions.
4. State: keep `'install': 'manual'`, so `check`'s doctor-SKIP logic is unchanged. Add `'vscode_settings': [<settings paths changed or already correct>]`.
5. `cleanup --host vscode`: for each settings path in state, also print how to undo the change: remove that path from `chat.pluginLocations` in the named file, or restore the backup. Do not edit settings in cleanup.

## Tests (tests/test_host_acceptance.py)

Extend or add tests next to `test_vscode_install_without_copilot`, using `KAIZEN_VSCODE_DATA_DIRS` pointed at temp dirs. Test the JSONC helper functions directly where that is simpler, using the `runpy` pattern the file already uses. Cover:

- a settings file with `//` and `/* */` comments, a URL string that contains `//`, and a trailing comma: after install, both keys are set, the comments are kept, a backup exists, and the original content equals the backup;
- a second install: no change, and no new backup;
- an existing `chat.pluginLocations` with another path: both paths present;
- `chat.plugins.enabled: false`: value not changed, and the message is printed;
- an unparseable file: untouched, and the message is printed;
- a missing `User/settings.json` under an existing root: the file is created and parses;
- no existing root: the manual instructions are printed (the existing test's assertions still hold);
- `--print-only`: no settings written.

## Docs

- `docs/testing/host-acceptance.md`: the VS Code chat lines (around 31, 54, 62, 93, 104 and "Troubleshooting VS Code") say `install` now registers the plugin in VS Code user settings (with a backup), then the human runs Developer: Reload Window. Mention `--print-only`. Leave the Agents-app statements as they are.
- `docs/hosts.md`: only if it describes the VS Code chat install steps. Keep the same plain wording.
- Do not bump the version. Do not edit CHANGELOG.md or plan.md.

## Constraints

- Python 3.9+, standard library only. Run `python3`, not `python`.
- No home-directory paths or personal data in tracked files or test fixtures. Use temp dirs.
- Touch only `tools/host-acceptance`, `tests/test_host_acceptance.py`, `docs/testing/host-acceptance.md` and possibly `docs/hosts.md`.

## Verify

```
python3 -m unittest tests.test_host_acceptance
python3 -m unittest discover -s tests
python3 tools/host-acceptance install --help
```
