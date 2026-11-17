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

A failed write must never fail the caller's work. Callers should use `packet-event ... || true`.

Report conventions: see the Report section.
