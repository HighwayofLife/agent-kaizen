# Friction port for Agent Kaizen 0.13.0

## Summary

Port the useful parts of the unlanded 0.6.0 friction work onto the 0.12.0 integration base. Keep collection deterministic and local. Claude and Codex observations feed the existing audit scan, then the runner prepares a bounded view for the friction skill. Action tools re-derive eligibility from live state. Scheduled actions run in the runner after a successful scoped review and its existing guards. General Claude Bash permissions stay as they are in 0.12.0.

Planning base is main at `d8a4cb7` (0.11.0). The local `multi-host` tip is `18ababd`. Its P02 sidecar and P01 installer probe are present; its remaining 0.12.0 behavior is read from the branch plan and verified on the merged base before use. The older branches are review material, all based on `599810c`, and their archived tips are `archive/friction-0.6/<name>`. The complete/partial status describes the 2026-11-17 read-only review, not a clean current test run. Reuse focused code and regression cases by revision. A stacked cherry-pick would replace newer scanner, runner and permission behavior. [Code map](context.md)

## Goal and scope

- Quantify tool latency, waits and contention without a second transcript pass or model collection. Preserve cost/usage accounting, format canaries, scheduled cadence, and the existing context budget.
- Prepare ranked, evidence-backed friction candidates and machine-local action tracking. Offer reversible host and Git operations through code-checked entry points. Keep scheduled hard stops, non-Claude configuration proposals, undo and recovery intact.
- The release does not add a scheduler job, background daemon, Python dependency, Copilot usage parser, native non-Claude permission editing, remote Git action, root-only fix or model transcript reads.

## Verdicts

| Original feature | Verdict | Reason on current main | Packets |
|---|---|---|---|
| p01 Claude tool timing and friction extract | Port | Current Claude scan already pairs tool rows and writes the same v1 sidecar. Adapt the reviewed timing, signal and redact logic alongside the canary. | P03, P05, P23 |
| p02 Catalogue | Port | No equivalent catalogue exists. The reviewed data and validation can be reused without replacing code. | P01, P01b |
| p03 Config keys | Port | Current typed schema, settings lock, and defaults support these with one project-only validator. Tests pin the exact output. | P02, P24a |
| p04 Codex timeline and contention | Rewrite | Current Codex scan gates a single byte-filtered traversal and tracks format/usage separately. Reuse the bounded parser and timeline algorithm, rebuild admission and pairing at current seams. | P09, P13 |
| p05 Host probe | Port | Doctor checks correctness and installation, while the probe measures host conditions and directories. Retain passive checks and reuse shared Git facts for topology. | P06, P10 |
| p06 Host-action store | Port | Current project state and atomic writes fit a machine-local store. Keep the reviewed schema and transitions, with authenticated scope from prepared evidence and serialized writes. | P07, P11, P20b |
| p07 Sampler | Port | Bash-burst emits synchronous nudges on successes/failures and prompt submits. Add a separate silent async sampler registration and use current retention. Replace the archived race-prone append/claim implementation. | P14, P14b, P14c, P17 |
| p08a Runner wiring | Rewrite | Current runner owns ledger guard, active marker, process-group timeout and usage DB. Prepare and reconcile around those existing points. | P20, P20b, P23 |
| p08b Scheduled permission/installation | Rewrite | Current runner has an empty general Bash allowlist and pins scoped grants. Use a post-review broker and the current managed installer, replacing archived wildcard script grants and copying logic. The archived packet was partial. | P00, P21, P24a, P24b, P24 |
| p09 Host-action notice | Merge into existing feature | Startup notice already resolves projects and emits multiple daily notices with atomic markers. Add one count through its host-aware output. | P22 |
| p10 Friction skill | Rewrite | Current cycle has new review, checks, safety and ledger paths. Keep the staged flow, integrate prepared data and broker requests, and drop stale host/CLI assumptions in the archived partial text. | P26 |
| p12 Host fix and undo | Rewrite | Current runner denies direct host writes and undo validates backup paths. Preserve the two catalogue operations behind fresh path checks and private, retryable records. | P15, P15b, P19, P24 |
| p13 Exact allow rule | Rewrite | Current schedule removes broad Bash read access and denies settings writes. The archived `Bash(head:*)` is a prefix grant. Require proven literal Claude rules, positive evidence and a closed vocabulary. | P05, P18, P18b, P24 |
| p14 Worktree removal | Merge into existing feature | Dispatch status already discovers linked trees but intentionally hides `out` dirt. Merge facts there and share strict facts with a separate transactional `worktree-prune` mutation CLI. | P04, P12, P12b, P24 |
| p15 Local backup commit | Port | Current backup has stronger hashes, credential guards and interrupted-run recovery. Port the reviewed temporary-index/ref algebra onto it and use trusted runner mediation for scheduled commits. | P08, P16, P16b, P25 |

## Approach and contracts

### Collection, policy and installed names

One deterministic scan produces v1 usage plus an optional v1 `friction` object. Base flags are `{id,subject,detail,value,catalog_id?}` with finite numeric value and a measured, estimated or unconfirmed basis supplied by the cohort. Extracts remain machine-local under `<audits>/extracts` or explicit `--extract-out`. Unknown fields/version degrade to unavailable. Default on. `--no-friction` or effective friction off preserves old usage output and skips the extra work. Scheduled global `audit` and `auto-audit` use global effective config, and scoped scheduled review uses project precedence (P03/P23). Ordinary interactive cycle independently retains its old report freshness and refresh step, using scoped friction flags; pass the chosen report to preparation and skip only the friction stage if its gate is empty or unavailable (P20/P26).

