# P24 Run eligible scheduled friction actions outside Claude's tool grants

## Goal

Run eligible scheduled friction actions outside Claude's tool grants. This packet is part of the Agent Kaizen friction port for 0.13.0.

- **Agent / model / effort** — `codex-dispatch` (`codex-engineer` fallback), sol, high.
- **Risk** — high. Get a per-packet verifier and Sol high review before merge. Obtain security review before landing.
- **Group / dependencies** — L. After P12b, P18b, P19, P23, P24b.
- **Size target** — ~395 changed lines including focused tests.
Sol reason: The broker must make one recoverable effect across interruption without broadening Claude grants.
- Changelog: Run eligible scheduled friction actions outside Claude's tool grants.

Owner decisions O1–O2 apply to the two corresponding broker operations. Other operations can be implemented and tested independently.

## Context

`scripts/kaizen-scheduled:139–156,989–1057,1187–1220` pins permissions, `:1650–1876,1940–2048` handles recovery and the commit point. `tests/test_runner.py:1093–1245` pins the complete sandbox flags. P23 supplies the in-memory frozen allow map and a guarded success branch. P12b, P15b/P19 and P18b provide independently validating tools. P24a and P24b supply budget proof and scoped ledger/undo. P00 owns the sole `scripts/kaizen-link` mapping; verify it, with no late registration edit.

Use the 0.12.0 integration base for landing. The references above are from 0.11.0 main at d8a4cb7. Read `AGENTS.md` and `CLAUDE.md`. Locate symbols with `tools/codemap` if available, otherwise `rg -n` and narrow `sed` ranges. All runtime changes support Python 3.9 and stdlib only. Use `python3`. Keep hard stops, captured user changes, zero-token collection and public-repo privacy; keep real logs and fixtures private.

## Scope and archive references

Owned files: `scripts/kaizen-scheduled`, `scripts/kaizen_friction_apply.py`, `tests/test_friction_apply.py`. Record the changelog line in `docs/plans/2026-11-17-friction-port/changelog/P24.md`. Keep the scoped diff and tests within the assigned cap. Changes outside these paths need a separate packet or a revised scope.

Read `git show wt/p08b:scripts/kaizen-scheduled` at `review_command` and the install assertions in `git show wt/p08b:tests/test_runner.py`. Reuse the explicit operation inventory and installed path tests. Replace the archived `Bash(python3 <script>:*)` grants with trusted runner calls. Inspect archive paths with `git show` and keep the current branch.

## Implementation and acceptance

1. Enable the runner-only broker after safe review/rollback/ledger success, with strict scope, config, host, status and live revalidation. Reconcile existing journals before any new action. Place private journals and trusted bindings under the existing denied backup root; refuse if the model could write that namespace through the effective tool grants. Use fixed bounded subprocess argv and deadlines. Marker (Linux or O2-proven macOS), O1 exact fixed rule, and eligible clean merged worktree are the only effects in this packet. Leave Claude grants byte-for-byte unchanged.
2. After validating the one v1 action fragment, durably import the pending intent, then persist immutable operation identity and budget reservation, then execute. Use a generation-independent per-action transaction key for the tool-owned pending/effect record. Persist the verified effect as pending bookkeeping, write and verify one applied ledger row by action ID, mark the action terminal, then acknowledge. A permanent verified no-effect refusal can become terminal with a reason; unknown budget, temporary refusal, failure or ambiguous state stays pending. The verified terminal set for the generation is the only path to acknowledge.
3. On interruption after import, retain the receipt even if no journal exists. Open imported actions do not suppress a guarded retry. Test crashes after the effect before the ledger row and after the verified row before terminal: recover from the tool-owned operation identity and pending bookkeeping without repeating the effect or duplicating the row, then mark terminal and acknowledge only after verification. If a journal proves no effect, retry only from a fresh successful review and valid scope/budget. Assert zero ack and no writes on timeout, takeover, invalid config, mismatched target, unbacked model write or malformed request.
4. P24b already added `kaizen_friction_apply.py` to `install-schedule`’s `MANAGED_NAMES` using P00’s identity mapping. Test actual `install-schedule --apply` in a disposable cached-copy fixture and exercise the copied broker/undo path. Obtain security review before landing.

## Verification

- `python3 -m unittest discover -s tests -p 'test_friction_apply.py'`
- `python3 -m unittest discover -s tests -p 'test_runner.py'`
- `python3 -m unittest discover -s tests -p 'test_schedule_security.py'`
- `python3 -m unittest discover -s tests -p 'test_schedule_robustness.py'`
- `python3 -m unittest discover -s tests -p 'test_kaizen_link.py'`
- `python3 -m unittest discover -s tests -p 'test_schedule.py'`
- `tools/ci-local --python 3.9`

## Report

Report changed files and line counts, exact checks and outcomes, known uncertainty and any blocked verification. Label measurements with baseline/conditions. Redact paths and identifiers from shared output. Leave plugin version and release CHANGELOG to P27. Do not commit or push.

## Delta (BF13b residual, batch review 6 finding 2)

Before any prepared candidate can drive a scheduled action, bind the report to its extract at initial preparation: `scripts/token-audit` records the SHA-256 of each friction extract it writes (and its size) in the report's friction block; `scripts/kaizen_friction_prepare.py` reads the extract through the existing safe-open path, recomputes the digest and refuses (with a recorded reason) on mismatch or absence. The later receipt check already detects swaps after preparation (`test_swapped_extract_after_receipt_is_refused`). Add a test that swaps the extract between audit and first preparation and asserts refusal. Add `scripts/token-audit` to this packet's owned files for that change only (P18d lands first).

## Delta after P24b, BF15a and BF15b landed (2026-11-18)

Build on what landed; do not duplicate or rework it.

- P24b (merge 6114fab) already provides authenticated broker receipts, idempotent action-ledger recovery, scoped undo, and binding to P18d's generation-bound broker IDs. The native ID is fsync'd in the pending intent before the native effect. Receipt binding is derived from signed evidence, never supplied by the caller. Displaced ledger bytes are never deleted: they are kept under a recorded path and reported. Helpers launch with `python3 -I` from outside the checkout, with state paths resolved before chdir. Reuse these mechanisms. Do not reintroduce caller-supplied bindings, unbound IDs or deletion of displaced bytes.
- S2 stays closed for 0.13.0: the allow-rule operation remains proposal-only. P24 must not enable allow-rule settings writes. Any S2-only hardening belongs to P18e (`briefs/18e-*.md`, items 1–7), not here.
- BF15b (merge 9fc83c5) added the host-probe refresh, the lock-time policy/receipt/generation recheck before import, and publish-before-acknowledge in `scripts/kaizen-scheduled`. Keep them, and run P24's broker only after that import path succeeds.
- The BF13b digest-binding change described above (token-audit records extract SHA-256 and size, prepare recomputes and refuses on mismatch) is still P24's to do if `scripts/token-audit` and `scripts/kaizen_friction_prepare.py` don't already have it: check first with `rg -n "sha256|digest" scripts/token-audit scripts/kaizen_friction_prepare.py`. For this change only, P24 may edit those two files plus `tests/test_friction_prepare.py`.
- Line references above are stale. Find code by function name.
- Also run `python3 -m unittest discover -s tests -p 'test_friction_review.py'` and `python3 -m unittest discover -s tests -p 'test_allow_rule.py'`.
