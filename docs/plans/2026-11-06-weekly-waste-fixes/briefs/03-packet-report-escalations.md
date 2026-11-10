# 03: packet-report escalations

Repo: agent-kaizen (cwd). Do not commit. Do not edit `.claude-plugin/plugin.json` or `CHANGELOG.md`.

## Why
Outcome logs keep only the final model and effort per packet. When a packet starts on Terra, escalates to Sol, and lands on Sol, calibration only sees Sol. The weekly review could not tell how many packets escalated.

## Change
1. `docs/outcome-log.md`: add an optional key `dispatch_models`: a list, in dispatch order, of objects `{"model": str, "effort": str, "rounds": int}` (one per dispatch of the packet). Older rows without it stay valid. Keep the contract's wording style.
2. `scripts/packet-report`:
   - Accept and validate `dispatch_models` (ignore malformed values like other optional keys are handled; check `DEFAULTS` and the row normalisation).
   - New result key `escalations`: count of packets whose `dispatch_models` has more than one distinct model, plus a count per `from->to` pair (first model -> final model), sorted by count. Packets without `dispatch_models` are counted as `unknown` in a `dispatch_models_coverage` figure (`n_with`, `n_total`).
   - Markdown/text output: one short "Escalations" section, bounded like the existing sections (use the existing `bounded` helper).
   - Update the module docstring's JSON key list.
3. Tests in `tests/test_packet_report.py` following existing patterns: rows with and without the key, an escalation Terra->Sol, malformed value ignored, coverage numbers.

## Verify
`python3 -m unittest tests.test_packet_report`