Keep the current synchronous Bash burst. The silent async sampler observes successful Claude Bash PostToolUse only. Timeouts/failures remain transcript signals. Store bounded IDs and metrics plus allowlisted process basenames under the UTC-day cap and lock; protect the live day from retention. Unsupported host/lifecycle stays inert. Installed CLI extraction median ratio ≤1.10 versus 0.12.0 on the same private inputs, measured separately for on and off. Installed Claude synchronous return path target ≤10 ms added median.

P00 pre-registers the complete fixed `kaizen-link` SCRIPTS map before any source lands. A future absent source produces no installation work. P21 adds command/data source aliases and those dependencies to `install-schedule` MANAGED_NAMES. P20 adds `kaizen_friction_prepare.py` to the inventory when prepare first ships; P24b adds `kaizen_friction_apply.py` when undo first ships. P20b and P24 exercise their commands against those installed modules. For repo and copied installs use the runner's `sibling()` pattern, preferring `kaizen-friction-catalog.json` and falling back to `friction-catalog.json`. Executable consumers try the mapped `kaizen-*` then source spelling, private helpers retain their actual `kaizen_*.py` import basenames. Test copied intake with `install-schedule --apply`, not just bare linker coverage.

### Stable IDs, payload and comparison cohorts

P07 makes one stable ID from the atomically created machine-private key and compact ASCII JSON `[1, canonical_project, catalog_id, selector_key]` using ASCII escapes and no whitespace. The ID is `fa1_` followed by 64 lowercase HMAC-SHA256 hex characters over those bytes. Selectors are canonical scoped targets, closed literals/enums or existing redacted signal keys. Scope is the canonical enrolled project. Store target, scope and provenance privately. Keep the key, private preparation receipts and effect authority in a dedicated backup-root namespace covered by the existing backup denies. If run permissions would allow writing it or private identity cannot be verified, fail closed. A scheduled local-commit candidate uses catalogue tag `local-commit` and the runner-generated run ID as selector, and is available only when another friction signal opens the gate and the pre-launch baseline qualifies. Neither publish nor accept a model-provided target, path or Git argument.

The action wire format is one whole line `<!-- kaizen-host-actions {"v":1,"actions":[{"id":"fa1_<64 lowercase hex>","intent":"suggest"}]} -->`. At most 8 KiB including delimiters and 16 distinct IDs. Accept exactly the shown keys/types, no duplicate keys or IDs, and `suggest` or `apply` as the literal intents. A valid empty array explicitly reports no action. Known IDs and allowed intents come from the exact runner-retained map and effective mode. Only the post-review auto broker can execute scheduled apply; interactive import accepts suggestions, with direct effects remaining under their own approved tool workflow. P11 owns the shared parser/upsert and P20b lands the interactive entry point alongside re-derivation. Treat proposal prose and user-supplied model views as data.

P20 produces a redacted `friction-inputs-*.json` view and private receipt containing canonical scope, strictly ordered generation, bound report/extract/probe digests and policy with an allowed-ID map. Interactive P20b re-derives that exact current map before import. Compare saved positive finite numeric buckets `floor(log2(value))` by `(canonical scope, window definition, ordered threshold vector, timing basis, id, subject)`. Rolling windows require identical cutoff policy and lookback width, while fixed windows match exact UTC cutoff. Sliding a same-width rolling window is comparable. Disregard legacy keys lacking comparison fields. A missing prior cohort or a higher bucket opens the gate; maintain maxima within each cohort across switch-back. Reject stale, empty or out-of-order ack and store acknowledgement only after durable reconciliation. Unchanged suggestions, dismissed, flapped or already terminal actions do not open a gate; a still-valid imported pending action remains eligible for fresh review.

### Scheduled transaction and recovery

Keep existing Claude Bash, Edit/Write and deny snapshots; model output and all evidence are untrusted data. Require a successful scoped auto review, group exit, completed rollback and ledger guards, current settings/policy, strict scope, bounded fixed argv and live tool revalidation for any new effect. Explicit propose-only wins. Under the existing run/backup lease and scoped writer lock, use this order:

1. **Import.** Parse and validate the v1 block against the frozen map. Atomically persist generation-bound receipt plus action upserts and pending `apply` intent. Strip machine block from rendered prose. Missing or malformed block cannot consume friction work. Suggestions are terminal for the receipt and stay open for the user where applicable.
2. **Journal.** Before executing, persist stable action ID as transaction key, the generation, checked scope, fixed operation, expected precondition, and one durable budget reservation. A crash after import but before journal leaves a retriable open action. Before a new attempt revalidate it through a fresh guarded review, never replay model output or reuse a stale budget. One unresolved operation per action ID. Keep generation receipts long enough for recovery.
3. **Execute and verify.** Native helpers use the private action-ID transaction key in their pending and terminal records. Reconcile unfinished effects by checking tool-owned record and live identity. Recovery can observe/finalize known effects and bookkeeping without starting a new mutation. No duplicate effect after interruption. A verified permanent no-effect refusal is terminal with reason. Temporary failure, unknown effect or budget, or policy preventing current authorization remains pending for retry or explicit disposition. Unresolved recovery blocks new effects on the affected scope. Automatic apply is terminal for that action ID once successfully reverted. Reopen can return it for human follow-up, with no repeat unattended effect.
4. **Record and acknowledge.** Persist the verified effect as pending bookkeeping, write and verify its ledger row, mark the action terminal, then acknowledge. Only when every imported request for that exact generation is terminal may its successful reconciliation advance comparison fingerprints. Suggest-only/nothing requested can ack after a valid import. Failed review, interrupted or malformed import, unverified effect and failed bookkeeping cannot advance fingerprints.

