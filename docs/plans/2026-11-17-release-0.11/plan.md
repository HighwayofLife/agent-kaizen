# 0.11.0: First five minutes

## Summary

Deliver a first scan, local automatic audit, cache visibility, optional tier guard and format diagnostics. The release gate is mandatory.

## Goal / non-goals

A new user gets a finding quickly without installing an OS scheduler. No network, external dependencies, cache TTL simulator or CI workflow changes. The OS scheduler remains available.

## Context

`README.md:196` correctly describes disabled skill visibility in Claude Code 2.1.327; the auditor agent remains visible. `scripts/token-audit:1336` writes reports even with JSON. `scripts/usage-db:34` lacks spawn identity. `scripts/kaizen-scheduled:308,1532,1570` supplies a global lock, checks and audit/ingest pipeline. `context.md` holds the verified map.

## Approach

Use a model-visible repo-text budget and synthetic examples. Add no-write audit mode before the scan. A single asynchronous SessionStart worker reuses the existing audit pipeline and lock, recording successful due state atomically; it enforces its own deadline. Persist a versioned format canary and have doctor read it. Reject a new scheduler, SessionEnd ingest, and a full cache simulator: the existing audit already ingests usage and covers all projects.

## Decisions needed

None. The orchestrator settled the contracts below.

## Assumptions

The context budget is an estimated byte proxy, scoped to the tested CLI version, not exact runtime tokens. Full rewrite means write tokens at least 80% of positive context. Gap buckets are first, unknown, ≤5 minutes, >5–60 minutes and >60 minutes; subagent-type gaps are approximate. Missing scan signals show WARN/unknown. PreToolUse counters represent allowed spawn requests, not completed spawns.

## Research needed

R1 hook payloads and R2 visibility are complete in `research.md`. R3 is an optional owner-local backtest requiring at least 17 active days per metric; report aggregate results only. It does not replace the mandatory real-input release gate.

## Acceptance criteria and traceability

1. **J6 → 01:** Budget only visible agent descriptions, non-disabled skill descriptions and maximum literal output of each registered hook; fail for missing flags, missing inventory or over-budget; preserve the accurate skill claim and document tested visibility and agent cost.
2. **A2 → 02:** A repeatable synthetic generator produces safe fixture data that exercises main context, relay agent, cache rewrite and image inputs, with correct timestamps and isolated roots.
3. **A1 → 04a, 04b:** A no-write audit and scan provide actionable first findings and a disposable demo, including explicit unknowns for unavailable signals, without persistent writes.
4. **B1 → 03:** Cache reporting groups writes and rewrite heuristics by correctly ordered, distinct gap buckets and labels uncertain attribution.
5. **C2 → 05:** An opt-in, bounded, fail-open tier guard counts allowed spawn requests, applies first matching agent-type rule and offers a documented reason override.
6. **G1 + G2 → 06, 07:** Persist versioned parser-coverage canary metadata; a read-only doctor reports install/data health and handles missing or older reports.
7. **I1 → 08:** One silent async SessionStart hook runs the all-project audit when due, checks enrolled projects, records only successful unscoped runs, retries failures and honors global opt-out.
8. **B2 → 09:** A bounded local sentinel compares eligible metrics over 3 versus 14 active days, reports insufficient data and emits at most one daily notice.

## Packets

All are `codex-engineer`; normal packets receive batch review and high packets individual review. Waves branch from the prior merged tip, max four. Verify cells list exactly the commands in each brief, in brief order. Files in the same wave do not overlap. Feature packets propose changelog text. At each sequential landing the integrator updates the manifest and adds a dated changelog entry before checks, without parallel worktrees editing those shared files: use patch versions 0.10.1 through 0.10.10 in the table landing order; packet 10 sets 0.11.0.

