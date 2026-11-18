# P06 Add a read-only host probe for load, disk, sync and watchers

## Goal

Add a read-only host probe for load, disk, sync and watchers. This packet is part of the Agent Kaizen friction port for 0.13.0.

- **Agent / model / effort** — `codex-dispatch` (`codex-engineer` fallback), terra, medium.
- **Risk** — normal. Use green checks and the integration batch review.
- **Group / dependencies** — C. After P01b, P02.
- **Size target** — ~330 changed lines including focused tests.
- Changelog: Add a read-only host probe for load, disk, sync and watchers.

## Context

`scripts/kaizen-doctor:29–42,95–135` demonstrates bounded local commands and graceful missing tools. `scripts/kaizen-scheduled:158–171,662–746,1231–1245` defines audits, project storage and extract retention. P01 provides the v1 catalogue and P02 provides scoped config.

Use the 0.12.0 integration base for landing. The references above are from 0.11.0 main at d8a4cb7. Read `AGENTS.md` and `CLAUDE.md`. Locate symbols with `tools/codemap` if available, otherwise `rg -n` and narrow `sed` ranges. All runtime changes support Python 3.9 and stdlib only. Use `python3`. Keep hard stops, captured user changes, zero-token collection and public-repo privacy; keep real logs and fixtures private.

## Scope and archive references

Owned files: `scripts/host-probe`, `tests/test_friction_host_probe.py`. Record the changelog line in `docs/plans/2026-11-17-friction-port/changelog/P06.md`. Coordinate a split if the diff plus tests exceeds 400 changed lines. Changes outside these paths need a separate packet or a revised scope.

Read `git show wt/p05:scripts/host-probe` at `Probe.__init__`, `remaining`, `command`, `processes`, `read_proc`, `run`, `main`; use related tests from `git show wt/p05:tests/test_host_probe.py`. Adapt passive disk/sync/process/inotify checks and output to today's layout. Inspect archive paths with `git show` and keep the current branch.

## Implementation and acceptance

1. Implement `host-probe --project DIR --out DIR [--json]` with one bounded report under the supplied machine-local audit directory, private atomic create named `host-probe-<UTC-unique-stem>.json`, exit 0 on partial availability and nonzero on failed output. Expose v1 fields `project`, `generated_at`, `facts`, `findings` (catalogue ID, stable subject, bounded numeric evidence), `regenerable_dirs` and `worktrees` (empty until P10), and warning categories. Resolve the catalogue using the runner’s `sibling()` convention (`kaizen-friction-catalog.json` first, then `friction-catalog.json`), including from a copied install. P00 owns registration. Cap input/output and subprocesses (5 seconds per command, 30 total, bounded bytes/items); terminate a timed-out process group where supported. Process basenames only from catalogue, no process argv or env. Mark unavailable information explicitly and Windows indexer/AV presence as informational. Verify symlink/output refusal, bounded partial results, unavailable tool/OS and a benign POSIX/Windows fixture. Name the runtime probe's tests `tests/test_friction_host_probe.py`; `tests/test_host_probe.py` belongs to 0.12.0's installer probe.
2. Verify its failure and compatibility cases with the narrow checks below. Disabled/unavailable inputs must leave existing workflows usable. Keep partial changes private or gated until this packet's checks pass.
3. Confirm that the diff is confined to the owned files and that the integrated Python 3.9 check is green.

## Verification

- `python3 -m unittest discover -s tests -p 'test_friction_host_probe.py'`
- `python3 scripts/host-probe --help`
- `python3 -m unittest discover -s tests -p 'test_host_probe.py'`
- `python3 -m unittest discover -s tests -p 'test_kaizen_link.py'`
- `tools/ci-local --python 3.9`

## Report

Report changed files and line counts, exact checks and outcomes, known uncertainty and any blocked verification. Label measurements with baseline/conditions. Redact paths and identifiers from shared output. Leave plugin version and release CHANGELOG to P27. Do not commit or push.
