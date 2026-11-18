# 08: Review economics and evidence-qualified calibration HOLD in `packet-report`

## Goal and why

In the field log, 29 fix packets in 14 days were produced, 9 of them fixing an earlier fix, and two had no MUST-FIX finding; yet `packet-report` proposed "one rung UP" for every Terra row even though Terra's fix packets were tiny (about 75 lines, 3.6M tokens, against 24M for Sol). Add a review-economics section, and make an UP proposal become HOLD only when the evidence is complete and the attributed fixes are small. Unknown evidence never produces a HOLD.

## Context

- agent-kaizen is a Claude Code plugin; scripts are stdlib-only Python 3.9, tests in `tests/`. Read `AGENTS.md` (Rules).
- Packet 04 (already merged) added to `scripts/packet-report`: ladder-independent model normalisation, result keys `unknown_models`, `data_coverage`, `landed_failing`, a per-row evidence helper (token and cost states: known, zero, missing) and a `Data quality` text section. Reuse that helper; read its code first.
- `scripts/packet-report` as of 778f546 (line numbers shift after 04; locate with `rg -n`): `summarize` :49-121 builds `fixed` and `audited` id sets :52-55 and the proposals inside `groups()` :63-93 (UP when `n >= 8` and first-pass < 70% or fix rate > 30%; DOWN when first-pass >= 95% and no batch-review/final-audit fixes); `RULE` string :19 (printed after `Calibration proposals`); `render` :123-157; `DEFAULTS` :159-161 with `lines=0`; `read_rows` :164-205 does `row = dict(DEFAULTS, **row)` at :175, so an absent `lines` looks like an explicit 0. This packet must record whether `lines` was present and valid before that merge.
- `scripts/kaizen-project-report:39-52` runs `packet-report --markdown` and splits at the line `Calibration proposals`; every new text section goes before it, and `tests/test_project_report.py` must still pass.
- `tests/test_packet_report.py:24` asserts the exact JSON key set; update it for the new keys. Docs: `docs/outcome-log.md` (row table :7-31), `scripts/README.md` packet-report section (about :535-549).
- Stale wording to retire: `skills/cycle/SKILL.md:24` says "Propose calibration changes up or down one rung only."
- Decisions already made (orchestrator):
  - A fix packet is a row with non-null `fix_origin`. Fix-of-fix: a fix packet whose `fixes` list names another packet (not itself) that is also a fix packet in the full log.
  - `fix_per_landed` = fix packets over rows with a non-empty `merge_sha` (selected rows), `null` when there are no landed rows.
  - Optional row field `review_severities`: a list of strings. A known empty list means no MUST-FIX; missing or null means unknown; a list containing `MUST-FIX` (case-insensitive) is positive. Never infer missing evidence.
  - HOLD replaces UP only when at least one fix packet is attributed to the group and every attributed fix has explicit valid `lines`, known `tokens_in` (above 0) and known `tokens_out`, with `lines` below `--small-fix-lines` (default 100) and `tokens_in + tokens_out` below `--small-fix-tokens` (default 4000000). Otherwise UP stands and carries the reason. DOWN and the sample-size and fix-rate rules are unchanged.
  - Counts follow `--since`/`--until`; attribution of fixes to a group looks across the full log (the same policy as the existing fix rate).
  - No savings are claimed. This packet does not edit CHANGELOG.md.

## Scope / do not touch

Creates: nothing.
Edit only: `scripts/packet-report`, `tests/test_packet_report.py`, `tests/test_project_report.py` (one added test), `docs/outcome-log.md`, `scripts/README.md` (packet-report section only), `skills/cycle/SKILL.md` (:24 only), `scripts/rules-lint.patterns`, `tests/test_rules_lint.py` (one new test method; leave `tests/fixtures/rules_lint/` alone).
Do not touch `scripts/kaizen-project-report`, other skills, `README.md`, `CHANGELOG.md`.

## Steps

