# 02: `packet-report` and the outcome-log contract

## Goal and why
Any project that appends one JSON line per landed packet to `out/packets.jsonl` should feed the plugin's audit. Today the first-pass/fix-rate/calibration report exists only as New World's `tools/packet_report.py`, which the live `kaizen-token-audit` shells out to. Port it into the plugin as a generic `scripts/packet-report`, and document the log and commit-trailer contract in `docs/outcome-log.md`.

## Context
- Repo: ~/github/highwayoflife/agent-kaizen. Python 3.9+, stdlib only. Read `AGENTS.md`. No personal paths or project names (New World etc.) in any tracked file.
- Reference implementation (read-only, do not edit it): `~/github/highwayoflife/NewWorld/tools/packet_report.py` (129 lines) and the writer `.../NewWorld/tools/packet_log.py` (keys at its `build()` return). Real sample: `.../NewWorld/out/packets.jsonl` (16 rows, read-only; for the parity check only; never copy it into the repo).
- Row keys written by a project: `ts` (ISO UTC), `id`, `plan`, `merge_sha`, `model`, `effort`, `risk` (`low|normal|high|untagged`), `fix_origin` (null or e.g. `batch-review`, `final-audit`), `fixes` (list of packet ids this packet fixes), `dispatches`, `rounds`, `status` (`DONE|CHECKS FAILING|CODEX FAILED|ENV NOT READY|none`), `slot_wait_s`, `playmode_s`, `editmode_s`, `dotnet_s`, `wall_s`, `lines`, `files`, `area`, `tokens_in`, `tokens_out`, `note`. Required by the report: `ts`, `id`, `model`, `effort`. Everything else optional with defaults: fix_origin None, fixes [], dispatches 1, rounds 0, status "unknown", wall_s None, lines 0, area "mixed", risk "untagged". Commit trailers on the merge commit that the writer reads: `Risk:`, `Fix-Origin:`, `Fixes:`.
- Behaviour to keep exactly: first-pass = status DONE and dispatches == 1 and rounds == 0, over rows with no fix_origin; fix rate = share of rows whose id appears in some other row's `fixes`; groups by (model, effort) and (model, effort, area); proposals only when n >= 8: UP if first-pass < 70% or fix rate > 30%, DOWN if first-pass >= 95% and no row in the group was fixed by a `batch-review`/`final-audit` fix; "too few" rows when n < 8; JSON keys `groups, area_groups, totals{packets,span_days,merges_per_day}, fix_origins, proposals, rule, disclaimer`; `--since` filters samples but fixes from the whole file still count; text and `--markdown` renderers with the 8/3/5-row caps.
- Changes from the original: (a) the ladder is configurable. `--ladder "haiku,sonnet medium,sonnet high,opus high"` (default), else the global setting `calibrationLadder` read directly from `<claude home>/agent-kaizen.json` (`$CLAUDE_CONFIG_DIR` or `~/.claude`; a JSON list of strings, each `model` or `model effort`; the first rung per model with no effort is allowed). (b) Model normalisation: if the model string is not a ladder model, use its last `-`-separated segment when that is a ladder model (so `gpt-6.1-terra` matches `terra`). (c) Add `--until YYYY-MM-DD` (exclusive upper bound, for before/after use) next to `--since`. (d) Skip malformed lines, count them, print `skipped N malformed rows` to stderr. (e) `--project DIR` as shorthand for `--packets DIR/out/packets.jsonl`; default `--packets` is `./out/packets.jsonl`. (f) Null-safe medians (wall_s may be None).

## Scope / do not touch
Create `scripts/packet-report` (executable), `docs/outcome-log.md`, `tests/test_packet_report.py`, `tests/fixtures/packets.jsonl` (synthetic, at least 12 rows over two models, include fixes and fix_origins, no real names). Do not edit existing files. No version/CHANGELOG edits.

`docs/outcome-log.md` content (plain short sentences): purpose; the JSONL key table (required/optional/type); the three trailers and the allowed `Fix-Origin` values; how a project writes a row (one atomic append per landing; example one-line writer using only the stdlib); the optional project commands the owner can name in global config under `projectCommands` (`shadowStatus`, `slowTests`, `speedReport`; argv lists run with the project root as cwd, each printing Markdown or plain lines; shadow status may write state in the project, e.g. a STOP flag); how enrolment works (project has `docs/kaizen/`); the calibration rule text and that proposals are never applied automatically.

## Acceptance criteria
1. `python3 scripts/packet-report --packets tests/fixtures/packets.jsonl --json` prints valid JSON with exactly the documented keys; a fixture group with n >= 8 and first-pass < 70% yields an UP proposal, one with first-pass >= 95% and no audit fixes yields DOWN, small groups appear as "too few".
2. `--since` and `--until` change the sample set but not the set of known fixes; `--until` is exclusive.
3. Missing file prints "No packet data yet" and exits 0; unreadable/invalid arguments exit 2; malformed lines are skipped and counted.
4. Ladder override works via `--ladder` and via `calibrationLadder` in a temp `CLAUDE_CONFIG_DIR`; `--ladder` wins.
5. Parity: with `--ladder "haiku,terra low,terra medium,terra high,sol medium,sol high"`, `python3 scripts/packet-report --packets ~/github/highwayoflife/NewWorld/out/packets.jsonl --json | python3 -m json.tool --sort-keys` equals `cd ~/github/highwayoflife/NewWorld && python3 tools/packet_report.py --json | python3 -m json.tool --sort-keys` (diff is empty). Record the result in your report; do not put the New World path in any tracked file.
6. `docs/outcome-log.md` exists and every key in the table is a key the code reads or tests mention.
7. Full suite passes.

## Verification
```
cd ~/github/highwayoflife/agent-kaizen
python3 -m unittest tests.test_packet_report -v
python3 -m unittest discover -s tests
python3 scripts/packet-report --help
```

## Working tree
Codex packets run in their own git worktree (`git worktree add ~/github/highwayoflife/agent-kaizen-wt-02 -b kz-02`, created by the orchestrator). Work only there and run the commands from that directory.

## Reporting
Files changed, test counts, parity diff result. Do not commit or push. Stop and report if the New World file's behaviour differs from the description above.

## Suggested agent / model / effort
codex-engineer, Terra, medium. Risk: normal.
