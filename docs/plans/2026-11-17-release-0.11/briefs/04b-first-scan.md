# 04b: First scan and demo

## Goal and why

Give a real first finding and an offline demo without creating reports or extracts.

## Context

`scripts/token-audit:1336-1410` always writes report/extract today; packet 03 adds cache data. `scripts/kaizen-demo-fixtures` generates a temporary synthetic tree. `README.md:80-95,196` contains install and skill table.

## Constraints
Read `AGENTS.md`. Python 3.9 stdlib only; scripts under `scripts/` are executable and answer `--help`. Hooks use macOS bash 3.2, shellcheck, bounded work and exit 0 even on errors; an intentional denial is JSON with exit 0. Do not edit `.github/workflows/ci.yml`. Use `rg -n` and narrow `sed` ranges (no `tools/codemap` exists). Propose a changelog bullet; on each packet landing the integrator bumps the manifest and adds a dated changelog entry before checks, as required by AGENTS.md. Do not edit these shared files in parallel worktrees. Skills require quoted description, matching name, `disable-model-invocation: true`, and README table row. Never commit or push. Stop and report wrong assumptions or if the packet exceeds ~400 changed lines; do not drop criteria.

## Scope / do not touch

Edit `README.md`, `scripts/kaizen-link` SCRIPTS, and `scripts/install-schedule` MANAGED_NAMES; create executable `scripts/kaizen-scan`, `skills/scan/SKILL.md`, `tests/test_scan.py`. Register the script in both lists. No token-audit, usage-db or scheduler edits.

## Steps

Packet 04a supplies `token-audit --no-write --json`. Scan runs it with no writes against all local projects; demo generates and removes a private temporary fixture and isolates both Claude and Codex roots. Specify a table in script/tests of about ten checks with signal, explicit threshold, source field, and existing fixing skill. Cover context average/peak, cache rewrite share, wakeups, relay agents, images, unused tools, instruction size, inherited models, stuck turns and Bash volume where data exists. Unsupported/insufficient fields emit WARN unavailable, never invented values. Output PASS/WARN/FAIL, named fixing skill, and start pointer. Skill invokes script, without a model audit or enrollment; README starts install then scan.

## Acceptance criteria

1. Real scan and `--demo` yield deterministic, interpretable scorecards; demo exposes all four synthetic findings and routes warnings to valid skills.
2. Snapshot temp home/config before and after scan and assert no created/modified files; demo leaves no persistent artifacts. Missing data/empty input show unknown and a useful next step.
3. The script is registered in both install lists.
4. Measure scan elapsed time on demo and representative local input, without recording private data.

## Verification

```sh
python3 -m unittest discover -s tests -p 'test_scan.py' -v
python3 -m unittest discover -s tests -p 'test_kaizen_link.py' -v
python3 -m unittest discover -s tests -p 'test_repo.py' -v
scripts/kaizen-scan --help
time scripts/kaizen-scan --demo
```

## Reporting

Report files, results, limitations and baseline/after measurements where applicable. Do not commit or push.

Changelog: Add a no-write first scan.

## Suggested agent / model / effort and risk

`codex-engineer` / Terra medium. Risk: **normal**.
