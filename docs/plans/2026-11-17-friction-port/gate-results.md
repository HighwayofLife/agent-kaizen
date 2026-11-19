# P28 real-input gate results (agent-runnable part)

Candidate 0.13.0 (`release-0.13`, HEAD b2bb1ff), baseline 0.12.0 (tag `v0.12.0`, 2e0e643). Run 2026-11-18 on macOS arm64 (Darwin), Python 3.12.8 (3.9.6 for the 3.9 pass), Claude Code 2.1.x on PATH but never invoked with tokens, Codex CLI 0.170.0, Copilot CLI present.

**Overall: publication stays held.** The agent-runnable checks pass except one (row 42), and every step that needs a person, a signed-in `claude` or the real scheduler is BLOCKED (needs owner). Counts over 48 rows: 39 PASS, 1 FAIL, 8 BLOCKED.

## Conditions

- Delta `28-real-input-gate-delta.md` applied: everything ran inside a private scratch directory (`<scratch>`); `HOME`, `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, `XDG_CONFIG_HOME`, `GIT_CONFIG_GLOBAL`, `KAIZEN_BACKUP_DIR` and `KAIZEN_USAGE_DB` pointed into it. No real config, audit, crontab or launchd was read or written, and no credentials were copied.
- Scripts ran from isolated bins installed with `kaizen-link` (`<scratch>/bin-c` candidate, `<scratch>/bin-b` baseline), not through `install-schedule --apply` (row 3).
- Baseline was a detached worktree of `v0.12.0` inside scratch and was removed with `git worktree remove --force` at the end.
- Fixture git projects only, all inside scratch: a friction project with 9 linked worktrees and an ignored `target/` (flow), a prune project, a marker project, a commit project and synthetic Claude transcripts (400 turns for functional checks, 15000 turns for timing). The checkout itself was never a target.
- The machine was shared and busy (load average 5 to 10) during timing and the test runs. Scratch paths were symlink-resolved before use (observation 1).

## Checks

| # | Command | Result | Conditions | Trimmed output |
|---|---|---|---|---|
| S1 | `git worktree add --detach <scratch>/base v0.12.0` | **PASS** | tag v0.12.0 = 2e0e643 | HEAD is now at 2e0e643 |
| S2 | `kaizen-link --apply --plugin-root <candidate> --bin <scratch>/bin-c` (and baseline into `<scratch>/bin-b`), then `--check` | **PASS** | link mode, isolated config | `kaizen-link: 0 drift, 0 broken, 0 local`; candidate bin has the 0.13.0 scripts (allow-rule, host-fix, worktree-prune, host-probe, friction helpers); baseline bin has none of them |
| S3 | `kaizen-link --apply --mode copy ... --bin <scratch>/bin-copy`, `--check`, `--help` on 4 copied tools | **PASS** | copied dependencies | 0 drift; all 4 copied tools exit 0 |
| 1 | `python3 -m unittest discover -s tests -p test_repo.py` | **PASS** | Python 3.12.8 | Ran 12 tests, OK |
| 2 | `tools/host-probe --host all --worktree` | **PASS** | Codex CLI 0.170.0, Copilot CLI; isolated temp homes | codex: plugin add, installed version 0.13.0, skills hidden 0, 4 hooks (postToolUse, sessionStart x2, userPromptSubmit); copilot: install ok, 23 skills; exit 0 |
| 3 | `install-schedule --apply --scheduler cron` | **BLOCKED (needs owner)** | no documented way to point `install-schedule` at an alternate crontab file or launchd dir (source calls `crontab -`; launchd path is `$HOME/Library/LaunchAgents` plus `launchctl`) | Not run: would touch the real scheduler (delta rule 2) |
| 4 | `install-schedule --scheduler cron --review` (preview, no `--apply`), `PATH=<scratch>/empty` (stub `claude`, no `crontab`) | **PASS** | preview only; isolated so no crontab is read or written | audit job (`0 9 */3 * *`) and review job (`0 9 * * 1`) rendered with isolated `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, `KAIZEN_BACKUP_DIR`, `KAIZEN_USAGE_DB`; exit 2 with "crontab not found; schedule these jobs by hand" (expected without crontab) |
| 5 | `kaizen-scheduled audit` | **PASS** | isolated config, fixture transcripts | exit 0, `audit: ok <scratch>/claude/audits/token-audit-*.md`; step "kaizen-link: failed (plugin root unknown; set CLAUDE_PLUGIN_ROOT or re-run install-schedule --apply)" when `CLAUDE_PLUGIN_ROOT` is unset; with it set the step does not fail |
| 6 | `kaizen-scheduled auto-audit` | **PASS** | audit just ran, so not due | exit 0, no output |
| 7 | `kaizen-token-audit --cwd <proj> --days 1 --out <reports> --extract-out <config>/audits/extracts` | **PASS** | real (symlink-resolved) paths; fixture with 400 synthetic turns | exit 0; report and `.extract.json` written; "Claude: 400 calls". See observation 1 for the same command through a symlinked path |
| 8 | `kaizen-token-audit --cwd <proj> --days 1 --no-friction --no-write --json` | **PASS** | same fixture | exit 0; no `friction` key (see timing check for key presence on and absence off) |
| 9 | `dispatch-status --worktree-facts <proj>` | **PASS** | fixture project | exit 0; "WORKTREE FACTS (advisory)" with branch, tip, primary=true. Output not saved (see observation 4) |
| 10 | `kaizen-host-probe --project <proj> --out <reports> --json` | **PASS** | fixture project, 9 linked worktrees | exit 0; finding `sprawl` / `worktree-prune` with `prunable_worktrees: 9`; paths redacted to `[project]` in the stdout JSON |
| 11 | `kaizen-scheduled actions list --for <proj> --json` | **PASS** | before and after import | exit 0; `[]` before; one `worktree-prune` row, status `open`, after import |
| 12 | `kaizen-scheduled friction prepare --for <proj> --report <report>` | **PASS** | audit run with `--cwd` for the project and each linked worktree, then fresh host probe in the project reports dir | exit 0; prints `friction-inputs-*.json` with 2 slow-call flags and 1 action. Single-`--cwd` audit on a project with linked worktrees: exit 2 "preparation refused" (observation 2) |
| 13 | `kaizen-scheduled actions import <block> --for <proj> --inputs <inputs>` | **PASS** | block = one `suggest` for the prepared action ID | exit 0; one broker/action row |
| 14 | `kaizen-scheduled friction acknowledge <inputs> --for <proj>` | **PASS** | after import | exit 0 |
| 15 | `kaizen-scheduled actions verify --for <proj>` | **PASS** | manual-verify catalogue entry | exit 0; `<id> unavailable` (expected for a manual verification kind) |
| 16 | `kaizen-scheduled actions dismiss <id> --for <proj>` | **PASS** | - | exit 0; status `dismissed` |
| 17 | `kaizen-scheduled actions reopen <id> --for <proj>` | **PASS** | - | exit 0; status `open` |
| 18 | `kaizen-scheduled actions done <id> --for <proj>` | **PASS** | not the marker action | exit 0; status `done`, `done_by: user` |
| 19 | retry of the same `actions import` and `friction acknowledge` (interrupted-retry proxy) | **PASS** | after acknowledgement | both exit 2 "reconciliation refused"; action rows stay at 1; no duplicate row or acknowledgement |
| 20 | `kaizen-scheduled actions undo <id> --for <proj>` on an action with no applied effect | **PASS** | negative test | exit 2 "no verified broker effect in this project" |
| 21 | `kaizen-scheduled actions undo <applied-id>` on a verified effect | **BLOCKED (needs owner)** | no verified effect can exist: live broker/host writes are disabled (S3) and the apply path needs a signed-in `claude` | Not run |
| 22 | `kaizen-allow-rule add --project <proj> --command ls` without evidence | **PASS** | negative test | exit 2 "run a fresh scoped audit with a bounded evidence window"; no settings file written |
| 23 | `kaizen-allow-rule undo bogus --project <proj>` | **PASS** | negative test | exit 2 "settings writes are disabled pending live Claude proof" |
| 24 | Allow rule happy path: 10 accepted prompt/result pairs, scoped extract, apply, fresh scheduled propose-only and auto checks of effective Bash behaviour, undo | **BLOCKED (needs owner)** | needs a person to accept 10 prompts and a signed-in `claude`; settings writes are disabled | Not run. Grant claim stays unproven |
| 25 | `kaizen-host-fix apply --catalog-id {linux-localsearch,spotlight-output,timemachine-output} --path <marker-fixture>/target` | **PASS** | macOS arm64, git fixture with ignored `target/` | all exit 2: "unknown marker or wrong platform" (x2), "Time Machine requires a manual catalogue step because same-target exclusion is unverified"; target dir unchanged (no `.nomedia`, no marker) |
| 26 | `kaizen-host-fix undo bogus --project <proj>` (also with the output dir moved away) | **PASS** | P19 residual 3 probe | exit 2 "marker writes are disabled pending Linux compatibility checks" in 0.07 s, so no hang; the live undo path is not reachable, so residual 3 itself is not exercised |
| 27 | Marker apply, undo and `done\|dismiss\|reopen` on a different action | **BLOCKED (needs owner)** | needs a Linux host with a supported marker (O2: macOS is proposal-only); marker writes are disabled (S3). `done\|dismiss\|reopen` ran on a separate action (rows 16-18) | Not run |
| 28 | `kaizen-worktree-prune apply --project <primary> --path <linked>` run from the primary | **PASS** | fixture: linked worktree on a merged branch, tip 4 days old, worktree root, entries, `.git` pointer, admin `HEAD`/`index`/`logs/HEAD` and common branch log aged 30 h | exit 2 "eligible worktree. worktree changes are disabled pending safe removal and authenticated recovery"; worktree and branch still present |
| 29 | same command run from inside the target worktree | **PASS** | negative test | exit 2 "target contains the current directory" |
| 30 | `kaizen-worktree-prune undo bogus --project <proj>` | **PASS** | negative test | exit 2 "record is outside the private journal" |
| 31 | Prune removal, retained branch, recreation | **BLOCKED (needs owner)** | worktree removal is disabled (S3); delta rule 6 requires the refusal, which rows 28-30 verify | Not run |
| 32 | `kaizen-backup begin --repo <proj> --skill friction --ledger ... README.md`, edit, `finish`, `commit`, `undo` | **PASS** | clean fixture git project on `main` | begin/finish/commit/undo all exit 0; commit on local-only `refs/kaizen/<date>`; `HEAD` and branch unchanged; user change stays in the working tree until undo; undo restored the file |
| 33 | `kaizen-backup begin` on a credential-style path (empty file in the isolated config dir) | **PASS** | negative test | exit 2 "refusing to back up credential path" |
| 34 | Commit flow: interactive opt-in, scheduled review doing `begin`/Edit/`finish` with the run-ID candidate, one broker row, revert through real `/agent-kaizen:undo`, refusal when a real Edit/Write lacks its manifest | **BLOCKED (needs owner)** | needs a signed-in `claude` and real Edit/Write hooks | Not run |
| 35 | `kaizen-scheduled housekeep --dry-run` | **PASS** | isolated audits dir | exit 0, nothing to delete |
| 36 | `kaizen-scheduled review --dry-run --json --project-dir <proj>` | **PASS** | isolated config | exit 0; `[{"path": "<proj>", "scheduledAutonomy": "propose", "source": "default"}]` |
| 37 | `kaizen-scheduled review --force --propose-only` and `review --force` with scheduled auto for the fixture | **BLOCKED (needs owner)** | spends tokens through a signed-in `claude`; the isolated config has no login and credentials are not copied | Not run |
| 38 | Interactive `/agent-kaizen:cycle propose\|review\|friction`; real hook on interactive and `claude -p` Bash completion; usage refresh on empty/off friction; one notice across two sessions; P24a/S7 model-write envelopes | **BLOCKED (needs owner)** | needs a person and a signed-in `claude` with real tokens | Not run |
| 39 | Extraction timing, baseline vs candidate on vs candidate `--no-friction` | **PASS** | see timing table | on/baseline 0.77, off/baseline 0.63 (median); legacy keys identical; `friction` present on, absent off and in baseline |
| 40 | `python3 tests/bench_token_audit.py --baseline 2e0e643 --max-ratio 1.10` | **PASS** | synthetic data, `collect()` only; run twice | default: ratio 0.992x and 0.994x |
| 41 | `python3 tests/bench_token_audit.py --baseline 2e0e643 --max-ratio 1.10 --no-friction` | **PASS** | as above | off: ratio 0.822x |
| 42 | `python3 tests/test_friction_sampler.py --bench` | **FAIL** | Python 3.12.8 | exit 0 with no output in 0.1 s: the script has no `__main__` and no `--bench` handling, so it produces no benchmark. `python3 -m unittest discover -s tests -p test_friction_sampler.py`: 24 tests, OK. The same flag appears in the P14c and P14d briefs |
| 43 | `python3 tools/context_budget.py --root .` | **PASS** | - | exit 0; "Total: 1023 UTF-8 bytes ... budget: 1024 bytes" (1 byte of headroom) |
| 44 | `tools/ci-local` | **PASS** | Python 3.12.8, clean signal handling, env without `KAIZEN_*` | run 3 of 3: unit tests 1538, OK (3 skipped), 1756 s; context budget, shellcheck, JSON, compile, script help, plugin validation, host probe, version/changelog all PASS. Runs 1-2 are in the observations (900 s harness cap; 3 harness-caused errors) |
| 45 | `tools/ci-local --python 3.9` | **PASS** | uv, CPython 3.9.6 | unit tests 1538, OK (3 skipped), 2141 s; all other stages PASS |

