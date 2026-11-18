# fx3: final-audit fixes (multi-host)

Risk: normal. Model: Terra medium. Do not commit or push. Do not touch `.claude-plugin/`, CHANGELOG.md or `docs/plans/` (a parallel packet is releasing 0.12.0). These fix code that has not been released yet, so no changelog line is needed.

The final review of the branch (Astra, `--base 06564ed`) found these. Fix each one and add or adjust a test where noted.

1. **`tools/host-probe` ~line 83: sign-in detection runs before the exit status.** Any Copilot output containing `login` gives `SKIP needs sign-in`, even when the command succeeded. Only treat output as a sign-in prompt when the command's exit code is non-zero. Test in `tests/test_host_probe.py`: a fake `copilot` that exits 0 and prints a path containing `login` must not give a sign-in SKIP.

2. **`tools/host-probe` ~line 69: `--worktree` copy and symlinked parent folders.** `git ls-files --cached` lists index entries, so if a tracked folder on disk has been replaced by a symlink, `source / name` resolves outside the checkout and the file gets copied into the export. Skip any path where the file or any of its parent folders below `source` is a symlink (or whose `os.path.realpath` is not inside `os.path.realpath(source)`). Test: a temp git repo with a tracked `d/f.txt`, then `d` replaced by a symlink to a folder outside the repo; the export must not contain `d/f.txt`.

3. **`tests/test_host_probe.py` ~line 17: the fake Codex stub writes its whole inherited environment to disk.** That can store API keys or CI tokens in a temp file. Record only the keys the tests assert on (for example `HOME`, `CODEX_HOME`, `COPILOT_HOME`, `TMPDIR` and argv). Keep the existing assertions working.

4. **`scripts/kaizen-doctor` ~line 89: a missing or unreadable Copilot manifest gives `PASS`.** When `installed-plugins/<marketplace>/<plugin>/.claude-plugin/plugin.json` is missing or unreadable, emit `WARN 'Copilot: plugin folder found but its manifest is missing or unreadable'` with the existing `copilot plugin install ...` fix, not PASS. Test in `tests/test_doctor.py`: an empty install folder gives that WARN.

5. **README.md: Codex onboarding points at `scan`.** The review says `$agent-kaizen:scan` (the `kaizen-scan` script) ignores Codex sessions, while `audit` (`token-audit`) reports them. Check this first by reading `scripts/kaizen-scan` and `scripts/token-audit`. If it is true, change the Codex sentence in the README "Other hosts" section that ends "Then run `$agent-kaizen:scan`." so it points at `$agent-kaizen:audit` for Codex usage, and fix the Codex row's "Usage measured" cell in the hosts table if it implies scan covers Codex. If it is false, change nothing and say why in your report. Plain, short sentences.

## Verify

```
PYTHONPATH=tests python3 -m unittest tests.test_host_probe tests.test_doctor tests.test_repo
python3 tools/host-probe --help
```
Sandbox note: process and temp-dir tests may fail inside your sandbox; the dispatcher's checks run outside it and are the authority.
