# P16 Commit and revert only verified backup files on a local kaizen ref

## Goal

Commit and revert only verified backup files on a local kaizen ref. This packet is part of the Agent Kaizen friction port for 0.13.0.

- **Agent / model / effort** — `codex-dispatch` (`codex-engineer` fallback), sol, high.
- **Risk** — high. Get a per-packet verifier and Sol high review before merge. Obtain security review before landing.
- **Group / dependencies** — E. After P08.
- **Size target** — ~365 changed lines including focused tests.
Sol reason: Trusted handoff and Git plumbing must preserve the worktree and user index.
- Changelog: Commit and revert only verified backup files on a local kaizen ref.

## Context

`scripts/kaizen-backup:49–155,157–203,217–247,303–390` has current manifest, after hashes, targets and undo preflight. P08 records an opt-in clean git start. `scripts/kaizen-scheduled:1650–1705` still uses file-only undo in recovery. Scheduled commit access belongs to a later broker.

Use the 0.12.0 integration base for landing. The references above are from 0.11.0 main at d8a4cb7. Read `AGENTS.md` and `CLAUDE.md`. Locate symbols with `tools/codemap` if available, otherwise `rg -n` and narrow `sed` ranges. All runtime changes support Python 3.9 and stdlib only. Use `python3`. Keep hard stops, captured user changes, zero-token collection and public-repo privacy; keep real logs and fixtures private.

## Scope and archive references

Owned files: `scripts/kaizen-backup`, `tests/test_backup_commit.py`, `tests/fixtures/ledger_attestation_v1.json`. Record the changelog line in `docs/plans/2026-11-17-friction-port/changelog/P16.md`. Keep the scoped diff and tests within the assigned cap. Changes outside these paths need a separate packet or a revised scope.

Read `git show wt/p15:scripts/kaizen-backup` at `checked_root`, `tree_from_files`, `write_commit`, `check_run`, `commit`, `checked_revert`, `revert_commit` and the focused tests in `git show wt/p15:tests/test_backup_commit.py`. Keep p15b checks and replace unsafe filters, trust and partial-failure paths. Inspect archive paths with `git show` and keep the current branch.

## Implementation and acceptance

The v1 `ledger_attestation` in the scheduled-baseline JSON is null (no ledger exception) or an exact object: `v` integer 1; `run_id`, `session_id` strings; `ledger_relpath` string exactly `docs/kaizen/LEDGER.md`; `before_b64` base64 of bounded pre-launch bytes; `before_sha256`, `after_sha256` lowercase 64-hex SHA-256 strings; `manifest_ids` array of distinct nonempty strings. Reject duplicate/unknown fields, invalid types, encoding or bounds. P24a derives this from protected runner state, P25 passes it unchanged on fixed private stdin, and P16 rechecks matching IDs, canonical non-symlink scope, unstaged-only status, both hashes against decoded pre-launch and live bytes, unchanged byte prefix, valid appended rows and exact independently verified finished current-run manifests. Reject mismatches; the ledger is excluded from the commit. Hashes alone do not authenticate the source.

1. Build `kaizen-backup commit CHANGE_DIR` preflight and tree/ref primitives. Interactive use requires the P08 opt-in clean baseline. The private scheduled variant receives a v1 JSON runner tuple on stdin in fixed `kaizen-backup commit --scheduled-baseline-stdin CHANGE_DIR` after Claude exits (canonical root and common-dir device and inode, initial HEAD, clean/index stamp, run/session IDs, started-at, pre-launch exclusions and one authorized change-folder ID). Consume it only from fixed runner invocation and keep the verb outside Claude grants. A current-run ordinary `begin`/Edit/`finish` manifest needs no `--repo` stamp. Require it to be new since snapshot, from the exact run/session, verified/finished, unreverted and hash-matching. Recheck HEAD/root/index and account for every live status path using attested run manifests. The sole bookkeeping exception is the project ledger path, with the independently verified ordinary append proof and exact after-hash from P24a; refuse staged or unrelated ledger changes and never put the ledger in the commit. Scheduled mode never accepts fallback to an agent stamp.
The attestation contract is in [Approach and contracts](../plan.md#approach-and-contracts), under Shared mutation quota and trusted Git baseline. Implement that exact v1 wire shape and verification, and create the shared synthetic `tests/fixtures/ledger_attestation_v1.json` with valid and invalid cases. Test valid append, null, malformed fields, wrong run/session, forged prefix or hashes, staged ledger, foreign manifests and changed live bytes. P24a and P25 read this P16-owned fixture.
2. Read only validated bytes into Git plumbing with a private temporary index, bypass clean filters/hooks, refuse unowned or checked-out refs, and use compare-and-swap with a fixed trailer identifying the manifest. Exercise the happy path in isolated plumbing fixtures and refusal of stale/manipulated data. Keep public writes dark until P16b lands ref journal and revert.
3. Obtain security review before landing. Test the scheduled private entry point with a normal begin without `--repo`; cover missing/wrong run and session, pre-launch or changed manifest and forged opt-in stamps. P25 supplies the real runner-to-helper invocation.

## Verification

- `python3 -m unittest discover -s tests -p 'test_backup_commit.py'`
- `python3 -m unittest discover -s tests -p 'test_kaizen_backup.py'`
- `python3 -m unittest discover -s tests -p 'test_schedule_security.py'`
- `python3 scripts/kaizen-backup commit --help`
- `tools/ci-local --python 3.9`

## Report

Report changed files and line counts, exact checks and outcomes, known uncertainty and any blocked verification. Label measurements with baseline/conditions. Redact paths and identifiers from shared output. Leave plugin version and release CHANGELOG to P27. Do not commit or push.

## Delta from the P08 security reviews (2026-11-18)

- The clean-start stamp in any manifest is advisory only and never confers commit authority, interactive or scheduled. Commit authority comes from a live proof at commit time: HEAD and the index are unchanged from the trusted baseline (the runner tuple for scheduled runs; for interactive runs, the human invoking `commit` plus the `begin --repo` record), and the worktree differs from HEAD only by the manifest's files. Each of those files' before-hash must equal its HEAD blob, and its after-hash must equal its live bytes. Any other tracked or untracked difference is refused. This makes a forged or copied stamp harmless.
- Bind the validated manifest's SHA-256 (as returned by P08's handoff) and re-check it before building the commit, so replacing `manifest.json` in place after approval is refused.
- Run Git by the absolute path that P08's capture resolved before launch, never through the inherited `PATH`.