## Extraction timing (row 39)

Command per run (identical across modes): `/usr/bin/time -p <bin>/kaizen-token-audit --cwd <proj> --since 2026-11-18 --pricing <candidate>/scripts/pricing.json --out <out> --extract-out <out>/extracts [--no-friction]`. One warm-up run per mode, then 9 interleaved runs per mode with the order rotated each round; fresh output dir per run. Input: one synthetic Claude transcript, 45000 rows, 54.8 MB, 15000 Bash tool calls (one in ten is a slow call), no Codex data. `time -p` resolution is 0.01 s. p95 is nearest-rank over 9 runs (equals the slowest run).

| Mode | Version | Runs | Median (s) | p95 (s) | Ratio to baseline (median) | Ratio (p95) |
|---|---|---|---|---|---|---|
| baseline default CLI | 0.12.0 (2e0e643) | 9 | 1.20 | 1.57 | 1.00 | 1.00 |
| candidate on (default) | 0.13.0 | 9 | 0.92 | 1.25 | 0.77 | 0.80 |
| candidate `--no-friction` | 0.13.0 | 9 | 0.76 | 1.03 | 0.63 | 0.66 |

Raw runs (s): baseline 1.18 1.19 1.19 1.19 1.20 1.21 1.23 1.25 1.57; on 0.90 0.90 0.91 0.92 0.92 0.93 0.94 0.95 1.25; off 0.75 0.76 0.76 0.76 0.76 0.76 0.78 0.93 1.03.