| ID | Packet | Depends | Wave | Model / effort | Risk | Size | Verify |
|---|---|---|---|---|---|---|---|
| 01 | Context budget | — | A | Terra medium | normal | M | test_context_budget, test_rules_lint, test_repo, ci-local --skip-tests |
| 02 | Synthetic generator | — | A | Terra medium | normal | M | test_demo_fixtures, test_usage, test_kaizen_link, generator --help |
| 05 | Tier guard | — | A | Sol high: concurrency | high | M | test_tier_guard, test_hooks, shellcheck tier-guard, test_repo |
| 03 | Cache report | 02 | B | Terra medium | normal | M | test_usage_db, test_usage, benchmark, report --help |
| 04a | No-write audit | 03 | C | Terra medium | normal | M | test_usage, benchmark |
| 08 | SessionStart audit | 01 | C | Sol high: concurrency and process lifecycle | high | L | test_hook_schedule, test_schedule_usage_db, test_hooks, shellcheck session-audit, context budget, scheduled --help |
| 04b | First scan | 02, 04a | D | Terra medium | normal | M | test_scan, test_kaizen_link, test_repo, scan --help, demo timing |
| 06 | Format canary | 04a | D | Terra medium | normal | M | test_format_canary, test_usage, benchmark |
| 07 | Doctor | 06 | E | Terra medium | normal | M | test_doctor, test_kaizen_link, doctor --help |
| 09 | Regression sentinel | 03, 08 | E | Sol high: concurrent notice state | high | L | test_usage_guard, test_usage_db, test_schedule_usage_db, test_regression_notice, test_hooks, shellcheck audit-notice, context budget, guard --help |
| 10 | Release gate | 04b, 07, 09 | F | Terra medium | normal | M | test_kaizen_link, test_schedule, test_install_schedule, test_repo, test_rules_lint, demo, ci-local Python 3.9, plugin validate; owner real-input gate |

Wave A: 01 owns budget, README, learned notes and rules-lint; 02 owns generator, registration lists and its tests; 05 owns tier hook, guardrails and template. B: 03 owns usage-db, token-audit and usage tests. C: 04a owns token-audit and usage tests; 08 owns scheduling, registered hook, inventory and scheduling docs. D: 04b owns scan, skill, README and registration lists; 06 owns token-audit and canary tests. E: 07 owns doctor and registration lists; 09 owns usage-db, audit-notice, inventory and new tests. F: 10 owns release docs, release tests, manifest and changelog. Tests may read other packets' files, but must not edit files owned in parallel.

03 and 04a are serial because both edit token-audit and test_usage. 06 follows 04a. 07 depends on 06 alone. 08 does not depend on 05. Three Sol high assignments are justified by concurrency and process lifecycle. If 08 or 09 exceeds about 400 changed lines, split the former into hook and due-state slices or the latter into guard and notice integration; retain tests with behavior and recheck file ownership.

## End-to-end verification

Packet 10's owner-run commands and expected outcomes are mandatory: scan, doctor, cache report, usage guard, audit canary, tier guard fixture, and SessionStart in scratch configuration. Keep outputs local and never commit reports or transcripts. Record sanitized statuses, exit codes and elapsed first-finding time in Results. If real input or required tools are unavailable, the gate is blocked. Also verify copy and linked installs, Python 3.9 and plugin validation.

### Results

| Real-input gate | Status |
|---|---|
| First scan and elapsed time | pending (orchestrator) |
| Doctor | pending (orchestrator) |
| Cache report | pending (orchestrator) |
| Regression guard | pending (orchestrator) |
| Audit format canary | pending (orchestrator) |
| Tier guard fixture | pending (orchestrator) |
| SessionStart fixture | pending (orchestrator) |

## Risks and mitigations

- Concurrent hooks and stale state: bounded worker, global lock, atomic success marker, fail-open guard, retry tests.
- Format drift and ambiguous subagent attribution: explicit canary, unknown buckets and approximate labels.
- Context estimate is not measured token use: scope findings to tested CLI and describe proxy and overcount accurately.

## Rollout / rollback

Land on an unpublished integration branch with the required version and changelog update on every packet landing; packet 10 sets the release version. Disable `autoAudit` in global config or revert the registered hook to stop automatic audits. Existing database and reports remain readable and owner-removable; no destructive migration.

## Open questions

Optional R3 backtest remains owner-local. No blocking decisions remain.