P20 installs preparation; P23 wires scheduled preparation and imports. Until P24 lands, it may acknowledge only suggestion-only generations. P24a adds observation/accounting before writes are possible, P24b adds bookkeeping and scoped reversal, P24 assembles the transaction and P25 attaches the commit operation.

### Shared mutation quota and trusted Git baseline

P24a types `maxChangesPerRun` in the existing global/project schema. Resolve global then enrolled canonical project, default 3, integer ≥0, zero disables broker writes. Freeze trusted config pre-launch and recheck source/content before effects. Invalid, unreadable, duplicate or changed controlling config yields no broker allowance. Never trust a model-reported limit or a permissive config fallback. Keep ordinary review usable.

Prove remaining slots from complete, bounded host-generated runtime tool envelopes on a runner-owned stdout stream on a verified Claude version (S7). Bind start, tool calls/results and final envelope to the runner's session. Tool identity and its call arguments come from the runtime envelope. No inner model/tool-result body text, transcript or proposal can count as testimony. Correlate each dispatched Edit/Write with a fresh matching manifest whose begin preceded it, whose verified finish followed it and whose current after-hash matches. Charge at least one per dispatched write and any independently verified additional effect, counting a manifest of the same write only once. Allow only evidenced existing bookkeeping without change charge: authenticated notes-ledger add and a project ledger append whose before/after proves untouched prior rows and only new valid rows for exact finished manifests. Unmanifested writes (including restored writes), missing/ambiguous records, unexpected tools, incomplete/oversize stream, path mismatch or unresolved recovery leave zero broker allowance. Reserve one slot for every broker attempt before effect, including commit, and never refund an attempted effect in that run. The preflight and post-review limit apply to all broker operations. Unsupported stream versions stay proposal-only for broker effects.

P08 provides reusable strict clean Git capture. P25 invokes it before model launch and freezes canonical top level, Git common-dir identity, initial HEAD, index/clean stamp, runner-generated run/session IDs, start timestamp and pre-existing backup-folder identities in runner-owned state. Claude inherits the existing `KAIZEN_RUN_ID` and `KAIZEN_SESSION_ID` only. An ordinary scheduled `kaizen-backup begin --skill … --ledger … FILE` / Edit / finish writes normal manifests, with no `--repo` or authority from a model-provided stamp. P25 consumes at most one verified new mutation-bearing manifest from that exact run/session and rejects ambiguous groups, hashes, scope, missing coverage, or stale/foreign files. P16 gets a v1 JSON tuple of that immutable baseline and exact authorized folder identity via stdin to fixed `kaizen-backup commit --scheduled-baseline-stdin CHANGE_DIR` after Claude exits. It rechecks new folder identity, time, finish, current hashes, live status, scope, HEAD and index. The only status exception is the exact eligible unstaged project ledger append whose before/after proof and hash came from P24a. It cannot authorize other paths. The ledger stays out of the commit. Process this ref effect before other new broker effects in that run. The helper builds the commit from verified bytes with private index/local ref CAS. The private method never falls back to a manifest Git stamp. The ordinary interactive opt-in `begin --repo`, file rollback and legacy manifests remain compatible. No checkout or push. P16b journals ref update and inverse CAS, and P25 journals the broker phase before invoking it.

The v1 scheduled-baseline JSON tuple has `ledger_attestation` (object or null). Null permits no ledger status exception. An object has exactly `v` (integer 1), `run_id` and `session_id` (strings matching the runner baseline), `ledger_relpath` (string, exactly `docs/kaizen/LEDGER.md`), `before_b64` (base64 string of the exact bounded pre-launch ledger bytes), `before_sha256` and `after_sha256` (64 lowercase hex SHA-256 strings), and `manifest_ids` (array of distinct nonempty strings identifying the exact finished current-run manifests referenced by appended rows). Reject unknown/duplicate keys, wrong types, invalid encoding, over-limit data, and absent or inconsistent proof. P24a produces it from protected runner state; P25 passes it unchanged over the private fixed stdin handoff, never from model output. P16 independently checks baseline IDs, canonical non-symlink ledger scope and unstaged-only status, hashes decoded before bytes and live after bytes, verifies byte-for-byte unchanged prefix and parses only valid appended rows tied exactly to independently verified finished manifests. A digest alone is not authentication; runner ownership and the fixed handoff establish provenance, and every check is repeated at use. Reject on any mismatch; do not commit the ledger. P16 owns `tests/fixtures/ledger_attestation_v1.json` with synthetic valid and invalid cases; P16, P24a and P25 all consume this same fixture without modifying it later.

### Applied ledger row and accepted-permission evidence

P24b owns `docs/kaizen/LEDGER.md` bookkeeping for post-model effects. Copy the eight-column `skills/start/SKILL.md` format: date, change with exactly one `[action:fa1_…]` marker, why/catalogue signal, expected effect, measured effect `pending`, keep/revert `pending`, fixed same-scope metric command, and ISO review date at most 30 days out. No tool record path, target or reviewer prose in the row. Validate the scoped ledger before a new apply, append and verify under a project lock, and retain private authoritative lookup `action ID → scope, operation, tool record, verification, phase`. Retry missing row after effect or missing terminal state after row without duplicates. Refuse row/record conflicts. `kaizen-scheduled actions undo ID --for DIR` resolves only a verified scoped private record and matching ledger row, calls the fixed validated inverse, then marks the row reverted with date. Reconcile an interruption after undo before marking. P26 routes explicit interactive undo by ID while preserving ordinary backup undo. No scheduled undo or recorded arbitrary command execution.

