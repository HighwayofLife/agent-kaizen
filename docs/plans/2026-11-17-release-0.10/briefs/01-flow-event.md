# 01: Flow event writer (`packet-event`) and the event format doc

## Goal and why

Packets spend most of their wall time waiting between steps, but nothing records per-state times. Add a tiny append-only event log and a helper that any shell tool can call, and document the format once so the report (packet 05) and the skill (packet 10) cite it. This packet freezes the schema and the default path.

## Context

- agent-kaizen is a Claude Code plugin: stdlib-only Python scripts in `scripts/`, tests in `tests/`, docs in `docs/`. Read `AGENTS.md` (Rules section).
- Pattern for atomic append: `docs/outcome-log.md:33-37` (one `os.write` on a descriptor opened `O_WRONLY | O_CREAT | O_APPEND`). `scripts/kaizen-scheduled:1080` also opens with `O_APPEND`.
- Timestamp parsing pattern (Python 3.9's `datetime.fromisoformat` rejects a trailing `Z`): `scripts/kaizen-scheduled:686-694` (`parse_time`: replace `Z` with `+00:00`, require tzinfo, convert to UTC). Reuse that approach; do not import from `kaizen-scheduled`.
- Test style: `tests/test_packet_report.py:1-17` (subprocess with `sys.executable`, `tempfile`).
- CI runs `<script> --help` on every tracked executable under `scripts/` (`.github/workflows/ci.yml:46-50`): use `#!/usr/bin/env python3` and `chmod +x`.
- Decisions already made: states are `queued`, `dispatched`, `round-N` (N a positive integer), `checks`, `slot-wait`, `review`, `ready`, `landed`, `failed`. Terminal states are `landed` and `failed`. Default file `out/packet-events.jsonl` (external) (relative to the current directory). This packet does not edit CHANGELOG.md.

## Scope / do not touch

Creates: `scripts/packet-event`, `tests/test_packet_event.py`, `docs/flow.md`.
Edit only those. Do not touch `docs/outcome-log.md`, `README.md`, `CHANGELOG.md`, `.claude-plugin/`, `scripts/install-schedule`, `scripts/kaizen-link` (packet 11 registers the script).

## Steps

1. Write `docs/flow.md` first (schema section, frozen): one JSON object per line with keys `ts` (UTC ISO string ending in `Z`; seconds, plus microseconds only when nonzero), `id` (non-empty string, no newline), `state` (one of the list above), optional `detail` (string, omitted when not given). State the default path, the per-writer ordering note (events from one writer are in order; across writers sort by `ts` then file order), no rewriting or deleting lines, the local-filesystem atomicity limit and 4096-byte line cap, no locking promise on network filesystems, that a failed write must never fail the caller's work (callers use `|| true`), and what `wait` vs `touch` means is added by packet 05 (leave a one-line pointer: "Report conventions: see the Report section").
2. Write `scripts/packet-event ID STATE [--file PATH] [--ts ISO] [--detail TEXT]`.
   - `--ts` must be timezone-aware ISO (accept `Z`); naive or unparsable: exit 2 with a one-line message. Default is the current UTC time.
   - Validate before opening the file. Create the parent directory. Serialise with `json.dumps(..., ensure_ascii=False, separators=(",", ":"))` plus `\n`, encode UTF-8, refuse lines over 4096 bytes (exit 2), then one `os.write` on an `O_APPEND` descriptor. If `os.write` returns fewer bytes than the line, exit 1 and say so on stderr; any `OSError` exits 1 with the message.
   - Exit codes: 0 written; 1 write failed; 2 invalid input (argparse errors already exit 2).
3. Write the tests, then run them.

## Acceptance criteria

1. `scripts/packet-event --help` exits 0 and names the states, default path and exit codes.
2. A valid call appends exactly one line with keys `ts`, `id`, `state` (and `detail` only when given); `ts` ends in `Z` and is UTC for input like `2026-01-01T02:00:00+02:00` (output `2026-01-01T00:00:00Z`).
3. Invalid input (empty ID, ID with a newline, unknown state, `round-0`, `round-x`, naive `--ts`, line over 4096 bytes) exits 2 and leaves the file untouched or absent.
4. `round-1` and `round-12` are accepted; `ROUND-1` is not.
5. Concurrency test: start 8 subprocesses (`subprocess.Popen`, started before any is awaited), each appending 25 events with distinct ids to the same file; after all exit 0, the file has exactly 200 lines, every line parses as JSON with the expected keys, and the set of `(id, state)` pairs has 200 members.
6. Custom `--file` in a missing nested directory is created; non-ASCII and quotes in `--detail` round-trip through `json.loads`; an unwritable target (a directory path) exits 1.
7. `docs/flow.md` contains the schema table, the default path and each limitation named in step 1, in plain short sentences.

## Verification

```sh
python3 -m unittest discover -s tests -p 'test_packet_event.py' -v
scripts/packet-event --help
python3 -m unittest discover -s tests -p 'test_repo.py' -v
```

## Reporting

At most 20 lines: files changed, test results, anything unsure, and one proposed CHANGELOG bullet (do not edit CHANGELOG.md). Do not commit or push. Stop and report if the repo shows a different append pattern than described above. If the packet exceeds about 400 changed lines, stop and report instead of dropping criteria.

## Suggested agent / model / effort and risk

`codex-engineer` / Terra `high`. Risk: **high** (concurrency contract; per-packet review before merge). Estimated size: 300 lines.
