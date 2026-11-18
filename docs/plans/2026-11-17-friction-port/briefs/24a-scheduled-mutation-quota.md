# P24a Prove the scheduled mutation budget from runner-owned evidence

## Goal

Prove the scheduled mutation budget from runner-owned evidence. This packet is part of the Agent Kaizen friction port for 0.13.0.

- **Agent / model / effort** — `codex-dispatch` (`codex-engineer` fallback), sol, high.
- **Risk** — high. Get a per-packet verifier and Sol high review before merge. Obtain security review before landing.
- **Group / dependencies** — G. After P02, P08.
- **Size target** — ~395 changed lines including focused tests.
Sol reason: Independent tool accounting and trusted config decide whether any scheduled mutation is permitted.
- Changelog: Prove the scheduled mutation budget from runner-owned evidence.

Owner decisions O1–O2 apply to the two corresponding broker operations. Other operations can be implemented and tested independently.

## Context

`scripts/kaizen-scheduled:139–156,989–1057,1187–1220` pins permissions, `:1650–1876,1940–2048` handles recovery and the commit point. `tests/test_runner.py:1093–1245` pins the complete sandbox flags. P16 has already landed the shared ledger proof fixture; P23 later supplies the in-memory frozen allow map and a guarded success branch. P12, P15/P19 and P18 provide independently validating tools.

Use the 0.12.0 integration base for landing. The references above are from 0.11.0 main at d8a4cb7. Read `AGENTS.md` and `CLAUDE.md`. Locate symbols with `tools/codemap` if available, otherwise `rg -n` and narrow `sed` ranges. All runtime changes support Python 3.9 and stdlib only. Use `python3`. Keep hard stops, captured user changes, zero-token collection and public-repo privacy; keep real logs and fixtures private.

## Scope and archive references

Owned files: `scripts/kaizen-scheduled`, `scripts/kaizen_friction_apply.py`, `tests/test_friction_apply.py`, `tests/test_runner.py`, `tests/test_config_keys.py`. Record the changelog line in `docs/plans/2026-11-17-friction-port/changelog/P24a.md`. Keep the scoped diff and tests within the assigned cap. Changes outside these paths need a separate packet or a revised scope.

Read `git show wt/p08b:scripts/kaizen-scheduled` at `review_command` and the install assertions in `git show wt/p08b:tests/test_runner.py`. Reuse the explicit operation inventory and installed path tests. Replace the archived `Bash(python3 <script>:*)` grants with trusted runner calls. Inspect archive paths with `git show` and keep the current branch.

## Implementation and acceptance

The v1 `ledger_attestation` in the scheduled-baseline JSON is null (no ledger exception) or an exact object: `v` integer 1; `run_id`, `session_id` strings; `ledger_relpath` string exactly `docs/kaizen/LEDGER.md`; `before_b64` base64 of bounded pre-launch bytes; `before_sha256`, `after_sha256` lowercase 64-hex SHA-256 strings; `manifest_ids` array of distinct nonempty strings. Reject duplicate/unknown fields, invalid types, encoding or bounds. P24a derives this from protected runner state, P25 passes it unchanged on fixed private stdin, and P16 rechecks matching IDs, canonical non-symlink scope, unstaged-only status, both hashes against decoded pre-launch and live bytes, unchanged byte prefix, valid appended rows and exact independently verified finished current-run manifests. Reject mismatches; the ledger is excluded from the commit. Hashes alone do not authenticate the source.

1. Add typed `maxChangesPerRun` to the existing schema, default 3, strict integer ≥0, enrolled project overriding global. Zero disables broker writes. Bound reads, validate canonical nonsymlink config file identity and freeze trusted sources before launch and refuse changed/malformed/unreadable sources, boolean/string/negative values or a project scope mismatch. Reject duplicates in trust inputs; do not reuse permissive render-time fallback as a write authorization. Pin `test_defaults_and_global_reports`, `test_precedence`, `test_set_global_boolean_and_multiple_settings`, `test_set_project_preserves_other_keys_order_and_format` and `test_keys_and_reports_path` through full runner/config tests.
2. In eligible guarded auto, capture bounded Claude runtime stream envelopes over runner-owned stdout (verified version, matching session and full start/result coverage), not body text or transcripts. Sanitize rendering back to existing review output. Do not change effective allowed/denied tool sets. Only documented runtime records identify tool dispatch/completion. Absent, unknown, malformed, duplicate/conflicting, truncated or incomplete observations make the remaining budget unknown.
3. Correlate Edit/Write calls to the ordered runtime dispatch/completion of the fixed backup helpers and independently validated current-run manifests. Match each begin to the target before its write, and the subsequent finish to the exact new folder and current after-hash. Charge each distinct dispatched write or any additional verified effect at least one, avoid double charge of the same write's manifest, exempt only verified notes-ledger adds and a project Markdown ledger append that preserves prior rows and adds valid rows referencing those exact finished manifests (take the pre-launch ledger snapshot), and reserve one slot durably per broker attempt in P24. An unbacked write, unknown target, unsupported event or uncovered effect means no broker allowance, including an edit later restored. Include actual attempted calls in tests; successful empty output/zero manifests alone is insufficient proof. Prove zero-write, ordinary backed-up, exhausted, unbacked and incomplete-stream cases before enabling any broker. Verify on the installed Claude version that stdout `--output-format stream-json` and any required transport verbosity deliver all supported tool lifecycle records, distinct from nested model text. Test real backed/unbacked writes, reflected fake envelopes and truncation; unsupported versions leave broker writes disabled. Keep the adapter dormant until P24 integrates it.
4. Produce the exact ledger attestation defined in [Approach and contracts](../plan.md#approach-and-contracts), under Shared mutation quota and trusted Git baseline, from protected pre-launch and verified post-review evidence. Consume the P16-owned `tests/fixtures/ledger_attestation_v1.json` unchanged; cover valid and invalid proofs and fail closed on inconsistencies. Obtain security review before landing. Land accounting with broker writes dormant.

## Verification

- `python3 -m unittest discover -s tests -p 'test_friction_apply.py'`
- `python3 -m unittest discover -s tests -p 'test_runner.py'`
- `python3 -m unittest discover -s tests -p 'test_schedule_security.py'`
- `python3 -m unittest discover -s tests -p 'test_schedule_robustness.py'`
- `python3 -m unittest discover -s tests -p 'test_config_keys.py'`
- `python3 -m unittest discover -s tests -p 'test_kaizen_link.py'`
- `tools/ci-local --python 3.9`

## Report

Report changed files and line counts, exact checks and outcomes, known uncertainty and any blocked verification. Label measurements with baseline/conditions. Redact paths and identifiers from shared output. Leave plugin version and release CHANGELOG to P27. Do not commit or push.
