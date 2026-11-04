# 06: `kaizen-project-report` (packet outcomes, calibration, shadow status, slow tests, speed)

## Goal and why
The live audit's sections 9-11 ("Packet outcomes", "Speed KPIs", "Ledger rows due") shell out to a project's own tools and are wired to one project. Replace them with one generic script that builds a Markdown report for one enrolled project from (1) the project's `out/packets.jsonl` through `packet-report`, and (2) optional commands the owner names in global config. The scheduler (packet 09) runs it per enrolled project; the `cycle` skill reads the result.

## Context
- Repo: ~/github/highwayoflife/agent-kaizen. Python 3.9+ stdlib; read `AGENTS.md`. No personal paths or project names in tracked files.
- Depends on packets 02 (`scripts/packet-report`: `--packets FILE --markdown|--json --since --until`, ladder from `calibrationLadder`) and 04 (global keys). Confirm both exist before starting (`ls scripts/packet-report`; `rg -n projectCommands scripts/kaizen-scheduled`).
- Global config is `<claude home>/agent-kaizen.json` (claude home = `$CLAUDE_CONFIG_DIR` or `~/.claude`); read it directly (copy the paths helper from `scripts/token-audit` lines 17-29). Key `projectCommands`: `{ "<abs project path, ~ allowed>": {"outcomeLog": "out/packets.jsonl", "shadowStatus": [argv...], "slowTests": [argv...], "speedReport": [argv...]} }`. Only this global source is honoured; never read commands from the project's files.
- Reference (read-only, for the shape of each section; the originals are New World tools): `~/github/highwayoflife/NewWorld/tools/packet_report.py`, `speed_report.py` (`--markdown`), `test_timing_report.py --over`, `review_batch.py --shadow-status`.

## CLI
```
kaizen-project-report --project DIR [--since YYYY-MM-DD] [--out FILE] [--json]
```
Output Markdown, each section a `## ` heading, at most ~60 lines total:
1. `## Packet outcomes` and `## Calibration proposals`: from `packet-report` (use the sibling script next to this file via `Path(__file__).resolve().parent`, run with `sys.executable`). No log file: print `no outcome log at <relative path>` (not an error).
2. `## Shadow reviews`, `## Slow tests`, `## Speed`: output of `shadowStatus`, `slowTests`, `speedReport` if configured, trimmed to 15 lines each with `… N more lines`. Not configured: omit the section (one line `not configured` only under `--verbose`).
3. `## Project ledger rows pending`: parse `DIR/docs/kaizen/LEDGER.md` (a Markdown pipe table; find the header row by names, case-insensitive, `date` and `measured effect`; rows where the cell equals `pending`; date `YYYY-MM-DD`); list `date change[:60]` and the number of days pending. Missing ledger or column: one line explaining.
Command execution rules: run each configured argv with `subprocess.run(argv, cwd=project, capture_output=True, text=True, timeout=120, shell=False)`; the project must be an existing directory containing `docs/kaizen/` (else exit 2 `not an enrolled project`); `argv[0]` is resolved as given (PATH lookup, or relative to the project when it contains `/`); a non-zero exit, timeout or OSError becomes `unavailable: <reason>` in that section; the environment is passed through unchanged. Exit 0 whenever the report was written.

## Scope / do not touch
Create `scripts/kaizen-project-report` (executable) and `tests/test_project_report.py`. Do not edit other files. No version/CHANGELOG edits. Fixtures go inline in the test or in `tests/fixtures/` (packet 02 owns `tests/fixtures/packets.jsonl`; reuse it read-only).

## Acceptance criteria
1. On a temp project with `docs/kaizen/`, `out/packets.jsonl` (copy of the packet-report fixture) and a global config naming `shadowStatus`/`slowTests`/`speedReport` as small `python3 -c` argv lists, the report has all five sections with the expected lines.
2. A command that exits non-zero, sleeps past a patched short timeout, or does not exist yields `unavailable: ...` and the rest of the report is intact.
3. A project not in `projectCommands` still gets outcomes, calibration and pending-ledger sections.
4. A temp project without `docs/kaizen/` exits 2.
5. A command defined in the project's own `docs/kaizen/config.json` is NOT run (test it).
6. `--json` prints `{"sections":[{"title","lines"}]}`. `--out` writes atomically (temp file + rename).
7. Pending ledger rows parse from a table with extra columns (the owner's ledger has `metric and command` between expected effect and measured effect).
8. Full suite passes.

## Verification
```
cd ~/github/highwayoflife/agent-kaizen
python3 -m unittest tests.test_project_report -v
python3 -m unittest discover -s tests
python3 scripts/kaizen-project-report --help
```

## Working tree
Codex packets run in their own git worktree (`git worktree add ~/github/highwayoflife/agent-kaizen-wt-06 -b kz-06`, created by the orchestrator). Work only there and run the commands from that directory.

## Reporting
Files changed, test counts. Do not commit or push. Stop and report if `packet-report` lacks an option this brief assumes.

## Suggested agent / model / effort
codex-engineer, Terra, medium. Risk: normal (it executes owner-configured commands; reviewers should read the command-execution rules and test 5).
