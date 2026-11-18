# Packet flow events

The default log is `out/packet-events.jsonl`, relative to the current directory.
Each line is one JSON object.

| Key | Required | Value |
| --- | --- | --- |
| `ts` | yes | UTC ISO timestamp ending in `Z`, with seconds and microseconds only when nonzero |
| `id` | yes | Non-empty string without a newline |
| `state` | yes | `queued`, `dispatched`, `round-N` (positive integer N), `checks`, `slot-wait`, `review`, `ready`, `landed`, or `failed` |
| `detail` | no | String; omitted when not given |

`landed` and `failed` are terminal states. Events from one writer are in order. Across writers, sort by `ts`, then file order. Never rewrite or delete lines.

Each line is at most 4096 bytes including its newline. A single append is atomic only within the local filesystem's guarantees. There is no locking promise on network filesystems.
Readers must skip lines that are not valid JSON, since a failed short write can leave a partial line.

A failed write must never fail the caller's work. Callers should use `packet-event ... || true`.
Exit codes are 0 for written, 1 for write failed, and 2 for invalid input.

Report conventions: see the Report section.

## Report

Run `scripts/flow-report --events PATH` to report on a log. Add `--json` for JSON.
Each interval runs from an event to the next event for the same packet. Open final states have no duration.
Lead time runs from the first event to the first terminal event. Incomplete packets have no lead time.
Events after the first terminal event are anomalies and do not enter the calculations.
Wait is time in `queued` and `slot-wait`. Touch is time in `dispatched`, `round-N`, `checks`, `review`, and `ready`.
Percentiles use the nearest rank: sort durations and take the value at position `ceil(q * count)`, counting from one.
WIP counts a packet from its first non-terminal event to its first terminal event. A packet that starts terminal never enters WIP. Changes at the same timestamp are applied before reporting WIP.
