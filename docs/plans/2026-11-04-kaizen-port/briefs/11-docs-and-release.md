# 11: docs and release 0.7.0

## Goal and why
Document the new tools and ship them as version 0.7.0. The repo rule: any change under `skills/`, `agents/`, `hooks/`, `scripts/`, `templates/` or `.claude-plugin/` bumps `version` in `.claude-plugin/plugin.json` and adds a `## x.y.z (date)` entry to CHANGELOG.md. Earlier packets deliberately did not do this.

## Context
- Repo: ~/github/highwayoflife/agent-kaizen. Read `AGENTS.md`. Writing: plain short sentences, no marketing language; claims and numbers only from `docs/what-we-learned.md` or measured results; no personal paths, emails or project names (tests/test_repo.py checks paths and emails).
- Current version `0.6.0` in `.claude-plugin/plugin.json`; CHANGELOG top entry `## 0.6.0 (2026-10-31)` (see its style: bullets, last bullet "Upgrade notes: ...").
- Facts to document (check each against the merged code with `--help` before writing):
  - `scripts/kaizen-link`: links or copies plugin scripts and hooks into the Claude config dir; `--check` reports drift; `localScripts` marks intended differences; `--apply --replace` renames a differing file to `.replaced-<date>`; copy mode under a plugin cache.
  - `scripts/packet-report` and `docs/outcome-log.md`: outcome log `out/packets.jsonl`, trailers `Risk`, `Fix-Origin`, `Fixes`, calibration rule (n >= 8; UP if first-pass < 70% or fix rate > 30%; DOWN if first-pass >= 95% and no audit fixes), proposals only.
  - `scripts/kaizen-project-report`: sections and the `projectCommands` global config (argv lists, global only, 120 s timeout).
  - `scripts/rules-lint` + `scripts/rules-lint.patterns` + user and project pattern files + `rulesLintFiles`.
  - `scripts/notes-ledger` (`add`, `due`, `set`) and `notesLedger` config; unattended runs only `add`.
  - token-audit section 7 Codex kinds with durations; `codex-review diff --paths`; `dispatch-status` dirty worktrees; `hooks/session-notes.sh` (opt-in, in `templates/settings.example.json`).
  - Scheduled run now writes `checks-*.md` and `project-report-*.md`; `KAIZEN_SKIP_CHECKS=1`; `install-schedule --apply` installs through `kaizen-link`; the project registry file `project-repos.txt` of older private setups is replaced by enrolment (`docs/kaizen/`).
  - Config keys: `projectCommands`, `notesLedger`, `calibrationLadder`, `rulesLintFiles`, `localScripts` (global only).
  - `install-schedule --apply` now prints the link plan and renames only differing `kaizen-` prefixed files (to `.replaced-<date>`); other differing files are reported and left alone; `review --propose-only --force` flags; `audit` now discovers enrolled projects and writes `projects/index.json` itself.
  - Process rules added to skills and templates (Kaizen rule; planning rules A, B, C).

## Steps and files
1. `.claude-plugin/plugin.json`: `"version": "0.7.0"`.
2. `CHANGELOG.md`: new top entry `## 0.7.0 (2026-11-04)` with one bullet per bullet group above and a final `Upgrade notes:` bullet (re-run `install-schedule --apply` to install the new scripts; run `kaizen-link --check`; owners of private copies of these scripts in the config dir should compare with `kaizen-link --check` before replacing them; the `localScripts` setting keeps intended differences quiet).
3. `README.md`: update the loop description (Measure bullet near line 52) to mention project outcomes, rules-lint, drift check and the notes ledger; update the repository-layout line listing `scripts/` (near line 200) to include the new scripts; add a short "Feeding the audit from your project" paragraph linking `docs/outcome-log.md`. Do not add skills (the README skills table is checked against `skills/`).
4. `scripts/README.md`: one short section per new script (purpose, usage line copied from `--help`, one example).
5. `docs/scheduling.md`: in "Reports and storage" add `checks-*.md` and `projects/<key>/project-report-*.md` to the file list and the `reports` retention row; add an "Install through links" paragraph (kaizen-link behaviour, copy mode, drift check). Packet 09 already fixed the `--apply` sentence; do not reintroduce "copies the runner, token-audit".
6. `docs/what-we-learned.md`: add a short section "Keeping tools in one place" with only facts from this work: copies in the config dir and the plugin drifted in both directions; scheduled jobs ran old copies after the plugin moved on; a project-specific audit section needed a project-neutral log contract. No numbers that are not measured.

## Acceptance criteria
1. `.claude-plugin/plugin.json` says 0.7.0 and `CHANGELOG.md` has `## 0.7.0 (2026-11-04)` (tests/test_repo.py `test_manifest_names_match` checks this).
2. Every script named above appears in `scripts/README.md` and in the README layout line.
3. `python3 scripts/rules-lint --repo .` (with `CLAUDE_CONFIG_DIR` set to an empty temp dir) prints 0 hits.
4. Full suite, `claude plugin validate .` and JSON checks pass.

## Verification
```
cd ~/github/highwayoflife/agent-kaizen
python3 -m unittest discover -s tests
claude plugin validate .
for f in .claude-plugin/*.json hooks/hooks.json templates/*.json scripts/pricing.json; do jq empty "$f" || echo BAD $f; done
for s in kaizen-link packet-report kaizen-project-report rules-lint notes-ledger; do python3 scripts/$s --help >/dev/null || echo NOHELP $s; done
CLAUDE_CONFIG_DIR=$(mktemp -d) python3 scripts/rules-lint --repo .
```

## Working tree
Codex packets run in their own git worktree (`git worktree add ~/github/highwayoflife/agent-kaizen-wt-11 -b kz-11`, created by the orchestrator, after packets 05a, 05b, 08, 09 and 10 are merged). Work only there.

## Reporting
Files changed. Do not commit or push. Stop and report if a documented behaviour does not match the code.

## Suggested agent / model / effort
codex-engineer, Terra, medium (orchestrator decision: the docs must be checked against merged code, not just copied). Risk: low. (Docs, version and changelog only.)
