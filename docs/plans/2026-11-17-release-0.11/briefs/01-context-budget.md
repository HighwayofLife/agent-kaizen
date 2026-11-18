# 01: Context budget release gate

## Goal and why

Enforce the researched always-on model-visible context contract with a reproducible budget.

## Context

Tested on Claude Code 2.1.327: disabled skill descriptions are hidden; the auditor agent description is about 110 tokens. `claude plugin details` overcounts hidden skills. `README.md:196` is true. `docs/what-we-learned.md:37` needs the correction. CI calls `tools/ci-local --skip-tests`.

## Constraints
Read `AGENTS.md`. Python 3.9 stdlib only; scripts under `scripts/` are executable and answer `--help`. Hooks use macOS bash 3.2, shellcheck, bounded work and exit 0 even on errors; an intentional denial is JSON with exit 0. Do not edit `.github/workflows/ci.yml`. Use `rg -n` and narrow `sed` ranges (no `tools/codemap` exists). Propose a changelog bullet; on each packet landing the integrator bumps the manifest and adds a dated changelog entry before checks, as required by AGENTS.md. Do not edit these shared files in parallel worktrees. Skills require quoted description, matching name, `disable-model-invocation: true`, and README table row. Never commit or push. Stop and report wrong assumptions or if the packet exceeds ~400 changed lines; do not drop criteria.

## Scope / do not touch

Edit `tools/ci-local`, `README.md`, `docs/what-we-learned.md`, `scripts/rules-lint.patterns`, `tests/test_rules_lint.py`; create `tools/context_budget.py`, `tools/context-budget.json`, `tests/test_context_budget.py`. Do not edit feature scripts or CI workflow.

## Steps

Count only agent descriptions, descriptions of skills lacking `disable-model-invocation: true`, and maximum literal output for each hook file registered in `hooks/hooks.json`. Store a budget and one reviewed maximum per registered hook file in `tools/context-budget.json`; exclude opt-in hooks. Implement `tools/context_budget.py --root DIR`, reporting UTF-8 bytes and a labelled bytes/4 proxy. Fail on malformed frontmatter, a missing disable flag, missing registered-hook inventory entry, and over-budget total. Integrate the check in `tools/ci-local` outside the `--skip-tests` guard. Record baseline and budget. Keep the true README sentence, add auditor estimate and plugin-details overcount, and record method/version in `docs/what-we-learned.md`. Ensure stale wording patterns do not flag the true sentence; add isolated coverage.

## Acceptance criteria

1. Subprocess fixture trees cover disabled and flagless skills, agents, malformed frontmatter, over budget and registered hook absent from inventory; failures have useful output.
2. `tools/ci-local --skip-tests` executes the check. New or changed registered hook output requires inventory update and check in the same packet.
3. README and learned notes state observed 2.1.327 scope, agent estimate and estimator limitation without claiming exact measured tokens.

## Verification

```sh
python3 -m unittest discover -s tests -p 'test_context_budget.py' -v
python3 -m unittest discover -s tests -p 'test_rules_lint.py' -v
python3 -m unittest discover -s tests -p 'test_repo.py' -v
tools/ci-local --skip-tests
```

## Reporting

Report files, results, limitations and baseline/after measurements where applicable. Do not commit or push.

Changelog: Bound repo-estimated always-on context.

## Suggested agent / model / effort and risk

`codex-engineer` / Terra medium. Risk: **normal**.
