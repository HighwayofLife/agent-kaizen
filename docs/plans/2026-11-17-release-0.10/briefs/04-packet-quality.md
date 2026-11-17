# 04: Packet data quality in `packet-report`

## Goal and why

`packet-report` calibration is misleading on real logs: the same model appears under two labels (`terra` and `gpt-6.1-terra`) when the ladder names only one, rows labelled `unknown` are silently grouped, writers that cannot measure tokens log `tokens_in=0`, and packets that landed with checks failing look like successes. Fix the data-quality side only; packet 08 later adds review economics and the conditional HOLD on top of the evidence helpers added here.

## Context

- agent-kaizen is a Claude Code plugin; scripts are stdlib-only Python 3.9, tests in `tests/`. Read `AGENTS.md` (Rules).
- `scripts/packet-report`: docstring with the JSON key list :3-13; `normalize_model(model, models)` :43-46 only matches a trailing hyphen segment that is in the ladder; `summarize` :49-121 (normalises `selected` rows :60, dispatch histories :97-101); `render` :123-157 (text sections `Packet outcomes` ... `Fix origins`, `Escalations`, `Calibration proposals` last); `read_rows` :164-205 (optional fields are not validated, so odd tokens never drop a row); `main` :207-239.
- The script reads no `tokens_in`, `tokens_out`, `cost` or `merge_sha` field today. `docs/outcome-log.md:7-31` lists the row keys (tokens yes, cost no).
- `scripts/kaizen-project-report:39-52` runs `packet-report --markdown` and splits its output at the line `Calibration proposals` (`lines.index('Calibration proposals')`). New text sections must therefore come before that heading.
- `tests/test_packet_report.py:24` asserts the exact JSON key set (`assertEqual(set(data), {...})`); additive keys require updating that set. Fixture: `tests/fixtures/packets.jsonl` (17 rows).
- Stale wording to retire: `scripts/README.md:545` says "Names are normalised against the calibration ladder".
- Decisions already made (orchestrator): unknown or missing data is reported, never treated as zero or guessed; no price estimation; existing JSON keys and old rows keep working; additive keys only. This packet does not edit CHANGELOG.md.

## Scope / do not touch

Edit only: `scripts/packet-report`, `tests/test_packet_report.py`, `docs/outcome-log.md`, `scripts/README.md` (the `packet-report` section only, about :535-549), `scripts/rules-lint.patterns`, `tests/test_rules_lint.py` (add one new test method; do not change `tests/fixtures/rules_lint/` because `test_sources_allow_and_dropped` counts exact hits).
Creates: nothing.
Do not touch `scripts/kaizen-project-report`, `tests/test_project_report.py` (run it as a regression), `skills/`, `README.md`, `CHANGELOG.md`.

## Steps and behaviour

1. Alias normalisation independent of the ladder. Replace the ladder-only match: lower-case the label, and when it is not itself a known name, replace it by the single known name found among its `-` or `:` separated segments (`gpt-6.1-terra` becomes `terra`). Known names are the ladder's models plus a module constant of the built-in names `haiku`, `sonnet`, `opus`, `terra`, `sol`. A label with no known segment, or with two different known segments, stays as written. Use the same function for groups, escalation labels and `dispatch_models` histories.
2. Unknown models. A row whose model, after normalisation, is `unknown` stays in its group, and the result gains `unknown_models`: `{"count": n, "ids": [packet ids]}` over the selected rows.
3. Evidence coverage over the selected rows: result key `data_coverage` = `{"rows": n, "tokens_in": {"known": k, "zero": z, "missing": m, "zero_ids": [...], "missing_ids": [...]}, "tokens_out": {"known", "missing", "missing_ids"}, "cost": {"known", "missing", "missing_ids"}}`. `tokens_in`: a non-bool number above 0 is known; exactly 0 is `zero` (ambiguous: some writers log 0 when they cannot measure); absent, null or invalid is missing. `tokens_out`: a non-bool number at or above 0 is known. `cost`: optional non-bool number at or above 0 (API-equivalent dollars) or null; never estimated from tokens. Provide one helper that returns these states per row; packet 08 reuses it.
4. Landed with failing checks: result key `landed_failing` = `{"count": n, "ids": [...]}` for selected rows with a non-empty string `merge_sha` and `status` equal to `CHECKS FAILING`.
5. Text output: add a section `Data quality` before `Calibration proposals` showing unknown-model count and ids, the three coverage lines (counts, ids bounded to 10 then `... K more`) and the landed-failing ids; with nothing to report each line says `none`. Markdown output uses the same lines.
6. Docs: `docs/outcome-log.md` adds the optional `cost` row and states that `tokens_in` of 0 is treated as ambiguous; the script docstring and `scripts/README.md` list the new keys, say they follow `--since`/`--until` filtering, and replace the :545 sentence with the new alias rule.
7. Stale wording: add a pattern for `Names are normalised against the calibration ladder` to `scripts/rules-lint.patterns` (comment line above it, in the style of the existing entries), a new test method in `tests/test_rules_lint.py` that writes that sentence into a temp repo `CLAUDE.md` and expects one hit, and run `rg -n "normalised against the calibration ladder" --glob '!docs/plans/**'` to confirm no other hit remains.
8. Update the key-set assertion at `tests/test_packet_report.py:24` for `unknown_models`, `data_coverage`, `landed_failing`.

## Acceptance criteria

1. `gpt-6.1-terra`, `gpt-6.2-sol`, `claude-sonnet-4-5` (ladder with only `terra`/`sol`/`sonnet`) group under `terra`, `sol`, `sonnet`; under a different `--ladder` the same labels normalise identically; a label with no known segment stays unchanged; escalation labels and dispatch histories use the normalised names.
2. `unknown_models` counts and lists ids; a literal `unknown` row still contributes to its group.
3. `data_coverage` distinguishes 0 from null from absent for `tokens_in`; malformed token or cost values (string, bool, negative) count as missing without dropping the row; totals are never computed from zero as if it were data.
4. `landed_failing` lists only rows with `merge_sha` and `CHECKS FAILING`; a row with that status and no `merge_sha`, and a `DONE` row with a `merge_sha`, are excluded.
5. All new keys honour `--since` and `--until`; legacy fixtures give identical old keys and values; text and JSON both render; text has the `Data quality` section before `Calibration proposals`.
6. `python3 -m unittest discover -s tests -p 'test_project_report.py'` still passes (the split on `Calibration proposals` still works).
7. The `docs/outcome-log.md`, docstring and `scripts/README.md` text match the behaviour; the stale-wording test passes and `rg` finds no remaining old sentence.

## Verification

```sh
python3 -m unittest discover -s tests -p 'test_packet_report.py' -v
scripts/packet-report --help
scripts/packet-report --packets tests/fixtures/packets.jsonl --json | python3 -c 'import json,sys; d=json.load(sys.stdin); print(sorted(d))'
for m in test_project_report test_rules_lint test_repo; do python3 -m unittest discover -s tests -p "$m.py"; done
rg -n "normalised against the calibration ladder" --glob '!docs/plans/**'
```

## Reporting

At most 20 lines: files changed, test results, the printed key list, limitations, one proposed CHANGELOG bullet (do not edit CHANGELOG.md). Do not commit or push. Stop and report if `normalize_model` or `read_rows` differ from the lines above. If the packet exceeds about 400 changed lines, stop and report.

## Suggested agent / model / effort and risk

`codex-engineer` / Terra medium. Risk: **normal**. Estimated size: 350 lines. Batch reviewer regression modules: `test_packet_report`, `test_project_report`, `test_rules_lint`.