A smaller first pass (3000 turns, 10.9 MB, same protocol, 9 runs) gave medians baseline 0.30, on 0.31, off 0.22 (ratios 1.03 and 0.73), at the 0.01 s resolution limit.

Output comparison on the 15000-turn input (`--json --no-write`): every legacy key (headline, sessions, models, tool counts, scope, and the rest) is identical between baseline, candidate on and candidate off; the `friction` key is present only for candidate on (473 samples, 2 slow-call signatures) and absent for candidate off and baseline. Candidate extraction is faster than baseline here; the cause was not investigated.

Developer benchmark `tests/bench_token_audit.py` (collect() only, synthetic data, 45 interleaved repeats, median): default 0.992x and 0.994x; `--no-friction` 0.822x; threshold 1.10.

## Accepted residuals for 0.13.0 (P19 host-fix, still open)

Live host-fix writes and worktree removal stay disabled (S3); rows 25-31 show the code refuses them. These three P19 review residuals are recorded as accepted residuals for 0.13.0 and remain open; live host-fix writes must not be reported as safe to enable until they are fixed:

1. `scripts/host-fix` undo and rollback unlink the quarantine entry by name after the final identity check; a concurrent sync or restore that replaces that entry loses its file (same-UID race on a random quarantine name).
2. Undo persists `retire-pending` after the last scope check, then renames through the pinned directory FD; a directory moved outside the eligible tree during that write is still mutated (same-UID race).
3. Identity recovery for a moved directory walks unrelated mounts with blocking filesystem calls; an unavailable network mount can hang undo past the 20-second deadline. Not exercised: undo is refused before that code runs (row 26), and no slow or unreachable mount was available in the isolated run.

