# P28 delta (2026-11-18): agent-runnable part of the real-input gate

Read `briefs/28-real-input-gate.md` first. This delta narrows it to what an agent can run without a person present and without touching the machine's real configuration. Every step this delta excludes is still recorded in `gate-results.md` as **BLOCKED (needs owner)**, with the reason.

## Where things are

- Candidate 0.13.0: the `release-0.13` checkout at the repo root you are given (HEAD `b2bb1ff`). This is `FRICTION_PLUGIN`.
- Baseline 0.12.0: tag `v0.12.0` (`2e0e643`). Create it as a detached worktree inside your private scratch directory with `git worktree add --detach <scratch>/base v0.12.0`, and remove it at the end with `git worktree remove --force`. Nothing else may be created outside scratch.
- Private scratch (`FRICTION_RUN`): make a new directory under `$TMPDIR`. It holds all fixtures, installs, configs, reports and timing output.

## Hard safety rules

1. **Isolated config only.** Every command runs with `CLAUDE_CONFIG_DIR` and `HOME`-derived Kaizen paths pointed into scratch. Never read or write the real `~/.claude`, `~/.codex`, the real `agent-kaizen.json`, real settings, or real audits.
2. **No real scheduler.** Do not run `install-schedule --apply` against the real user crontab or launchd. Run it only if `install-schedule --help` or its source documents a way to target an alternative crontab file or launchd directory inside scratch, and say how you isolated it. Otherwise record it as BLOCKED.
3. **Fixture projects only.** Create the disposable Git projects for prune, marker and commit inside scratch. No live operation may target a real repository, including this checkout.
4. **No interactive acceptance.** The allow-rule step needs ten prompts accepted by a person. Record it as BLOCKED. Still run the refusal path on its own: `kaizen-allow-rule add` without the evidence must refuse.
5. **Token use.** Any step that needs a signed-in `claude` (interactive `/agent-kaizen:cycle`, the real hook on `claude -p`, `review --force` without `--dry-run`) is BLOCKED unless it works with the isolated config without copying credentials. Never copy credential files.
6. Live host-fix writes and worktree-prune removal stay disabled (S3). Verify the code refuses them, and record the three P19 residuals as accepted residuals for 0.13.0, still open.

## Run

Run everything else in the original brief's Verification list that fits these rules. Install the candidate and the baseline into scratch bins with `install-schedule` as far as rule 2 allows, or run the scripts straight from the checkouts and say which you did. Also run:

- the friction prepare / import / acknowledge / verify / dismiss / reopen / done flow on fixtures;
- backup begin / finish / commit / undo on the fixture commit project;
- `housekeep --dry-run`;
- `review --dry-run --json`;
- extraction timing: at least 5 interleaved warm runs each of baseline, candidate on, and candidate `--no-friction`. Use synthetic or fixture transcripts inside scratch, never real transcripts;
- `tests/bench_token_audit.py --baseline 2e0e643 --max-ratio 1.10`;
- `python3 tests/test_friction_sampler.py --bench`.

## Output

- Write `docs/plans/2026-11-17-friction-port/gate-results.md`. Give one row per check: command (with paths redacted to placeholders), PASS / FAIL / BLOCKED, conditions, and trimmed output. Put the timing results in their own table.
- Add a one-line P28 status to the P28 row in `plan.md`, or below the packet table if the row has no notes column.
- Privacy: no absolute home paths, user names, machine or project names, credentials or raw transcripts. Use `~`, or placeholders such as `<scratch>`.
- Do not commit or push. Do not change the version or CHANGELOG. Do not touch any other file in the checkout.
- Report: counts of PASS / FAIL / BLOCKED, every FAIL with its cause, timing ratios, and confirmation that scratch was cleaned up (or its path, if you kept it for evidence).
