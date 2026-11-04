# fix-a: group A batch-review fixes (risk normal, Terra medium)

Repo: agent-kaizen. Range reviewed: 815db91..94e65f4 (kz-01..04). Briefs 01–04 in this directory define the original contracts; read the parts named below. Keep code generic (no personal paths). Do not commit. Do not bump versions.

## Fix
1. **`scripts/kaizen-link` ~l.90:** a copied `kaizen-link` derives the plugin root from its own location (the config dir). It then finds no sources and reports "0 drift" with rc 0. When no `scripts/` or `hooks/` sources exist under the resolved root, exit 2 with a clear message. Add a documented, non-hidden `--plugin-root DIR` option. Test both.
2. **`kaizen-link` ~l.111:** `--unlink` must iterate every managed name even when its plugin source no longer exists. A symlink into the plugin root whose target was removed must still be unlinked. Test it.
3. **`kaizen-link` ~l.139:** refuse to mutate (exit 2) when the resolved `--bin` or `--hooks-dir` destination, or an ancestor, resolves inside the plugin root. Test it.
4. **`kaizen-link`:** `--restore-replaced` without `--unlink` is a parser error.
5. **`scripts/rules-lint` ~l.40:** a settings JSON that is valid but not an object (e.g. `[1]`) must exit 2 with a message, not raise a traceback and exit 1. Around l.59, apply `glob.escape` to the repo and home prefixes before globbing. Test both, including a repo path containing `[`.
6. **`scripts/kaizen-scheduled` `valid_notes_ledger`:** require a non-empty `csv`. **`valid_project_commands`:** project paths must start with `~/` or `/` (reject `~user`). Test both.

## Add the missing tests (acceptance items the review found untested)
- **kaizen-link:**
  - the link-mode default under `--mode auto`;
  - link-mode directory compare (a symlinked `preambles` dir) and `--replace` on a link-mode directory;
  - `--unlink` leaves a regular (non-symlink) file alone;
  - `--json` output shape and the `--check` exit code when drift exists.
- **packet-report:**
  - the `--until` exclusive bound, asserted directly;
  - the `--markdown` renderer;
  - `gpt-6.1-terra` model normalisation;
  - the DOWN guard when an audit fix exists;
  - an unreadable *file* (chmod 000) exits 2.
- **rules-lint:** `docs/kaizen/rules-lint.txt` and `scripts/rules-lint.patterns` are excluded from scanning.

## Verify
`python3 -m unittest discover -s tests`, `git diff --check`, and `./scripts/rules-lint --repo .` (0 hits).
