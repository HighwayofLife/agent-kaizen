# <Project name>: agent constitution

<!-- Template for <repo>/CLAUDE.md (and AGENTS.md: symlink it, or give AGENTS.md one line
pointing here). It is re-sent on every turn, so keep only what nearly every task needs.
Topic detail goes in docs/agents/*.md; process that only the main session needs goes in
docs/agents/orchestrator.md, imported at the bottom. -->

Read `<design doc path>` before design work. Plans and briefs live in `docs/plans/<yyyy-mm-dd>-<slug>/` (`plan.md`, `briefs/NN-*.md`).

## Architecture (invariants only)

- <e.g. Game logic lives in `<core library>` with no engine references; the engine is a viewer that reads snapshots and sends commands.>
- <e.g. Determinism: one seeded PRNG with named streams; no wall clock in game logic.>
- <e.g. Every tunable lives in `<settings file>`; never hard-code one.>
- <e.g. Player-facing text lives in language files keyed by id.>

## Commands

```
<build command>
<fast unit tests: seconds, no editor>
<engine tests: targeted filter>
<one check command per change, e.g. tools/check.sh>
<asset validator, if any>
```

Inside the Codex sandbox (no network): <the offline build and test variants, if they differ>.

## Code map

`tools/codemap` indexes symbols, settings keys, localisation ids and scenes. Use it before grepping or reading files, then read only the line ranges it prints: `find`, `outline <file>`, `refs`, `setting <key>`, `tests <fragment>`, `brief <file>`, `tree`.

## Working rules

- Tests first (red), then implement (green). Never weaken a test to pass it.
- One brief per change, under ~400 changed lines. Report files changed, checks run with results, and anything unsure.
- Agents do not commit or push; the main session owns git.
- Tools before tokens: <list this repo's scripts for results, logs, timing and assets>.
- Never add a dependency or package yourself: stop and report.

## Topic docs

Read the one that matches your task and skip the rest:
- `docs/agents/engine.md`: engine toolchain, test runner, batch-mode traps.
- `docs/agents/assets.md`: asset tools, budgets, licensing ledger.
- `docs/agents/ui-text.md`: language files and naming.

Main session only (Codex and subagents skip it): @docs/agents/orchestrator.md
