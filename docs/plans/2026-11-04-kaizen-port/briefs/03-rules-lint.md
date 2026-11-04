# 03: generic `rules-lint` with a built-in stale-wording list

## Goal and why
The owner's `~/.claude/bin/rules-lint` flags stale rule text in instruction files, but its pattern list is hardcoded with owner-specific wording. Port it to the plugin with patterns read from files, so any user can keep a stale list, and so the plugin can ship its own list of superseded wording (rule from 2026-11-04: when a contract changes, add the old wording to rules-lint and its test fixture, and fix every hit).

## Context
- Repo: ~/github/highwayoflife/agent-kaizen (Python 3.9+ stdlib; read `AGENTS.md`; no personal paths or names in tracked files).
- Reference (read-only): `~/.claude/bin/rules-lint` (83 lines) and `~/.claude/bin/tests/test_rules_lint.py` (63 lines). Behaviour to keep: `--repo DIR` (repeatable), `--json`, default repo = cwd when it contains `CLAUDE.md`; text hits as `path:line: pattern: text`; final line `rules-lint: N stale-rule hit(s)`; exit 0 none, 1 hits, 2 usage or IO error; a line containing `rules-lint: allow` is skipped; `DROPPED.md` is skipped; files are read with errors="replace".
- Changes: (a) patterns come from files, one regex per line, `#` starts a comment, blank lines ignored; sources in order: the plugin's built-in `scripts/rules-lint.patterns` (next to the script, resolved via `Path(__file__).resolve()`), `<claude home>/kaizen-rules-lint.txt` (user), and per repo `docs/kaizen/rules-lint.txt`. (b) scanned files: `<claude home>/CLAUDE.md`, `<claude home>/agents/*.md`, plus extra globs from the global setting `rulesLintFiles` in `<claude home>/agent-kaizen.json` (list of strings; `~` expanded; relative ones are relative to the claude home); per repo `CLAUDE.md`, `AGENTS.md`, `docs/agents/*.md`, `.claude/agent-context/*.md`, `.claude/agents/*.md`. Claude home = `$CLAUDE_CONFIG_DIR` or `~/.claude` (copy the paths helper from `scripts/token-audit` lines 17-29). (c) The old script used `$HOME`; use the claude home instead. (d) With no patterns anywhere print `rules-lint: no patterns configured` and exit 0. (e) Invalid regex in a pattern file: report `rules-lint: bad pattern ...` to stderr and exit 2. (f) Do not scan `docs/kaizen/rules-lint.txt` or `scripts/rules-lint.patterns` themselves.
- Built-in list `scripts/rules-lint.patterns` (superseded plugin wording; each with a `#` comment saying what replaced it): `project-repos\.txt` (replaced by enrolment: a project with `docs/kaizen/` is enrolled; 0.7.0). Keep the list short; later packets append their superseded wording only if their contract changes.
- Test fixture dir `tests/fixtures/rules_lint/` must hold sample instruction files and a pattern file so the built-in pattern is exercised by a test that fails if someone removes it.

## Scope / do not touch
Create `scripts/rules-lint` (executable), `scripts/rules-lint.patterns`, `tests/test_rules_lint.py`, `tests/fixtures/rules_lint/*`. Do not edit other files, do not touch `~/.claude`. No version/CHANGELOG edits. Note: the owner's seven patterns (400k/250k, "w/ Sol", etc.) are NOT shipped; packet 12 puts them in the owner's `kaizen-rules-lint.txt`.

## Acceptance criteria
1. `--help` exits 0. Clean tree: exit 0 and `rules-lint: 0 stale-rule hit(s)`.
2. Each pattern source works (built-in, user file, repo file) and a hit line reports file and line number; `rules-lint: allow` skips; `DROPPED.md` skipped; `--json` prints `{"count":N,"hits":[{"path","line","pattern","text"}]}`.
3. A hit for `~/.claude/audits/project-repos.txt` text in a fixture CLAUDE.md is reported from the built-in list.
4. `rulesLintFiles` globs are scanned (temp `CLAUDE_CONFIG_DIR` with `agent-kaizen.json`).
5. No patterns configured: exit 0 with the message; bad regex: exit 2; usage error: exit 2.
6. Tests copy the cases of the old `test_rules_lint.py` (clean, each pattern + allow + DROPPED, text output + global root, usage error), adapted to the file-based patterns. Use `HOME` and `CLAUDE_CONFIG_DIR` pointing into temp dirs.
7. Full suite passes.

## Verification
```
cd ~/github/highwayoflife/agent-kaizen
python3 -m unittest tests.test_rules_lint -v
python3 -m unittest discover -s tests
python3 scripts/rules-lint --help
CLAUDE_CONFIG_DIR=$(mktemp -d) python3 scripts/rules-lint --repo .
```
(The last command lints this repo; it must print 0 hits. If it finds hits in tracked docs, fix wording only in files this packet owns, and report the rest.)

## Working tree
Codex packets run in their own git worktree (`git worktree add ~/github/highwayoflife/agent-kaizen-wt-03 -b kz-03`, created by the orchestrator). Work only there and run the commands from that directory.

## Reporting
Files changed, test counts, any hits in the repo. Do not commit or push.

## Suggested agent / model / effort
codex-engineer, Terra, medium. Risk: normal.
