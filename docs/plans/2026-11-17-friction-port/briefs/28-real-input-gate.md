# P28 Verify the installed 0.13.0 workflows on real input

## Goal

Verify the installed 0.13.0 workflows on real input. This packet is part of the Agent Kaizen friction port for 0.13.0.

- **Agent / model / effort** — `codex-dispatch` (`codex-engineer` fallback), terra, medium.
- **Risk** — normal. Use green checks and the integration batch review.
- **Group / dependencies** — P. After P27.
- **Size target** — ~300 changed lines including the trimmed gate evidence.
- Changelog: No user-facing change. Record installed verification.

Requires signed-in disposable test installs. Scope every live operation to a fixture.

## Context

`tools/ci-local:15–86` runs repository checks. The 0.12.0 `tools/host-probe` will verify installation/discovery. `README.md:61–95` and `docs/scheduling.md:29–79` describe supported installation, and `tests/bench_token_audit.py:55–95` measures scan comparison. Use the assembled 0.13.0 candidate, a signed-in Claude test install and disposable home/config/git worktrees. Use a real Linux or macOS install for any advertised marker capability, and a real Codex install for Codex parsing.

Start from the merged 0.12.0 install tooling and a 0.13.0 release candidate with all prior friction packets. Read `AGENTS.md` and `CLAUDE.md`. Locate symbols with `tools/codemap` if available, otherwise `rg -n` and narrow `sed` ranges. All runtime changes support Python 3.9 and stdlib only. Use `python3`. Keep hard stops, captured user changes, zero-token collection and public-repo privacy; keep real logs and fixtures private.

## Scope and archive references

Owned files: `docs/plans/2026-11-17-friction-port/plan.md`, `docs/plans/2026-11-17-friction-port/gate-results.md`. Coordinate a split if the diff plus tests exceeds 400 changed lines. Changes outside these paths need a separate packet or a revised scope.

Read `git show wt/p10:skills/friction/SKILL.md` for intended workflows. Use existing source tests as rehearsal, then exercise the actual installed commands below. The original checks used pre-0.6.0 runtimes and cannot prove current matching or hook support. Inspect archive paths with `git show` and keep the current branch.

## Implementation and acceptance

1. Prepare real installed disposable 0.13.0 and 0.12.0 executables and isolated config, schedules and real benign inputs. Set `FRICTION_RUN` to private scratch, `FRICTION_BIN` and `FRICTION_BASE_BIN` to the managed bins, `FRICTION_BASE` to the recorded merged 0.12.0 revision, and `FRICTION_PLUGIN` to the candidate checkout/install. Resolve scratch paths through symlinks (for example, `FRICTION_RUN="$(cd "$FRICTION_RUN" && pwd -P)"` on macOS) before creating fixtures. Use documented Claude, Codex and Copilot paths and disposable scheduler `install-schedule --apply`. In each isolated install, run `python3 "$FRICTION_PLUGIN/scripts/kaizen-link" --apply --plugin-root "$FRICTION_PLUGIN"` after testing scheduler dependency installation alone. Verify linked and cached/copied dependencies, then set `FRICTION_PROJECT_REPORTS` from scoped config and `FRICTION_REPORT` to the generated report. Keep branch-specific private state, with fresh evidence per test.
2. Use separate success fixtures, before running the commands below:
   - **Prune**: merged clean linked branch and no ignored/untracked files. Create its old tip (older than 24 h) first. After setup, use `git -C "$FRICTION_LINKED" rev-parse --absolute-git-dir` to locate the real admin directory and age its HEAD, index and logs/HEAD, the linked root, its .git pointer, every checked worktree entry, and the common branch log together (e.g. Python `os.utime(..., follow_symlinks=False)`, at least 25 h old). Run strict preflight and exercise invocation from the target cwd, then apply from the primary. Verify retained branch and recreation.
   - **Allow rule**: create at least ten distinct, explicitly accepted prompt/result pairs for exact `ls` in one enrolled canonical cwd (accept once, do not choose Always Allow). Produce a fresh scoped extract, inspect ten verified acceptances and zero denied/ambiguous for that pair, and keep denied/ambiguous and lookalike cases in a separate fixture. Apply the local rule. Before undoing it, start fresh scheduled propose-only and auto processes and check actual effective Bash behavior in both, including the persisted literal and disallowed outside paths, extra args, quoting, redirects or chains. Compare permission snapshots and approved helpers. An effective widened boundary blocks the grant claim.
   - **Marker**: use a supported regenerable output with a verified open apply-eligible marker action. Use a different action/fixture for `done|dismiss|reopen`; do not mark the marker done before applying. Run apply and undo, verify file/target state. On macOS record O2 proposal-only unless same-target native proof is present.
   - **Commit**: use a separate clean Git project with an open friction gate and working ledger. Run the ordinary interactive opt-in flow below once, then run a separate scheduled review that does ordinary `begin`/Edit/`finish` without `--repo` and requests the reserved run ID-derived candidate. Check run/session/hash handoff, preserved user index/branch, local-only ref, one broker ledger row, and revert by explicit action ID via real `/agent-kaizen:undo`. Exercise the refusal when a real Edit/Write lacks its manifest.