P05 writes private v1 `permission_acceptance` rows keyed by literal `ls`, `ls -a`, or `ls -l` and opaque canonical `--cwd` member ID, with distinct integer `accepted`, `denied`, and `ambiguous` counters. An accepted count requires an explicit verified host-recorded user permission acceptance and corresponding exact Bash execution from that canonical scope, deduplicated by session/tool-use ID. Textual inference, execution alone, conflicting events and uncertain joins are ineligible. Require ≥10 genuine acceptances within seven days for the same literal and scope, zero denied/ambiguous observations for that pair and live verified runtime exact matching with deny precedence. No pooling across worktrees or commands, global or substring-only evidence. P18/P18b may touch only the canonical project's `.claude/settings.local.json`; the prior permission model and O1 vocabulary are settled. Confirm a fresh scheduled propose-only and auto review still enforce their respective Bash boundaries after a rule persists.

Follow archived D1–D4 with current hard stops. Keep newer settings, agent-definition and protected home instruction denies. D2 retains branches and requires live clean merged worktree facts. D3 uses the validated local-only ref. D4 is limited to O1. Non-Claude configurations remain proposal-only; O2 native Time Machine stays manual until same-target apply/undo proof. Rejected approaches include stacked cherry-picks, a second transcript pass, async Bash-burst, repo-tracked host state or broad scheduled helper grants.

## Decisions needed

Settled by the orchestrator 2026-11-17 (owner delegated: "if they are useful, we should include them"): O1 and O2 take the recommendation below.

| ID | Owner decision | Recommendation and blocking scope |
|---|---|---|
| O1 | Confirm the 0.13.0 exact allow-rule vocabulary. | Start with the three fixed read-only literals `ls`, `ls -a`, `ls -l` in the project's local settings, with at least 10 verified acceptances per literal and scope and live matching proof. This is narrower than the archived head-based list. Keep broader or unverified rules as proposals. Blocks write enablement in P18/P18b/P24 and the permission claim in P27. |
| O2 | If the native Time Machine target cannot be bound safely, confirm the release fallback despite the earlier scheduled-auto approval. | Ship the rest with a manual catalogue action on macOS. Enable fixed sticky no-root mutation only after same-target apply/undo is proven. Blocks only the native Time Machine write path/claim in P19/P24/P27. |

## Assumptions

- Planning proceeds with the recommendations above. Code-independent work can begin from 0.11.0, and every packet is rebased onto 0.12.0 before landing. The first release refuses worktree removal with any observed ignored entries, even known build output. Confirm Git's safety boundary for entries created during the final check before enabling unattended removal. Read-only probe reporting still shows such output.
- 0.12.0 resolves the deployed host adapter and its Copilot fallback before the manifest changes. Copilot usage remains unmeasured. A host with unverified sampler execution produces no samples.
- Auto host fixes stay on for eligible cases in `hostActions=apply`. `suggest` lists actions and `off` suppresses collection of host actions and notices. Per-project `friction=off` skips analysis/preparation for that scope. Disabled global plugin or sampler stops the hook.
- Do not rewrite saved v1 usage extracts or existing backup manifests. Missing new fields keep old behavior. Never install a new timer as part of the port.

## File overlap with 0.12.0

| Files in both plans | 0.12.0 owner | Friction packets and ordering |
|---|---|---|
| `scripts/token-audit` | P06 | P03, P05, P09, P13, P17. P03 waits for P06; the scan packets then build in order. |
| `hooks/audit-notice.sh`, `tests/test_hooks.py` | P05 | P22 waits for the merged host adapter and golden fixtures. |
| `tools/context-budget.json` | P05 | P14c waits for P05; P22 waits for P14c to refresh the notice entry independently. |
| `tools/host-probe`, `tests/test_host_probe.py` | P01, conditional C1 (tool only) | P14c waits for merged discovery logic. Keep strong assertions for existing hooks and document the observed sampler registration. Friction runtime probe tests have a distinct filename. |
| `skills/cycle/SKILL.md`, `skills/review/SKILL.md`, `skills/undo/SKILL.md`, `agents/kaizen-auditor.md` | P04 | P26 starts after merged preambles and visibility design. |
| `docs/autonomy.md`, `docs/hosts.md` | P03 | P26 extends autonomy after P03. P27 extends the new host map after P03. |
| `README.md`, `scripts/README.md`, `docs/scheduling.md` | P06, P07 | P26 owns the required skill table row. P27 updates docs after that and the 0.12.0 text. |
| `.claude-plugin/plugin.json`, `CHANGELOG.md` | P07, P09 | P27 waits for the release version and description changes. |
| `.github/workflows/ci.yml`, `tools/ci-local` | P08 | P27 waits and preserves host probe and PR/tag checks. |
| `.github/plugin/plugin.json` (conditional) | C1 | P27 synchronizes version if this file exists. |