## Observations

1. `token-audit` refuses to write the extract when any component of `--extract-out` (or the default `<config>/audits/extracts`) is a symlink. On macOS the temp dir is under `/var`, a symlink to `/private/var`, so the candidate printed `token-audit: extract not written ([Errno 20] Not a directory: ...)`, exited 0 and wrote only the report; the baseline wrote the extract. Without the extract there is no friction or allow-rule evidence. The gate used symlink-resolved paths. Whether a user config dir behind a symlink should be tolerated is a product decision.
2. `friction prepare` requires the audit scope to equal the project plus its linked worktrees. An audit run with a single `--cwd` on a project with linked worktrees is refused with the generic "preparation refused; local evidence or private state is invalid or unavailable". The gate brief's single-`--cwd` command works only on projects without linked worktrees.
3. The gate brief's prune fixture instruction to leave the root `.git` pointer unaged is stale: the idle walk checks the `.git` entry's mtime before skipping it, so the pointer, the admin `index` and `logs/HEAD`, and the common branch log must also be at least 24 h old. Until then the refusal is "worktree is not idle for 24 hours".
4. `dispatch-status` lists every running dispatch command on the machine, including other projects' paths. The output was not saved.
5. On macOS, host-fix apply refuses with "unknown marker or wrong platform" before reaching the S3 disabled message; the disabled message was seen only through `undo`. The Linux apply path is untested here.
6. Test suite cost and sensitivity: 1538 tests take 29 to 36 minutes serially on this machine (`test_backup_commit` alone is about 15 minutes), so a 900 s cap on `tools/ci-local` times out. Run 1 of `tools/ci-local` (3.12) hit that cap (not a hang; progress continued). Run 2 failed with 3 errors: two SIGHUP tests (the runner was launched with SIGHUP ignored) and `test_submodule_hidden_index_and_ignore_values` (`probe.worktrees()` returned None once under load). Those three files passed when rerun alone, and run 3 was fully clean. Tests also fail if `KAIZEN_BACKUP_DIR` or `KAIZEN_USAGE_DB` is set in the environment (`test_environment_unset`) or if the runner ignores SIGINT.
7. The context budget is 1023 of 1024 bytes.
8. Exit codes: `token-audit` returns 0 after a failed extract write; `kaizen-scheduled` refusals return 2 with fixed generic messages.

## Held items for the owner

Rows 3, 21, 24, 27, 31, 34, 37 and 38. The allow-rule grant claim, the marker and Time Machine write claims, the scheduled commit and review claims, the interactive cycle, the real hook and the P24a runtime envelopes are unproven; keep them proposal-only or held. Row 42 needs a decision: implement the `--bench` mode or drop it from the P14c, P14d and P28 verification lists.
