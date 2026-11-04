# 04: new global config keys in `kaizen-scheduled`

## Goal and why
Owner-specific paths and commands must live in user config, not code. Add five global-only keys to the scheduled-settings schema so later packets (project report, notes ledger, rules-lint, link check, calibration) can read them through the existing validation, `config set` and `config show`.

## Context
- Repo: ~/github/highwayoflife/agent-kaizen. Python 3.9+ stdlib; read `AGENTS.md`. No personal paths or project names in tracked files (use `/work/proj` style examples).
- `scripts/kaizen-scheduled`: `SCHEMA` at lines 64-71 (kinds `bool`, `enum`, `int`, `object` with `check`, `paths`), `DEFAULTS`/`CHOICES` 72-73, `valid_value` 117, `effective()` 133 (loops `DEFAULTS`; global-only keys are ignored with a warning in project config), `config set` parsing in `main()` near the end (`elif kind in ("int", "object", "paths")` uses `json.loads`), `show_config` prints JSON. Existing example of an object check: `valid_retention_overrides` (line 47).
- Keys to add (all `global_only: True`):
  - `projectCommands`: object. Keys are absolute project paths (a leading `~` is allowed); each value is an object whose allowed keys are `outcomeLog` (relative path string, no `..`, no leading `/`), and `shadowStatus`, `slowTests`, `speedReport` (each a non-empty list of strings = argv). Default `{}`.
  - `notesLedger`: object with `csv` (string path, `~` allowed), optional `timeline` (string path), optional `measureAfterDays` (int >= 1). Default `{}` (feature off).
  - `calibrationLadder`: list of non-empty strings, each `"model"` or `"model effort"`. Default `["haiku", "sonnet medium", "sonnet high", "opus high"]`.
  - `rulesLintFiles`: list of non-empty strings (globs). Default `[]`.
  - `localScripts`: list of non-empty strings without `/`. Default `[]`.
- Add a new kind `strings` (list of non-empty strings) with an optional per-key `check`; parse it with `json.loads` in `config set` like `object`. Invalid values fall back to the default with the existing warning, and `config set` rejects them with `parser.error`.
- Other packets read these keys by parsing `<claude home>/agent-kaizen.json` directly (no import of this script), so the names and shapes above are a contract; do not rename.

## Scope / do not touch
Edit `scripts/kaizen-scheduled` (schema, validators, `config set` parsing only; do not add new commands; packet 09 owns the rest of this file) and the settings table in `docs/scheduling.md` (add the five rows: scope Global only, value shape, default). Create `tests/test_config_keys.py`. Do not edit `tests/test_schedule.py`. No version/CHANGELOG edits.

## Acceptance criteria
1. `python3 scripts/kaizen-scheduled config show` (with `CLAUDE_CONFIG_DIR` set to a temp dir) lists the five keys with their defaults and source `default`.
2. `config set projectCommands='{"/work/proj":{"shadowStatus":["python3","tools/x.py","--shadow-status"],"outcomeLog":"out/packets.jsonl"}}'` stores it; `config show` echoes it with source `global`.
3. Invalid values are rejected by `config set` (non-list argv, `outcomeLog` containing `..`, `measureAfterDays` 0, a `localScripts` entry with `/`) and ignored with a warning when read from a hand-edited file.
4. Setting any of the five with `--for DIR` fails with "is global-only"; a project `docs/kaizen/config.json` containing one is ignored with the existing warning.
5. Existing keys and tests are unchanged: `python3 -m unittest tests.test_schedule tests.test_housekeep` still pass.
6. `docs/scheduling.md` table lists the five keys.
7. Full suite passes.

## Verification
```
cd ~/github/highwayoflife/agent-kaizen
python3 -m unittest tests.test_config_keys tests.test_schedule tests.test_housekeep -v
python3 -m unittest discover -s tests
CLAUDE_CONFIG_DIR=$(mktemp -d) python3 scripts/kaizen-scheduled config show
```

## Working tree
Codex packets run in their own git worktree (`git worktree add ~/github/highwayoflife/agent-kaizen-wt-04 -b kz-04`, created by the orchestrator). Work only there and run the commands from that directory.

## Reporting
Files changed, test counts. Do not commit or push. Stop and report if `config set` for `object` kinds cannot carry these shapes without a larger refactor.

## Suggested agent / model / effort
codex-engineer, Terra, medium. Risk: normal.