Read the local 0.12.0 contracts with `git show multi-host:docs/plans/2026-11-17-multi-host/plan.md` (76, 105, 110, 122, 146–158, 166, 170), `git show multi-host:tests/test_repo.py` (sidecar), `git show multi-host:hooks/hooks.json` and `git show multi-host:tools/host-probe`. The 0.12.0 P05/P09 plan explicitly pins `hooks/hooks.json` byte-identical to 0.11.0, although the planner brief flags it as a potential overlap. P14c changes it only after that check lands and rechecks conditional `hosts/copilot/hooks.json` behavior without adding sampling there. `hooks/bash-burst.sh`, `hooks/session-audit.sh`, `scripts/kaizen-doctor`, `scripts/kaizen-scan`, `tests/test_repo.py` and `tools/context_budget.py` are read/test dependencies of the friction work. They are owned by the multi-host plan wherever it changes them. If 0.12.0 broadens its file set, re-run an overlap review before dispatch.

## Packets

Packet rows use Haiku high for fixed registration/catalogue changes, Terra medium for routine work and Sol only for the stated reasons. Use `haiku-engineer` for Haiku or `codex-dispatch` (`codex-engineer` fallback) for Terra/Sol. Size counts added and removed lines including focused tests. Split caps are preassigned. Reuse code paths and combine redundant archive cases instead of copying full suites. Each group has at most four active packets, with disjoint owned paths. Complete the group before starting the next. Rebase onto merged 0.12.0 before landing. A conditional capability with missing live proof stays on its documented refusal path.

Installer and proof ownership in the packet table: P16 owns `tests/fixtures/ledger_attestation_v1.json`; P24a and P25 only read it. P20 owns `scripts/install-schedule` for preparation inventory; P20b tests that installed dependency. P23 only reads that inventory. P24b owns `scripts/install-schedule` for undo inventory; P24 only reads it. The affected packets use their existing test files to run copied-install command checks. These owners are in separate groups.

Every brief includes `tools/ci-local --python 3.9` and narrow checks. Only P00 registers new script sources in kaizen-link. Each implementation packet records a changelog fragment. P27 alone owns version and release CHANGELOG, integrating those with the runtime changes before release. Low risk lands on green checks, normal gets batch review, high gets a per-packet verifier and Sol high diff review. The marked entries require explicit security sign-off from a security review before landing. Run a read-only final audit on the integration range before P28.

Reference sizing (source + tests): P01/P01b take 613 + 160 catalogue lines with compact data rows; P12/P12b cover 373 + 589 through smaller shared refusal/recovery fixtures. P14/P14b/P14c divide the expanded worker, sampling/bench tests, registration/probe and retention. The archive measured 59 hook + 5 manifest + 137 hook-test lines before the extra worker, host-probe and retention work. P15/P15b/P19 share 404 + 908 for the marker and optional macOS flows. P08/P16/P16b cover 291 + 756, with baseline capture separated from ref plumbing and recovery. P18/P18b cover 329 + 692, replacing prefix-rule fixtures and consolidating overlapping refusal cases. Keep each planned split near or below 400 lines with its own behavior tests.