1. Baseline first: before editing, save `scripts/packet-report --packets tests/fixtures/packets.jsonl --json` and the default text output to the git-ignored `out` folder at the repo root as `before.json` and `before.txt`.
2. In `read_rows`, record `lines_known` (present, number, not bool) before the defaults merge; keep `lines` defaulting to 0 for the existing medians.
3. Add `review_economics` to the result: `{landed, fix_packets, fix_per_landed, fix_of_fix: {count, rate, unknown_references}, no_must_fix: {count, ids}, severity_coverage: {known, unknown, unknown_ids}, thresholds: {small_fix_lines, small_fix_tokens}}`. `rate` is fix-of-fix over fix packets (`null` when none); `unknown_references` counts ids in fix packets' `fixes` that match no row in the log.
4. HOLD: for each proposal whose direction would be UP, collect attributed fix packets and decide; the proposal gets `direction` `HOLD` or `UP` plus `fix_evidence: {attributed, complete, small}` and, for HOLD, `reason`; an UP that stands because of missing, zero or large evidence adds `hold_blocked` with the short reason (`no attributed fixes`, `unknown evidence: <ids>`, `fix not small: <ids>`). Add flags `--small-fix-lines N` and `--small-fix-tokens N` (integers at or above 0; invalid exits 2). Update `RULE` to mention HOLD.
5. Text: add `Review economics` (before `Calibration proposals`) with the counts, rates with denominators, unknown references, severity coverage and no-MUST-FIX ids (bounded to 10); proposal lines read `<model> <effort>: HOLD (<reason>; thresholds <lines> lines, <tokens> tokens)` or `...: propose UP one rung` with ` (hold not applied: <reason>)` appended when applicable.
6. Docs: `docs/outcome-log.md` documents `review_severities`; the docstring and `scripts/README.md` document the new keys, flags, HOLD semantics and the filter policy. Replace the cycle skill sentence at :24 with: follow the project report's calibration proposals; UP or DOWN moves one rung, HOLD keeps the tier and carries its reason. Add the stale pattern `calibration changes up or down one rung only` to `scripts/rules-lint.patterns`, a new test method in `tests/test_rules_lint.py` that writes the old sentence into a temp repo `CLAUDE.md` and expects a hit, and confirm with `rg -n "up or down one rung" --glob '!docs/plans/**'` that no old sentence remains.
7. After the code is done, save `after.json` and `after.txt` the same way and put a short diff summary (keys added; proposals and coverage changed or not) in your report. Do not claim measured savings.

## Acceptance criteria

1. `fix_per_landed` is fix rows over rows with `merge_sha`; zero landed gives `null`; a fix-of-fix is counted once per fix packet; self-references and unknown references are excluded and the unknown ones counted.
2. Severity: `[]` counts as no MUST-FIX, missing or null is unknown and is never listed as no-MUST-FIX, `["MUST-FIX", "NIT"]` is positive; coverage counts add up to the fix packets.
3. HOLD tests, one method each: all attributed fixes small and complete gives HOLD with reason and thresholds; one fix with `tokens_in` 0, one with missing `lines` (explicit `lines: 0` is known), one with missing `tokens_out`, and one at exactly the threshold (not below) each keep UP with `hold_blocked`; no attributed fix keeps UP; attribution works through an alias label (`gpt-6.1-terra` fixed by a `terra` fix) and across rows outside `--since`; custom `--small-fix-lines` and `--small-fix-tokens` change the outcome; invalid flag values exit 2.
4. DOWN and `n < 8` ("too few") lines are unchanged; legacy fixtures give the same old keys and values.
5. Text and JSON contain thresholds, counts and reasons; the `Review economics` section appears before `Calibration proposals`; `tests/test_project_report.py` has a test that the markdown project report still splits correctly with the new section present.
6. Key-set assertion updated; stale-wording test passes; `rg` finds no remaining old cycle sentence.
7. The report lists before/after output differences from step 1 and 7.

## Verification

```sh
python3 -m unittest discover -s tests -p 'test_packet_report.py' -v
scripts/packet-report --help
scripts/packet-report --packets tests/fixtures/packets.jsonl --json | python3 -c 'import json,sys; d=json.load(sys.stdin); print(sorted(d))'
for m in test_project_report test_rules_lint test_process_rules test_repo; do python3 -m unittest discover -s tests -p "$m.py"; done
rg -n "up or down one rung" --glob '!docs/plans/**'
```

## Reporting

At most 20 lines: files changed, test results, before/after diff summary, limitations, one proposed CHANGELOG bullet (do not edit CHANGELOG.md). Do not commit or push. Stop and report if packet 04's evidence helper is missing. Split trigger: if the packet exceeds about 400 changed lines, finish review economics and docs with tests, then stop and list the HOLD logic for a follow-up packet.

## Suggested agent / model / effort and risk

`codex-engineer` / Terra medium. Risk: **normal**. Estimated size: 380 lines. Batch reviewer regression modules: `test_packet_report`, `test_project_report`, `test_rules_lint`, `test_process_rules`.
