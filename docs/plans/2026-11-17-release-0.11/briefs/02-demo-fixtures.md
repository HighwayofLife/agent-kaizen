# 02: Synthetic transcript generator

## Goal and why

Create public synthetic data for reproducible audits and the installed demo.

## Context

`scripts/token-audit:445,721` scans Claude main and subagent files; `tests/test_usage.py:17-65` shows fixture conventions; `scripts/usage-db:164` reads agent metadata.

## Constraints
Read `AGENTS.md`. Python 3.9 stdlib only; scripts under `scripts/` are executable and answer `--help`. Hooks use macOS bash 3.2, shellcheck, bounded work and exit 0 even on errors; an intentional denial is JSON with exit 0. Do not edit `.github/workflows/ci.yml`. Use `rg -n` and narrow `sed` ranges (no `tools/codemap` exists). Propose a changelog bullet; on each packet landing the integrator bumps the manifest and adds a dated changelog entry before checks, as required by AGENTS.md. Do not edit these shared files in parallel worktrees. Skills require quoted description, matching name, `disable-model-invocation: true`, and README table row. Never commit or push. Stop and report wrong assumptions or if the packet exceeds ~400 changed lines; do not drop criteria.

## Scope / do not touch

Create executable `scripts/kaizen-demo-fixtures` and `tests/test_demo_fixtures.py`. Edit `scripts/kaizen-link` SCRIPTS and `scripts/install-schedule` MANAGED_NAMES to register the generator. Do not modify parser, README or real transcripts.

## Steps

Generator accepts `--output DIR` as a required explicit output directory, creates only its synthetic projects tree and metadata, and uses timestamps relative to current UTC. Include a large-context main session, relay-style Bash-heavy subagent with short output, two calls with an idle gap and large cache rewrite, and an image tool result; use stable fake names and IDs. Give deterministic expected values and no network access. Demo consumers use this same generator in a private temporary directory; this packet registers it.

## Acceptance criteria

1. Running generator against a temporary root then `token-audit --json --project-dir ...` detects known main context, relay tools, cache write and image read. Assert exact timestamps in generated rows, and parser aggregates through `--json`, isolating both Claude and Codex config roots. Gap aggregation assertions belong to packet 03.
2. Repeat generation produces equivalent data apart from time; nothing references real sessions or private paths.
3. `--help` succeeds; only target tree is written.

## Verification

```sh
python3 -m unittest discover -s tests -p 'test_demo_fixtures.py' -v
python3 -m unittest discover -s tests -p 'test_usage.py' -v
python3 -m unittest discover -s tests -p 'test_kaizen_link.py' -v
scripts/kaizen-demo-fixtures --help
```

## Reporting

Report files, results, limitations and baseline/after measurements where applicable. Do not commit or push.

Changelog: Add synthetic audit examples.

## Suggested agent / model / effort and risk

`codex-engineer` / Terra medium. Risk: **normal**.
