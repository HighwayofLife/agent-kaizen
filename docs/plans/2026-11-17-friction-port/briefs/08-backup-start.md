# P08 Capture opt-in clean Git baselines for local backup commits

## Goal

Capture opt-in clean Git baselines for local backup commits. This packet is part of the Agent Kaizen friction port for 0.13.0.

- **Agent / model / effort** — `codex-dispatch` (`codex-engineer` fallback), sol, high.
- **Risk** — high. Get a per-packet verifier and Sol high review before merge. Obtain security review before landing.
- **Group / dependencies** — B. No friction dependencies.
- **Size target** — ~245 changed lines including focused tests.
- Sol reason: The clean-start capture and identity boundary authorize later Git writes.
- Changelog: Capture opt-in clean Git baselines for local backup commits.

## Context

`scripts/kaizen-backup:49–84,110–203,346–390` validates legacy manifests, paths and hashes. `scripts/kaizen-scheduled:1187–1220,1650–1705` grants only selected backup verbs and owns scheduled rollback.

Use the 0.12.0 integration base for landing. The references above are from 0.11.0 main at d8a4cb7. Read `AGENTS.md` and `CLAUDE.md`. Locate symbols with `tools/codemap` if available, otherwise `rg -n` and narrow `sed` ranges. All runtime changes support Python 3.9 and stdlib only. Use `python3`. Keep hard stops, captured user changes, zero-token collection and public-repo privacy; keep real logs and fixtures private.

## Scope and archive references

Owned files: `scripts/kaizen-backup`, `tests/test_backup_commit.py`. Record the changelog line in `docs/plans/2026-11-17-friction-port/changelog/P08.md`. Keep the scoped diff and tests within the assigned cap. Changes outside these paths need a separate packet or a revised scope.

Read `git show wt/p15:scripts/kaizen-backup` at `git_start`, `git`, `begin` and the matching `git show wt/p15:tests/test_backup_commit.py` cases. Reuse clean-start checks, leaving today's backup validation in place. Inspect archive paths with `git show` and keep the current branch.

## Implementation and acceptance

1. Capture exact canonical top level, common-dir identity, HEAD, strict clean status including untracked and ignored inputs, and index identity/state without optional locks/fsmonitor or sparse/hidden index entries. Expose one shared capture routine (load it through `runpy.run_path`, matching the runner's credentials helper pattern) for P25’s independent pre-launch runner use. Its clean proof must precede Claude and every backup/edit.
2. Keep `kaizen-backup begin --repo DIR` as interactive opt-in, binding the entire run to its original root and HEAD. Conflict, dirty and non-Git still permit ordinary file backup, with no commit authority. No migration of old manifests.
3. Preserve the ordinary `begin --skill … --ledger … FILE` manifest contract. A scheduled backup inherits runner-generated `KAIZEN_RUN_ID` and `KAIZEN_SESSION_ID`; its standard `run_id`, `session_id` and created timestamp persist without `--repo`. Validate those fields and new change-folder identity at the handoff, leaving existing file-only rollback behavior intact. `--run` spoofing or an agent-supplied baseline cannot confer scheduled commit authority. Test ordinary begin/finish with inherited IDs, interactive opt-in, dirty/hidden state and rejected mismatches. P16 validates the trusted tuple delivered independently after the model exits; P25 integrates it.

## Verification

- `python3 -m unittest discover -s tests -p 'test_backup_commit.py'`
- `python3 -m unittest discover -s tests -p 'test_kaizen_backup.py'`
- `python3 scripts/kaizen-backup begin --help`
- `tools/ci-local --python 3.9`

## Report

Report changed files and line counts, exact checks and outcomes, known uncertainty and any blocked verification. Label measurements with baseline/conditions. Redact paths and identifiers from shared output. Leave plugin version and release CHANGELOG to P27. Do not commit or push.
