# Shared Context: `speed` skill and `check-profile` script

## Code map (`file:line`)

- `AGENTS.md:1-28`: hard repo rules — `python3` (never `python`), Python 3.9+ stdlib only, no home paths or personal emails/keys in tracked files, scratch output in `out/`, bump `.claude-plugin/plugin.json` and `CHANGELOG.md` when `skills/`, `scripts/` or runtime docs change.
- `.claude-plugin/plugin.json:1-20`: current version is `"0.13.4"` (bump to `"0.14.0"`).
- `CHANGELOG.md:5-16`: `0.13.4` and `0.13.3` entries documenting the macOS `/usr/bin/git` `xcrun` launcher slowdown (170–390 ms per Git call; `42efb34` is the pre-0.13.3 commit).
- `scripts/kaizen-scheduled:83-96,141-142`: `valid_project_commands` already validates `projectCommands.<project>.slowTests` and `projectCommands.<project>.speedReport` as non-empty string argv lists.
- `scripts/kaizen-project-report:21-31,124-129`: iterates `('shadowStatus', 'Shadow reviews')`, `('slowTests', 'Slow tests')`, `('speedReport', 'Speed')` and runs `run_command(commands[key], project)` with a 120s timeout, taking the first 15 stdout lines.
- `scripts/kaizen-link:28-53`: `SCRIPTS` mapping of managed `scripts/` filenames installed into `<Claude config dir>/bin/`.
- `tests/test_kaizen_link.py:146-150`: `test_all_scripts_are_registered` asserts every file in `scripts/` (except `README.md`, `__pycache__`, and dot-files) appears in `SCRIPTS.values()` in `scripts/kaizen-link`.
- `tests/test_repo.py:10-25,44-53,77-100,110-136`:
  - `test_skill_preamble` (lines 44–52): every `skills/*/SKILL.md` must contain `PREAMBLE` (lines 11–15) once, immediately after `# <Title>\n\n`.
  - `test_manifest_names_match` (lines 77–84): `plugin.json` `version` must have a matching `## <version>` heading in `CHANGELOG.md`.
  - `test_skill_frontmatter` (lines 86–92): `name` equals folder name, `description` is double-quoted (`^"[^"]+"$`), `disable-model-invocation: true`.
  - `test_skills_have_codex_visibility_sidecar` (lines 94–100): every `skills/<name>/agents/openai.yaml` must exist and equal `policy:\n  allow_implicit_invocation: false\n`.
  - `test_plugin_root_references_exist` (lines 110–121): every `${CLAUDE_PLUGIN_ROOT}/<ref>` outside `docs/plans/` must exist in the repo.
  - `test_readme_lists_every_skill` (lines 123–127): `README.md` `/agent-kaizen:<name>` references must exactly equal the set of `skills/*/SKILL.md` folders.
  - `test_no_personal_data` (lines 129–136): scans all non-ignored files (including `docs/plans/`) for `/Users/[A-Za-z]`, `/home/[a-z]+/`, personal emails, and API key prefixes.
- `tools/context_budget.py:70-121`: verifies frontmatter and checks that skills with `disable-model-invocation: true` and `agents/openai.yaml` (`allow_implicit_invocation: false`) add 0 visible context bytes.
- `tools/ci-local:64-83`: compiles every script in `scripts/` and runs `<script> --help` on every executable script without `.json`, `.md`, `.patterns`, or `.py` suffix.
- `skills/friction/SKILL.md:1-27` and `skills/test-loop/SKILL.md:1-53`: skill header, preamble, and `docs/autonomy.md` reference patterns to copy.
- `README.md:170-173,245-273,283-300`: Friction section, Skills table, and `What's in the repo` tree.
- `scripts/README.md:682-721`: per-script CLI reference sections.
- `docs/scheduling.md:113-127`: `projectCommands` table row and configuration prose.
- `tests/test_backup_commit.py:26-55`: `BackupCommitTests` runs `git` via PATH in `self.git()`, used for pre-0.13.3 dogfood tracing.

## Discrepancies found in the input

1. **`scripts/kaizen-link` registration required by tests:** `tests/test_kaizen_link.py:146-150` fails if a new file in `scripts/` is not in `SCRIPTS` in `scripts/kaizen-link:28-53`. Packet 01 registers `"check-profile": "check-profile"` in `scripts/kaizen-link`.
2. **`skills/speed/agents/openai.yaml` and `README.md` coupling:** `tests/test_repo.py:94-100` requires `skills/speed/agents/openai.yaml`, and `tests/test_repo.py:123-127` fails if `skills/speed/SKILL.md` exists without `/agent-kaizen:speed` in `README.md` (or vice versa). Packet 02 owns `skills/speed/SKILL.md`, `skills/speed/agents/openai.yaml`, and the `README.md` updates together so `python3 -m unittest tests.test_repo` passes at the end of every packet.
3. **`scripts/kaizen-project-report:25-27` non-zero exit behavior:** `run_command` in `scripts/kaizen-project-report` treats any non-zero exit code from a `projectCommands` command as `unavailable: exit <rc>` and discards `stdout`. To keep `kaizen-project-report` untouched while keeping `check-profile compare` non-zero on regression by default, `check-profile compare` adds `--exit-zero` for `projectCommands.<project>.speedReport`.

## Sanctioned verification commands

- Packet 01: `python3 -m unittest tests.test_check_profile tests.test_kaizen_link tests.test_repo`
- Packet 02: `python3 -m unittest tests.test_repo && python3 tools/context_budget.py --root . && claude plugin validate .`
- Packet 03: `python3 -m unittest tests.test_repo && claude plugin validate .`
- Packet 04 (end-to-end gate): `python3 scripts/check-profile probe --out out/speed`, `python3 scripts/check-profile unittest -s tests --out out/speed`, `python3 -m unittest discover -s tests`
