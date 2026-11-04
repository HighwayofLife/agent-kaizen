# 05a: token-audit section 7 "Codex by kind, model and effort" (kind, median minutes, total hours)

## Goal and why
The owner's old `~/.claude/bin/kaizen-token-audit` has a Codex table by session kind with median minutes and total hours. The plugin's token-audit has only "7. Codex by model". Port the table generically. The plugin's collection code currently discards per-session kind and duration, so `scan_codex` and the collection initialisation change too (review finding).

## Context
- Repo: ~/github/highwayoflife/agent-kaizen. Python 3.9+ stdlib; read `AGENTS.md`. No personal paths or project names in tracked files. `token-audit` must stay zero-token and fast. Tests: `tests/test_usage.py` loads the script with `runpy.run_path(SCRIPTS / 'token-audit')` and builds JSONL fixtures; copy that pattern.
- Plugin code: `scripts/token-audit` `scan_codex` at line ~568 (reads one Codex session file, keeps final `total_token_usage` into `data["codex"][model]`); `collect()` at line ~623 initialises `data` (add the new list there); section 7 is `sections.append(("7. Codex by model", ...))` at line ~1073; `--json` output carries `data`.
- Reference (read-only, older code): `~/.claude/bin/kaizen-token-audit` lines ~205-226 (per-session record `dict(kind, model, effort, tokens, duration_s)`; `duration_s = last - first` row timestamps; kind from prompt text: "VERDICT: APPROVE | REVISE" -> review-plan, "VERDICT: NO ISSUES" -> review-diff, "as the engineering planner" -> planner, "You are working in a git repository. Read AGENTS" (the plugin engineer preamble `scripts/preambles/engineer.md`) -> engineer, else other) and ~430-440 (table `Kind | Model | Effort | Sessions | Median min | Total hours | Tokens`, sorted by tokens, capped at 12 rows plus `… N more kind/model/effort rows omitted; use --json for all details.`).
- Keep the single-pass pattern: collect the user text and first/last timestamps while the file is already being read; do not re-open files. Effort: use the field the scan already reads for the model/effort if any; else `n/a`.
- Keep the existing "7. Codex by model" table; add the new table as a second table inside section 7 or as "7b" without renumbering sections 8 and 9 (choose the least invasive for the 80-line budget; JSON must carry `codex_sessions` rows).

## Scope / do not touch
Edit `scripts/token-audit` (`scan_codex`, the data initialisation in `collect`, section 7 rendering only). Create `tests/test_codex_kinds.py`. No version/CHANGELOG edits. Do not touch `~/.claude`.

## Acceptance criteria
1. Fixture Codex sessions of the five kinds give the new table with correct kind, session counts, median minutes and total hours; `--json` carries per-session rows with kind, model, effort, tokens, duration_s.
2. Existing token-audit tests still pass (the 80-line budget holds).
3. Sessions with a single timestamp give `n/a` duration without crashing.
4. Timing guard: on real data, `time python3 scripts/token-audit --days 7 --out out/ta-new.md` is within 10% of the HEAD version run the same way (commands below). Paste both timings in your report.
5. Full suite passes.

## Verification
```
cd ~/github/highwayoflife/agent-kaizen   # your worktree
python3 -m unittest tests.test_codex_kinds tests.test_usage -v
python3 -m unittest discover -s tests
python3 scripts/token-audit --help
git show HEAD:scripts/token-audit > out/ta-old.py
( time python3 out/ta-old.py --days 7 --out out/ta-old.md ) 2>&1 | tail -4
( time python3 scripts/token-audit --days 7 --out out/ta-new.md ) 2>&1 | tail -4
```

## Working tree
Codex packets run in their own git worktree (`git worktree add ~/github/highwayoflife/agent-kaizen-wt-05a -b kz-05a`, created by the orchestrator). Work only there.

## Reporting
Files changed, test counts, both timings, how `scan_codex` changed. Do not commit or push. Stop and report if per-session duration needs a second pass over the files.

## Suggested agent / model / effort
codex-engineer, Terra, medium. Risk: normal. (Batch reviewer: `tests/test_codex_kinds.py` and the section 7 budget.)
