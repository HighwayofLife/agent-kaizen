# P27 Document friction and assemble release 0.13.0

## Goal

Document friction and assemble release 0.13.0. This packet is part of the Agent Kaizen friction port for 0.13.0.

- **Agent / model / effort** — `codex-dispatch` (`codex-engineer` fallback), terra, medium.
- **Risk** — low. Use green checks.
- **Group / dependencies** — O. After P26.
- **Size target** — ~320 changed lines including focused tests.
- Changelog: Document friction and assemble release 0.13.0.

Owner decisions O1–O2 and evidence for any enabled capability must be resolved before release.

## Context

`CHANGELOG.md:5` and `.claude-plugin/plugin.json` own version. `README.md:156–232`, `scripts/README.md:164–280` and `docs/scheduling.md:91–179,200–230` document commands and permission policy. `docs/hosts.md` arrives in 0.12.0. `tools/ci-local:58–86` checks tracked executable scripts automatically but its JSON allowlist is static. `.github/workflows/ci.yml:43–63` delegates to it.

Wait for the integrated 0.12.0 release, including P03, P06–P09 and C1 if activated. Read `AGENTS.md` and `CLAUDE.md`. Locate symbols with `tools/codemap` if available, otherwise `rg -n` and narrow `sed` ranges. All runtime changes support Python 3.9 and stdlib only. Use `python3`. Keep hard stops, captured user changes, zero-token collection and public-repo privacy; keep real logs and fixtures private.

## Scope and archive references

Owned files: `CHANGELOG.md`, `.claude-plugin/plugin.json`, `README.md`, `scripts/README.md`, `docs/scheduling.md`, `docs/hosts.md`, `tools/ci-local`, `.github/workflows/ci.yml`, `.github/plugin/plugin.json` if present. Coordinate a split if the diff plus tests exceeds 400 changed lines. Changes outside these paths need a separate packet or a revised scope.

Use `git show wt/p10:scripts/README.md` and `git show wt/p10:docs/autonomy.md` as references for vocabulary only. Read the 0.12.0 CI and docs from merged code, and collect packet changelog fragments rather than lifting archived release notes. Inspect archive paths with `git show` and keep the current branch.

## Implementation and acceptance

1. Add `## 0.13.0 (YYYY-MM-DD)` with actual release date and matching plugin version, retain 0.12.0 description/host matrix and synchronize an existing contingent `.github/plugin/plugin.json` if its version is checked. Document installed prefix names, defaults, retention, exact scheduled scope, reversals, opt-outs, migration/reinstall and Codex re-trust after changed hooks. Do not claim unverified host behavior or savings. Add `scripts/friction-catalog.json` to CI's JSON list, confirm tracked new entry points and helpers enter compile/`--help`, and include the sampler in the existing shellcheck glob. Keep the 0.12.0 host-probe stage and PR/tag triggers, updating the workflow's check description if needed. If P28 blocks a conditional capability, re-run P27 on its owned docs, changelog and claims to document the shipped refusal/proposal-only behavior. Hold release until the affected P28 refusal/claim checks pass; a failed unconditional capability requires a fix in its owning packet. This packet assembles metadata for the integration batch. Do not create a tag, push or publish.
2. Verify its failure and compatibility cases with the narrow checks below. Disabled/unavailable inputs must leave existing workflows usable. Keep partial changes private or gated until this packet's checks pass.
3. Confirm that the diff is confined to the owned files and that the integrated Python 3.9 check is green.

## Verification

- `python3 -m unittest discover -s tests -p 'test_repo.py'`
- `python3 -m unittest discover -s tests -p 'test_doctor.py'`
- `python3 -m unittest discover -s tests -p 'test_context_budget.py'`
- `python3 -m json.tool scripts/friction-catalog.json >/dev/null`
- `python3 tools/context_budget.py --root .`
- `claude plugin validate .`
- `tools/ci-local --version-only --tag v0.13.0`
- `tools/ci-local`
- `tools/ci-local --python 3.9`

## Report

Report changed files and line counts, exact checks and outcomes, known uncertainty and any blocked verification. Label measurements with baseline/conditions. Redact paths and identifiers from shared output. Write release metadata in this packet only. Do not commit or push.
