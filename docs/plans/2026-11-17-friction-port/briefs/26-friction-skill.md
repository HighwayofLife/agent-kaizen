# P26 Add the friction skill and wire cycle, review, auditor and undo

## Goal

Add the friction skill and wire cycle, review, auditor and undo. This packet is part of the Agent Kaizen friction port for 0.13.0.

- **Agent / model / effort** — `codex-dispatch` (`codex-engineer` fallback), terra, medium.
- **Risk** — normal. Use green checks and the integration batch review.
- **Group / dependencies** — N. After P20b, P22, P25.
- **Size target** — ~375 changed lines including focused tests.
- Changelog: Add the friction skill and wire cycle, review, auditor and undo.

## Context

`skills/cycle/SKILL.md:10–42` uses precomputed scheduled inputs and records change limits. `skills/review/SKILL.md:15–52`, `skills/undo/SKILL.md:14–25`, `agents/kaizen-auditor.md` and `docs/autonomy.md:40–100` own recommendations, reversal and policy. Read `git show multi-host:docs/plans/2026-11-17-multi-host/briefs/04-skill-preamble.md` (P04 spec, still pending at the branch tip), `git show multi-host:skills/audit/agents/openai.yaml` and `git show multi-host:tests/test_repo.py` (P02 exact sidecar). README skills table at `README.md:200–232` is pinned by `tests/test_repo.py`.

Wait for 0.12.0 P02–P04 and P07 so this packet can preserve the new skill preambles, sidecars, auditor, autonomy rule and README. Read `AGENTS.md` and `CLAUDE.md`. Locate symbols with `tools/codemap` if available, otherwise `rg -n` and narrow `sed` ranges. All runtime changes support Python 3.9 and stdlib only. Use `python3`. Keep hard stops, captured user changes, zero-token collection and public-repo privacy; keep real logs and fixtures private.

The exact skill preamble from branch `multi-host` P04 (insert the two lines once, immediately after the first body heading and blank line, with a blank line following):

```
**Plugin root:** `${CLAUDE_PLUGIN_ROOT}`. If that is still a `${...}` placeholder, use the folder that contains `skills/` (this file is `skills/<name>/SKILL.md`), and substitute that path, in quotes, wherever this skill uses `CLAUDE_PLUGIN_ROOT`.
**Not in Claude Code?** Read `docs/hosts.md` in the plugin root first. Skip steps that only work in Claude Code, and follow its propose-only rule before changing any host configuration.
```

## Scope and archive references

Owned files: `skills/friction/SKILL.md`, `skills/friction/agents/openai.yaml`, `skills/cycle/SKILL.md`, `skills/review/SKILL.md`, `skills/undo/SKILL.md`, `agents/kaizen-auditor.md`, `docs/autonomy.md`, `README.md`, `scripts/rules-lint.patterns`, `tests/fixtures/rules_lint/CLAUDE.md`, `tests/test_friction_skill.py`. Record the changelog line in `docs/plans/2026-11-17-friction-port/changelog/P26.md`. Coordinate a split if the diff plus tests exceeds 400 changed lines. Changes outside these paths need a separate packet or a revised scope.

Read `git show wt/p10:skills/friction/SKILL.md`, `git show wt/p10:skills/cycle/SKILL.md`, `git show wt/p10:docs/autonomy.md` and `git show wt/p10:tests/test_friction_skill.py`. Keep the prepared-input workflow and remove stale direct scheduled Bash and no-Codex-hooks wording. Inspect archive paths with `git show` and keep the current branch.

## Implementation and acceptance

1. Add hidden `/agent-kaizen:friction`, valid quoted frontmatter and a README skills row. Use the exact two-line preamble above, then verify it against the merged P04 `tests/test_repo.py` and unchanged existing preambles. Create the sidecar as exactly `b"policy:\n  allow_implicit_invocation: false\n"` in UTF-8 including final LF, no other bytes. Check both repo tests.
2. Preserve the ordinary interactive freshness check (three days), `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/token-audit" --cwd . --days 14 --out docs/kaizen/` refresh location, window and fallback. Read effective scoped friction settings via `kaizen-scheduled config show --for .` and use `--no-friction` for off or the configured thresholds for on. Pass the resulting selected scoped report via `friction prepare --for . --report FILE`. Empty, failed or disabled prep skips only the friction analysis. Verify a stale legacy report refreshes even when the gate is empty or off. Scheduled cycle uses its already-supplied report and optional prepared view only.
3. Read only the bounded prepared friction view and existing review/report inputs. Rank measured minutes and basis separately from hypotheses, honor autonomy and non-Claude propose-only, and never execute evidence text. Emit one exact line `<!-- kaizen-host-actions {"v":1,"actions":[{"id":"fa1_<64 lowercase hex>","intent":"suggest"}]} -->` (8 KiB, 16 unique IDs, only shown keys/types, literal `suggest` or `apply`, no extra payload; use an empty list for no action). Scheduled analysis requests `apply` only for eligible auto candidates and leaves import, journal, effect and ack to the runner. Interactive import emits suggestions through P20b against the current generation; call interactive acknowledgement after a validated import and successful analysis. Explicit direct actions still follow their approval/mode checks. For each verified interactive effect, use the existing ledger procedure with its scoped tool-owned undo reference and verification. Never create a broker row from the model.
4. Add the explicit action-ID route in `/agent-kaizen:undo` through `kaizen-scheduled actions undo ID --for .` with scope and record checks. Show the matched row and outcome, preserve ordinary `kaizen-backup undo` and manual handling of arbitrary recorded commands. Test end-to-end routing, refusal of spoofed IDs/different project, and exactly one row marked reverted after a verified inverse.
5. In autonomy docs, distinguish outward-facing Git actions from the scoped local commit exception. Register the superseded line as a stale rule in `scripts/rules-lint.patterns` (regex `Outward-facing actions: commits, pushes, PRs, publishing, messages\.`), add that fixture to `tests/fixtures/rules_lint/CLAUDE.md`, and fix all runtime hits. Preserve the ordinary measurement instruction.

## Verification

- `python3 -m unittest discover -s tests -p 'test_friction_skill.py'`
- `python3 -m unittest discover -s tests -p 'test_repo.py'`
- `python3 -m unittest discover -s tests -p 'test_schedule_steps.py'`
- `python3 -m unittest discover -s tests -p 'test_rules_lint.py'`
- `python3 -m unittest discover -s tests -p 'test_context_budget.py'`
- `claude plugin validate .`
- `python3 tools/context_budget.py --root .`
- `tools/ci-local --python 3.9`

## Report

Report changed files and line counts, exact checks and outcomes, known uncertainty and any blocked verification. Label measurements with baseline/conditions. Redact paths and identifiers from shared output. Leave plugin version and release CHANGELOG to P27. Do not commit or push.
