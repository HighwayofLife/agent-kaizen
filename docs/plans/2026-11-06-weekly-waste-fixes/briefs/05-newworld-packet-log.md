# 05: New World packet log records every dispatch's model

Repo: a New World worktree (cwd). Do not commit. Touch only `tools/packet_log.py`, `tools/tests/test_packet_log.py`, and `tools/land_packet.sh` only if needed.

## Why
`out/packets.jsonl` keeps only the final `model`/`effort` (passed at landing). Packets that started on Terra and escalated to Sol or Astra look like Sol/Astra-only packets, so calibration cannot see escalations.

## Change
In `tools/packet_log.py`, where `dispatch_dirs` (the packet's `out/dispatch/*` directories) and their `report.md` texts are read, also parse from each report, in dispatch order:
- `Model/effort: <model> / <effort>` (line written by codex-dispatch)
- `Rounds used: <n>/<max> resumes`
and write a new optional key `dispatch_models`: a list of `{"model": str, "effort": str, "rounds": int}`, one per dispatch dir whose report has a Model/effort line (skip ones that do not). Omit the key (or write `[]`, match how other optional fields are handled) when none parse. Keep the existing `model`, `effort`, `dispatches`, `rounds` fields unchanged. Keep the append atomic and the `--prepare` / `--prepared` paths working (the prepared metadata must carry the new key).

Add tests in `tools/tests/test_packet_log.py` following the existing patterns: two dispatch dirs (terra then sol) produce two entries in order; a report without the line is skipped; prepared round-trip keeps the key.

## Verify
`python3 -m unittest discover -s tools/tests -p 'test_packet_log.py' && python3 -m unittest discover -s tools/tests -p 'test_land_packet.py'`
(if the test layout needs a different invocation, use the one in `tools/tests` docs or other tests' headers)