3. Run actual interactive `/agent-kaizen:cycle propose`, review and friction, plus fresh scheduled reviews, assert normal usage refresh on empty/off friction, zero changes in propose-only, one notice across two sessions, and no duplicate effect/row/ack on interrupted retry. Verify the real hook on interactive and `claude -p` successful Bash completion, and observe that failure/timeout remains transcript-only. Use P24a’s installed runtime envelopes to prove version-specific model-write coverage. Unsupported or failed requirements have explicit held/proposal-only status.
4. Time actual installed extraction. Interleave 5+ warmed runs per mode using the identical private transcript/Codex data, scoped cwd, explicit UTC `--since`, pricing data and output protocol. Compare the baseline's default CLI (no friction flag in 0.12.0) to candidate CLI on (default) and off (`--no-friction`). Write real reports and extracts to separate private dirs; time both candidate modes against the baseline and report median/p95, ratios, input sizes and version. Compare legacy summary/scope and verify candidate friction keys present on and absent off. The developer `collect()` benchmark is a secondary check.
5. Record each exit status, PASS/FAIL/blocked, baseline/conditions, and redacted trimmed output. Replace home paths with `~` and omit project/machine identifiers, credentials, raw transcripts, exact paths and raw runtime envelopes before saving `gate-results.md`. Link status in P28’s plan row. If a conditional claim fails, rerun P27’s claims pass on its owned files, then rerun P28 affected checks. Keep publication held until every advertised capability passes.

## Verification

