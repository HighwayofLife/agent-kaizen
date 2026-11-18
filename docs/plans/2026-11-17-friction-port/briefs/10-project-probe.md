# P10 Measure worktree sprawl and identify regenerable outputs

## Goal

Measure worktree sprawl and identify regenerable outputs. This packet is part of the Agent Kaizen friction port for 0.13.0.

- **Agent / model / effort** — `codex-dispatch` (`codex-engineer` fallback), terra, medium.
- **Risk** — normal. Use green checks and the integration batch review.
- **Group / dependencies** — D. After P04, P06.
- **Size target** — ~340 changed lines including focused tests.
- Changelog: Measure worktree sprawl and identify regenerable outputs.

## Context

`scripts/dispatch-status:11–58` separates dirty reporting. P04's `kaizen_worktree_facts.py` adds strict, read-only facts. P06 shipped `host-probe` and a bounded v1 output. `scripts/kaizen-scheduled:70–76,119–147` defines config syntax and scope.

Use the 0.12.0 integration base for landing. The references above are from 0.11.0 main at d8a4cb7. Read `AGENTS.md` and `CLAUDE.md`. Locate symbols with `tools/codemap` if available, otherwise `rg -n` and narrow `sed` ranges. All runtime changes support Python 3.9 and stdlib only. Use `python3`. Keep hard stops, captured user changes, zero-token collection and public-repo privacy; keep real logs and fixtures private.

## Scope and archive references

Owned files: `scripts/host-probe`, `tests/test_friction_host_probe.py`. Record the changelog line in `docs/plans/2026-11-17-friction-port/changelog/P10.md`. Coordinate a split if the diff plus tests exceeds 400 changed lines. Changes outside these paths need a separate packet or a revised scope.

Read `git show wt/p05:scripts/host-probe` at `worktrees`, `size`, `directories`, `output_dir_problem` and relevant `run` sections. Pull gitignore, nested tree and bounded traversal cases from `git show wt/p05:tests/test_host_probe.py`. Inspect archive paths with `git show` and keep the current branch.

## Implementation and acceptance

1. Populate sprawl, stale linked worktrees, regenerable directory sizes, and indexed-output findings based on catalogue and evidence. Use scoped Git ignore checks and catalogue/explicit project names; never label a worktree itself as regenerable or walk symlinks. Refuse sensitive roots, tracked descendants, nested repositories and ambiguous scope from the automatic candidate list. Bound enumeration, memory and bytes under the same deadline and report partial facts as unknown. Retain P06’s copied-install name resolution and `host-probe-*.json` retention pattern. Maintain stable findings and absolute canonical local subjects only inside private output. Test tracked/ignored/symlink/nested cases plus unavailable Git and worktree identities. Probe results are advisory and grant no mutation.
2. Verify its failure and compatibility cases with the narrow checks below. Disabled/unavailable inputs must leave existing workflows usable. Keep partial changes private or gated until this packet's checks pass.
3. Confirm that the diff is confined to the owned files and that the integrated Python 3.9 check is green.

## Verification

- `python3 -m unittest discover -s tests -p 'test_friction_host_probe.py'`
- `python3 -m unittest discover -s tests -p 'test_dispatch_status.py'`
- `python3 scripts/host-probe --help`
- `python3 -m unittest discover -s tests -p 'test_host_probe.py'`
- `tools/ci-local --python 3.9`

## Report

Report changed files and line counts, exact checks and outcomes, known uncertainty and any blocked verification. Label measurements with baseline/conditions. Redact paths and identifiers from shared output. Leave plugin version and release CHANGELOG to P27. Do not commit or push.