| ID and brief | Group | Depends on | Model / effort | Risk | Lines | First narrow check |
|---|---|---|---|---|---:|---|
| [P00 register-scripts](briefs/00-register-scripts.md) | A | — | haiku / high | low | ~95 | `python3 -m unittest discover -s tests -p 'test_kaizen_link.py'` |
| [P01 catalog](briefs/01-catalog.md) | A1 | P00 | haiku / high | low | ~340 | `python3 -m unittest discover -s tests -p 'test_friction_catalog.py'` |
| [P02 config](briefs/02-config.md) | A1 | — | terra / medium | low | ~230 | `python3 -m unittest discover -s tests -p 'test_friction_config.py'` |
| [P03 claude-timing](briefs/03-claude-timing.md) | A1 | — | sol / medium<br>Sol reason: A one-pass scan change must preserve bounded parsing, existing metrics and scan speed. | normal | ~365 | `python3 -m unittest discover -s tests -p 'test_friction_claude.py'` |
| [P04 worktree-facts](briefs/04-worktree-facts.md) | A1 | P00 | terra / medium | normal | ~250 | `python3 -m unittest discover -s tests -p 'test_dispatch_status.py'` |
| [P01b catalog-hardening](briefs/01b-catalog-hardening.md) | B | P01 | haiku / high | low | ~350 | `python3 -m unittest discover -s tests -p 'test_friction_catalog.py'` |
| [P05 claude-signals](briefs/05-claude-signals.md) | B | P03 | terra / medium | normal | ~335 | `python3 -m unittest discover -s tests -p 'test_friction_signals.py'` |
| [P08 backup-start](briefs/08-backup-start.md) | B | — | sol / high<br>Sol reason: The clean-start capture and identity boundary authorize later Git writes. | high<br>security review before landing | ~245 | `python3 -m unittest discover -s tests -p 'test_backup_commit.py'` |
| [P14 sample-writer](briefs/14-sample-writer.md) | B | P00, P02 | sol / high<br>Sol reason: Concurrent writers must preserve private file identity, cap and hook deadline. | high | ~300 | `python3 -m unittest discover -s tests -p 'test_friction_sampler.py'` |
| [P06 host-probe](briefs/06-host-probe.md) | C | P01b, P02 | terra / medium | normal | ~330 | `python3 -m unittest discover -s tests -p 'test_friction_host_probe.py'` |
| [P07 actions-store](briefs/07-actions-store.md) | C | P01b, P02 | sol / high<br>Sol reason: Stable scoped IDs and concurrent private-store writes are the action trust boundary. | high | ~350 | `python3 -m unittest discover -s tests -p 'test_host_actions.py'` |
| [P09 codex-pairing](briefs/09-codex-pairing.md) | C | P03 | sol / medium<br>Sol reason: Codex call/output admission shares the single-pass format and accounting fast path. | normal | ~340 | `python3 -m unittest discover -s tests -p 'test_friction_codex.py'` |
| [P12 worktree-prune](briefs/12-worktree-prune.md) | C | P04 | sol / high<br>Sol reason: Clean, merged worktree preflight must refuse hidden changes and unsafe topology. | high<br>security review before landing | ~360 | `python3 -m unittest discover -s tests -p 'test_worktree_prune.py'` |
| [P10 project-probe](briefs/10-project-probe.md) | D | P04, P06 | terra / medium | normal | ~340 | `python3 -m unittest discover -s tests -p 'test_friction_host_probe.py'` |
| [P11 actions-reconcile](briefs/11-actions-reconcile.md) | D | P05, P07 | sol / high<br>Sol reason: Strict wire validation and an atomic import receipt are required for retry after interruption. | high | ~375 | `python3 -m unittest discover -s tests -p 'test_host_actions.py'` |
| [P13 timeline](briefs/13-timeline.md) | D | P05, P09 | terra / medium | normal | ~320 | `python3 -m unittest discover -s tests -p 'test_friction_timeline.py'` |
| [P14b sample-process-hardening](briefs/14b-sample-process-hardening.md) | D | P01b, P14 | sol / high<br>Sol reason: Rate claims across concurrent hooks and process teardown must preserve the sampling deadline. | high | ~255 | `python3 -m unittest discover -s tests -p 'test_friction_sampler.py'` |
| [P12b worktree-prune-recovery](briefs/12b-worktree-prune-recovery.md) | E | P12 | sol / high<br>Sol reason: Recovery and compare-before-remove must handle late writes and forged records. | high<br>security review before landing | ~385 | `python3 -m unittest discover -s tests -p 'test_worktree_prune.py'` |
| [P15 host-marker](briefs/15-host-marker.md) | E | P10, P11 | sol / high<br>Sol reason: No-follow directory operations and path revalidation protect the marker target. | high<br>security review before landing | ~370 | `python3 -m unittest discover -s tests -p 'test_host_fix.py'` |
| [P16 backup-commit](briefs/16-backup-commit.md)<br>owns `tests/fixtures/ledger_attestation_v1.json` | E | P08 | sol / high<br>Sol reason: Trusted handoff and Git plumbing must preserve the worktree and user index. | high<br>security review before landing | ~365 | `python3 -m unittest discover -s tests -p 'test_backup_commit.py'` |
| [P18 allow-rule](briefs/18-allow-rule.md) | E | P05 | sol / high<br>Sol reason: Persistent permissions require live exact matching and user acceptance provenance. | high<br>security review before landing | ~380 | `python3 -m unittest discover -s tests -p 'test_allow_rule.py'` |
| [P14c sample-registration](briefs/14c-sample-registration.md) | F | P14b | terra / medium | normal | ~390 | `python3 -m unittest discover -s tests -p 'test_friction_sampler.py'` |
| [P15b host-marker-recovery](briefs/15b-host-marker-recovery.md) | F | P15 | sol / high<br>Sol reason: Marker apply/undo must recover safely around partial effects and replacement. | high<br>security review before landing | ~390 | `python3 -m unittest discover -s tests -p 'test_host_fix.py'` |
| [P16b backup-commit-recovery](briefs/16b-backup-commit-recovery.md) | F | P16 | sol / high<br>Sol reason: Ref compare-and-swap and interrupted reversal must recover without duplicate commits. | high<br>security review before landing | ~390 | `python3 -m unittest discover -s tests -p 'test_backup_commit.py'` |
| [P18b allow-rule-recovery](briefs/18b-allow-rule-recovery.md) | F | P18 | sol / high<br>Sol reason: Locked settings transactions and ownership-preserving undo change persistent permissions. | high<br>security review before landing | ~390 | `python3 -m unittest discover -s tests -p 'test_allow_rule.py'` |
| [P17 sample-join](briefs/17-sample-join.md) | G | P13, P14c | terra / medium | normal | ~350 | `python3 -m unittest discover -s tests -p 'test_friction_samples.py'` |
| [P19 time-machine](briefs/19-time-machine.md) | G | P15b | sol / high<br>Sol reason: The native path-based operation must stay bound to one eligible directory through apply and undo. | high<br>security review before landing | ~365 | `python3 -m unittest discover -s tests -p 'test_host_fix.py'` |
| [P21 install](briefs/21-install.md) | G | P10, P11, P12b, P15b, P18b | terra / medium | normal | ~290 | `python3 -m unittest discover -s tests -p 'test_kaizen_link.py'` |
| [P24a scheduled-mutation-quota](briefs/24a-scheduled-mutation-quota.md) | G | P02, P08, P16 | sol / high<br>Sol reason: Independent tool accounting and trusted config decide whether any scheduled mutation is permitted. | high<br>security review before landing | ~395 | `python3 -m unittest discover -s tests -p 'test_friction_apply.py'` |
| [P20 prepare](briefs/20-prepare.md)<br>owns `scripts/install-schedule` | H | P10, P11, P17, P24a | terra / medium | normal | ~380 | `python3 -m unittest discover -s tests -p 'test_friction_prepare.py'` |
| [P22 notice](briefs/22-notice.md) | H | P11, P14c | terra / medium | normal | ~240 | `python3 -m unittest discover -s tests -p 'test_hooks.py'` |
| [P20b interactive-friction-import](briefs/20b-interactive-friction-import.md)<br>tests copied-install import | I | P20 | terra / medium | normal | ~335 | `python3 -m unittest discover -s tests -p 'test_friction_prepare.py'` |
| [P23 review-wiring](briefs/23-review-wiring.md)<br>reads installer inventory | J | P20b, P21 | terra / medium | normal | ~375 | `python3 -m unittest discover -s tests -p 'test_friction_review.py'` |
| [P24b action-ledger-undo](briefs/24b-action-ledger-undo.md)<br>owns `scripts/install-schedule` | K | P24a, P23 | sol / high<br>Sol reason: Ledger recovery and fixed undo lookup must never adopt forged state. | high<br>security review before landing | ~365 | `python3 -m unittest discover -s tests -p 'test_friction_apply.py'` |
| [P24 scheduled-actions](briefs/24-scheduled-actions.md)<br>reads installer inventory | L | P12b, P18b, P19, P23, P24b | sol / high<br>Sol reason: The broker must make one recoverable effect across interruption without broadening Claude grants. | high<br>security review before landing | ~395 | `python3 -m unittest discover -s tests -p 'test_friction_apply.py'` |
| [P25 scheduled-commit](briefs/25-scheduled-commit.md) | M | P16b, P24 | sol / high<br>Sol reason: Brokered commits must bind trusted pre-review Git state to current-run backups. | high<br>security review before landing | ~385 | `python3 -m unittest discover -s tests -p 'test_friction_apply.py'` |
| [P26 friction-skill](briefs/26-friction-skill.md) | N | P20b, P22, P25 | terra / medium | normal | ~375 | `python3 -m unittest discover -s tests -p 'test_friction_skill.py'` |
| [P27 release](briefs/27-release.md) | O | P26 | terra / medium | low | ~320 | `python3 -m unittest discover -s tests -p 'test_repo.py'` |
| [P28 real-input-gate](briefs/28-real-input-gate.md) | P | P27 | terra / medium | normal | ~300 | `python3 -m unittest discover -s tests -p 'test_repo.py'` |