- `python3 -m unittest discover -s tests -p 'test_repo.py'`
- `tools/host-probe --host all --worktree`
- `python3 "$FRICTION_PLUGIN/scripts/install-schedule" --apply --scheduler cron` in the isolated scheduler and config only
- `"$FRICTION_BIN/kaizen-scheduled" audit` and `"$FRICTION_BIN/kaizen-scheduled" auto-audit` in isolated fresh audit state (check global config/thresholds)
- Audit the project together with all linked worktrees by repeating `--cwd` for each linked worktree; the single-`--cwd` examples below apply only when there are no linked worktrees.
- `"$FRICTION_BIN/kaizen-token-audit" --cwd "$FRICTION_PROJECT" --days 1 --out "$FRICTION_PROJECT_REPORTS" --extract-out "$CLAUDE_CONFIG_DIR/audits/extracts"`
- `"$FRICTION_BIN/kaizen-token-audit" --cwd "$FRICTION_PROJECT" --days 1 --no-friction --no-write --json`
- `"$FRICTION_BIN/dispatch-status" --worktree-facts "$FRICTION_PROJECT"`
- `"$FRICTION_BIN/kaizen-host-probe" --project "$FRICTION_PROJECT" --out "$FRICTION_RUN/reports" --json`
- `"$FRICTION_BIN/kaizen-scheduled" actions list --for "$FRICTION_PROJECT" --json`
- `"$FRICTION_BIN/kaizen-scheduled" friction prepare --for "$FRICTION_PROJECT" --report "$FRICTION_REPORT"`
- `"$FRICTION_BIN/kaizen-scheduled" actions import "$FRICTION_BLOCK" --for "$FRICTION_PROJECT" --inputs "$FRICTION_INPUTS"`
- `"$FRICTION_BIN/kaizen-scheduled" friction acknowledge "$FRICTION_INPUTS" --for "$FRICTION_PROJECT"`
- `"$FRICTION_BIN/kaizen-scheduled" actions verify --for "$FRICTION_PROJECT"`
- `"$FRICTION_BIN/kaizen-scheduled" actions dismiss "$FRICTION_ACTION_ID" --for "$FRICTION_PROJECT"`
- `"$FRICTION_BIN/kaizen-scheduled" actions reopen "$FRICTION_ACTION_ID" --for "$FRICTION_PROJECT"`
- `"$FRICTION_BIN/kaizen-scheduled" actions done "$FRICTION_ACTION_ID" --for "$FRICTION_PROJECT"`
- `"$FRICTION_BIN/kaizen-scheduled" actions undo "$FRICTION_APPLIED_ID" --for "$FRICTION_PROJECT"` on a separate verified effect after exercising the skill route
- `"$FRICTION_BIN/kaizen-allow-rule" add --project "$FRICTION_PROJECT" --command ls`
- `"$FRICTION_BIN/kaizen-allow-rule" undo "$FRICTION_ALLOW_RECORD" --project "$FRICTION_PROJECT"`
- `"$FRICTION_BIN/kaizen-host-fix" apply --project "$FRICTION_PROJECT" --catalog-id "$FRICTION_MARKER_ID" --path "$FRICTION_OUTPUT"`
- `"$FRICTION_BIN/kaizen-host-fix" undo "$FRICTION_FIX_RECORD" --project "$FRICTION_PROJECT"`
- `"$FRICTION_BIN/kaizen-worktree-prune" apply --project "$FRICTION_PROJECT" --path "$FRICTION_LINKED"`
- `"$FRICTION_BIN/kaizen-worktree-prune" undo "$FRICTION_PRUNE_RECORD" --project "$FRICTION_PROJECT"`
- `"$FRICTION_BIN/kaizen-backup" begin --repo "$FRICTION_PROJECT" --skill friction --ledger 'Disposable friction gate' "$FRICTION_PROJECT/README.md"`; edit the fixture file, finish with `"$FRICTION_BIN/kaizen-backup" finish "$FRICTION_CHANGE_DIR"`, then `"$FRICTION_BIN/kaizen-backup" commit "$FRICTION_CHANGE_DIR"` and `"$FRICTION_BIN/kaizen-backup" undo "$FRICTION_CHANGE_DIR"`
- `"$FRICTION_BIN/kaizen-scheduled" housekeep --dry-run`
- `"$FRICTION_BIN/kaizen-scheduled" review --dry-run --json --project-dir "$FRICTION_PROJECT"`
- `"$FRICTION_BIN/kaizen-scheduled" review --force --propose-only --project-dir "$FRICTION_PROJECT"`
- `"$FRICTION_BIN/kaizen-scheduled" review --force --project-dir "$FRICTION_PROJECT"` with scheduled auto configured only for the disposable project
- `python3 tests/test_friction_sampler.py --bench`
- Use this extraction timing invocation for baseline, on and off: `/usr/bin/time -p "$FRICTION_TIMED_BIN/kaizen-token-audit" --cwd "$FRICTION_PROJECT" --since "$FRICTION_SINCE" --pricing "$FRICTION_PRICING" --out "$FRICTION_TIMED_OUT" --extract-out "$FRICTION_TIMED_OUT/extracts" "${FRICTION_FLAGS[@]}"`. Use Bash with `FRICTION_FLAGS=()` for baseline/on or `FRICTION_FLAGS=(--no-friction)` for off, switch the bin and private output dir for each mode, and capture stderr timing locally.
- `python3 tests/bench_token_audit.py --baseline "$FRICTION_BASE" --max-ratio 1.10`
- `python3 tools/context_budget.py --root .`
- `tools/ci-local`
- `tools/ci-local --python 3.9`

## Report

Report changed files and line counts, exact checks and outcomes, known uncertainty and any blocked verification. Label measurements with baseline/conditions. Redact paths and identifiers from shared output. Leave plugin version and release CHANGELOG to P27. Do not commit or push.

## Delta: P19 review residuals (host-fix, 2026-11-18)

Live host-fix writes stay off under S3. Before this gate reports host-fix live writes as safe to enable, each item below is either fixed in a fail-closed fix packet or recorded as an accepted residual in the gate report:

1. `scripts/host-fix` undo and rollback unlink the quarantine entry by name after the final identity check; a concurrent sync or restore that replaces that entry loses its file (same-UID race on a random quarantine name).
2. Undo persists `retire-pending` after the last scope check, then renames through the pinned directory FD; a directory moved outside the eligible tree during that write is still mutated (same-UID race).
3. Identity recovery for a moved directory walks unrelated mounts with blocking filesystem calls; an unavailable network mount can hang undo past the 20-second deadline. Exercise undo with the output directory moved and a slow or unreachable mount present, and confirm it refuses within the deadline instead of hanging.
