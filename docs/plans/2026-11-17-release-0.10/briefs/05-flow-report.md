# 05: Flow report (`flow-report`)

## Goal and why

In the logs that motivated this release, 135 packets summed 740 hours of wall time and slot waits alone were 67.7 hours; one packet waited 7.7 hours between fix rounds for a 13 to 25 minute check. Packet 01 adds an event log; this packet reads it and shows where the time goes: lead time per packet, time per state, queue versus touch share, work in progress over time, and the longest waits.

## Context

- agent-kaizen is a Claude Code plugin; scripts are stdlib-only Python 3.9, tests in `tests/`. Read `AGENTS.md` (Rules).
- The event format is frozen in `docs/flow.md` (created by packet 01; read it first): one JSON object per line with `ts` (UTC ISO ending in `Z`), `id`, `state` and optional `detail`; default file `out/packet-events.jsonl` (external); states `queued`, `dispatched`, `round-N`, `checks`, `slot-wait`, `review`, `ready`, `landed`, `failed`; terminal states are `landed` and `failed`.
- Timestamp parsing: Python 3.9's `datetime.fromisoformat` rejects `Z`; use the approach at `scripts/kaizen-scheduled:686-694` (replace `Z` by `+00:00`, require tzinfo, convert to UTC). Offsets other than `Z` must work too.
- Patterns to copy from `scripts/packet-report`: median and rendering split into a result dict and a `render` function (`:49-157`), text bounded by a `bounded` helper (`:124`), `--json` printing `json.dumps(result, sort_keys=True)` (`:235`), error exit 2 on bad input (`:232-234`). Test style: `tests/test_packet_report.py:1-17`.
- CI runs `--help` on every tracked script (`.github/workflows/ci.yml:46-50`): `#!/usr/bin/env python3`, executable bit.
- Decisions already made (orchestrator): Terra `high`; exit codes 0 report produced (also for an empty file, malformed lines or anomalies), 2 usage error or missing/unreadable file; wait = `queued` + `slot-wait`, touch = `dispatched`, `round-N`, `checks`, `review`, `ready`. This packet documents that convention in `docs/flow.md`.
- This packet does not edit CHANGELOG.md.

## Scope / do not touch

Creates: `scripts/flow-report`, `tests/test_flow_report.py`.
Edit only: `docs/flow.md` (append a `## Report` section; do not change the schema section).
Do not touch `scripts/packet-event`, `tests/test_packet_event.py`, `scripts/packet-report`, `README.md`, `scripts/README.md`, `CHANGELOG.md`, installer lists (packet 11).

## Behaviour (fixed)

`flow-report [--events PATH] [--json]`.

1. Read lines in file order. A line is malformed (counted, never fatal) when it is not a JSON object, lacks a non-empty string `id`, has a `state` outside the list (`round-N` needs a positive integer N), or has a missing, unparsable or timezone-naive `ts`.
2. Per packet, sort events by UTC `ts`, ties by file order (stable). Events after the packet's first terminal event are anomalies: listed (`id`, `ts`, `state`, reason) and excluded from every calculation.
3. A state is held from its event until the packet's next event; that interval's duration (seconds) is attributed to the state. Terminal states accrue no duration. A final non-terminal event is open: no duration, counted in `open_final_states`, never closed against "now".
4. Lead time = first event to first terminal event; a packet without a terminal event has lead time `null` (incomplete).
5. Per-state table: count, total, p50, p90 using nearest-rank percentiles (the value at 1-based index `ceil(q*n)` of the sorted durations). All `round-N` states report together under `round`.
6. Queue versus touch: wait total, touch total, shares = each total over (wait + touch) of closed classified intervals; shares are `null` when that denominator is 0.
7. Top waits: the 10 longest closed wait intervals (`id`, `state`, `start`, `end`, `seconds`), longest first, ties by start then id.
8. WIP: a packet is counted when its first event is non-terminal and is removed at its first terminal event, once each. Output change points `[{ts, wip}]`, one per distinct timestamp after applying every event at that timestamp (file order), plus `max_wip`. A packet whose first event is terminal is never counted.

Text output sections, in order: a header line `Flow report: P packets, E events, M malformed line(s), A anomaly(ies), O open final state(s)`; `Lead time`; `Time per state`; `Queue vs touch`; `Top waits`; `WIP`; `Anomalies` (only when present); each bounded to about 12 lines. JSON keys (`packets`, `events`, `malformed_lines` and `open_final_states` are integer counts): `packets`, `events`, `malformed_lines`, `anomalies`, `open_final_states`, `lead_times` (`[{id, seconds, complete}]`), `states` (`{state: {count, total_s, p50_s, p90_s}}`), `queue_touch` (`{wait_s, touch_s, wait_share, touch_share, intervals}`), `top_waits`, `wip`, `max_wip`. Empty input: header with zeros and `no events`, exit 0.

## Acceptance criteria

1. `scripts/flow-report --help` exits 0 and documents the default path, exit codes and the wait/touch convention.
2. Tests (each its own method): out-of-order events; identical timestamps within a packet and across packets (stable file order); repeated states; events after a terminal state (anomaly, excluded); incomplete packet (lead time null, open final state counted, no duration to "now"); several packets interleaved; percentiles for n=1, 2 and 10; nearest-rank value checked by hand in the test; wait/touch shares including a zero denominator; top-10 truncation and tie order; WIP with a packet that opens and closes at the same timestamp, a packet counted once despite repeated events, and a packet whose first event is terminal; malformed lines (bad JSON, missing id, unknown state, `round-0`, naive `ts`) counted and not fatal; `Z` and `+02:00` timestamps; empty file; missing file exits 2; `--json` parses with exactly the keys above.
3. The `## Report` section of `docs/flow.md` states the wait/touch convention, the interval and lead-time definitions, nearest-rank percentiles, and the WIP rule, in plain short sentences, and leaves the schema section untouched (`git diff` shows only added lines there).
4. If `python3.9` is on PATH, the test module also passes under it (`python3.9 -m unittest discover -s tests -p 'test_flow_report.py'`); report whether it was available.

## Verification

```sh
python3 -m unittest discover -s tests -p 'test_flow_report.py' -v
scripts/flow-report --help
python3 -m unittest discover -s tests -p 'test_repo.py'
git diff --stat docs/flow.md
```

## Reporting

At most 20 lines: files changed, test results, limitations, one proposed CHANGELOG bullet (do not edit CHANGELOG.md). Do not commit or push. Stop and report if `docs/flow.md` or `scripts/packet-event` is missing or differs from the schema above. Split trigger: if the packet exceeds about 400 changed lines, finish everything through `Queue vs touch` with tests and docs, then stop and list WIP and top waits for a follow-up packet.

## Suggested agent / model / effort and risk

`codex-engineer` / Terra `high` (ordering and WIP invariants are the hard part). Risk: **normal**. Estimated size: 400 lines. Batch reviewer regression modules: `test_flow_report`, `test_packet_event`, `test_repo`.