- **A** — P00.
- **A1** — P01, P02, P03, P04.
- **B** — P01b, P05, P08, P14.
- **C** — P06, P07, P09, P12.
- **D** — P10, P11, P13, P14b.
- **E** — P12b, P15, P16, P18.
- **F** — P14c, P15b, P16b, P18b.
- **G** — P17, P19, P21, P24a.
- **H** — P20, P22.
- **I** — P20b.
- **J** — P23.
- **K** — P24b.
- **L** — P24.
- **M** — P25.
- **N** — P26.
- **O** — P27.
- **P** — P28.

## Traceability

| Requirement / review finding | Packet and acceptance owner |
|---|---|
| One-pass Claude/Codex detection, truthful basis, scan speed and format stability | P03, P05, P09, P13, P17, P28 |
| Host probe, sprawl, bounded samples and scoped notices | P04, P06, P10, P14/P14b/P14c, P17, P22 |
| Bounded inputs and evidence, stable action schema/state, gate and successful review | P01/P01b, P02, P07, P11, P20/P20b, P23, P26 |
| Reversible eligible host/Git operations and guarded scheduled broker | P08, P12/P12b, P15/P15b, P16/P16b, P18/P18b, P19, P24a/P24b/P24, P25, P26, P28 |
| Linked/copied installation, compatibility, privacy, context budget and release | P00, P14c, P21, P22, P23, P24, P26–P28 |
| Codex B1–B3 | P08/P16/P25 ordinary manifest handoff. P07/P11/P20b/P26 exact wire/ID and co-landed interactive import. P11/P20/P23/P24 receipt and crash/retry ordering. |
| Codex B4–B6 | P24a/P24/P25 trusted quota incl. unbacked edits. P24b/P24/P25/P26/P28 idempotent scoped ledger/undo. P05/P18 accepted-only per-literal and scope evidence. |
| Codex B7–B9 | P12 cwd and project-target refusals. P00/P01/P06/P14b/P21/P20/P20b/P23/P24b/P24 copied aliases and installer coverage. P03/P20/P20b bound fingerprint comparisons. |
| Codex B10–B12 | P03/P23 global audit and P26 independent refresh. P14c explicit installer-probe paths and verification. P28 separate eligible fixtures. |
| Codex A1–A3 | P06/P10 runtime probe tests. P18/P28 fresh scheduled permission-boundary checks. P28 installed CLI timing with 0.12.0 control. |
| Sonnet 1–4 | P00 pre-registration. P14/P14c title, changelog and ownership cleanup. P24 corruption cleanup and owner allocation. P06/P10 right test names. |
| Sonnet 5–7 | P01/P12/P14/P15/P16/P18 splits and archive sizing. Explicit mutation security sign-off. P26 exact branch preamble and sidecar. |
| Sonnet advisories | P01/P04/P06/P14b copied siblings, P06 exact probe name, P14c runner retention tests and success-only sampling, P22 notice byte cap, context branch references, P27 claims rerun, P28 privacy, split numbered criteria and reduced P18 dependencies. |

## Risks, rollout and rollback

- While integrating, keep unverified mutations disabled and existing 0.12.0 permission grants untouched. If parser versions drift, canary output stays available and unknown durations or formats skip friction measurements. Kill/retry paths are exercised before enabling work.
- Update the plugin, re-trust changed hooks where required, and refresh managed links for scheduled installs. Use project `friction=off` to stop processing, `hostActions=suggest` or `off` to stop new automatic host actions, and global `frictionSampler=off` to stop sampling. An unconfirmed hook may stay inactive on that host.
- To roll back applied effects, use the scoped tool's structured undo, or the backup's validated Git revert for a commit. Preserve private records so rollback survives disabled collection or exchange of plugin versions. Return the plugin/links to the prior release only after keeping the undo tooling for applied changes. Housekeeping expires samples and prepared outputs, while action and undo records stay.
- Keep actual reports, transcript content, host paths, process arguments and machine information outside public artifacts. Gate output contains sanitized status lines and can cite measurements only from the run with its basis.

## Research needed

Planning was offline. The October hook notes are leads; verify against current shipped runtimes and document results by one version and environment per claim.

| Gate | Question and suggested source | Consequence |
|---|---|---|
| S1 | On current supported Claude Code, which success/failure events supply optional `duration_ms` and stable session/tool IDs? Does duration exclude permission and pre-tool time? How do async commands and their subprocesses behave on timeout, interruption and immediate `-p` teardown? Read Claude Code hook docs and capture key/type-only payloads and timings from throwaway interactive and headless runs. | P14c default-on and P17 measured joins. Missing fields degrade to estimates. If additional async registration breaks Codex or Copilot using the shared manifest, hold default-on registration and resolve with the 0.12.0 host choice. |
| S2 | Does current Claude Code match exact `Bash(<literal>)` in local project settings as required, including extra args, quoting, chaining, redirect, substitution, managed rules and deny precedence? Can it affect the review already in progress or load only on the next session? Use official permissions docs and live negative fixtures. | P18/P24 write enablement. Keep proposals if proof fails. |
| S3 | Does no-root sticky Time Machine exclusion bind to the same directory under nested mount/rename and survive the intended verification/rollback? Does the current Linux LocalSearch honor a `.nomedia` marker, including a private marker payload? Use native help/official documentation and a disposable output-volume or directory exercise. | P15/P19 marker support. Unverified systems keep manual actions. |
| S4 | Which Claude transcript record forms still identify explicit user-sourced permission decisions, user questions, interruptions and timeout details? Are IDs stable across resumption/subagents? Compare redacted field-shape captures in current installations with canary counters and archive fixtures. | P03/P05. No qualified permission evidence means no eligible allow rule. |
| S5 | Which current Codex CLI/IDE rollout envelope types pair tool calls and results, and where are wall seconds, IDs, timeout hints and canonical cwd? Is `hooks/list` reporting the extra PostToolUse entry, and do hook trust and host detection leave it inert? Use local source/schema where available, installed CLI/app-server and redacted rollout key shapes. Verify Copilot loading and sampler no-op via 0.12.0 O1. | P09/P14c/P28. Unknown types stay in canary; no fabricated timings or expanded host support. |
| S6 | Do supported Git versions expose a reliable no-force removal safety boundary for newly changed linked trees and have usable ref compare-and-swap under the planned environment? Probe with temporary repos on supported installs and Git documentation. | P12b/P16b. Keep unknown or unsupported topology read-only. **Answered 2026-11-18 (P12b): no.** Apple Git 2.54 `worktree remove` without `--force` deleted an ignored file, and an open fd could modify the checkout after verification; removal and undo stay proposal-only until a quarantine-retention design lands. |
| S7 | Verify on the scheduled Claude version that bounded stream-json provides caller-authenticated session start, full Edit/Write and helper dispatch/result coverage and final result, with no event loss under tested interruptions. Exercise real backed and unbacked writes, reflected fake envelopes and truncation, and confirm existing permissions on a fresh run. | P24a/P24/P25/P28. Incomplete evidence keeps broker writes unavailable. |

## P27 docs and release

Assemble README, command and scheduling docs, CI checks and the 0.13.0 CHANGELOG/version. Preserve the 0.12.0 host matrix. Keep the release candidate local until the real-input gate accepts all advertised capabilities. P27 owns a follow-up claims pass whenever P28 blocks a conditional capability. Verify refusal and confirm downgraded docs, then rerun P28 for the affected checks. [Release brief](briefs/27-release.md)

## End-to-end verification

### P28 real-input gate

Use the 0.13.0 candidate on real disposable host installs and record each exit status, trimmed output, flags, base version, timing basis, negative tests and undo verification in `gate-results.md`. The packet covers new scripts and subcommands plus the previously existing commands that changed behavior. Use distinct eligible worktree, allow-rule, marker and backup fixtures, and verify a fresh scheduled review in both modes after permission persistence. Compare installed CLI extraction on/off against the installed 0.12.0 baseline for the same input. Normalize home paths to `~` and omit raw captures. Any failed advertised claim returns to P27. Repeat `tools/ci-local --python 3.9` on the integration tree. Status is pending. [Gate brief](briefs/28-real-input-gate.md)

## Benchmark baseline (batch review 2, 2026-11-18)

Every token-audit benchmark compares against the fixed pre-friction revision `d8a4cb7`, with friction on and with `--no-friction`, never against the previous tip: per-packet ratios compounded to 1.31× before BF4. Briefs write `python3 tests/bench_token_audit.py --baseline d8a4cb7 --max-ratio 1.10` (plus the `--no-friction` run).
