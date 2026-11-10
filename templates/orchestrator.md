# Orchestrator process (main session only)

<!-- Template for <repo>/docs/agents/orchestrator.md, imported by CLAUDE.md with
"@docs/agents/orchestrator.md". Subagents (with CLAUDE.md omitted) and Codex never load it,
so process detail here costs nothing on their turns. This holds when AGENTS.md is a one-line
pointer to CLAUDE.md; if AGENTS.md is a symlink, Codex sees the @import line as plain text
and does not load this file either. -->

## Worktrees

- One worktree per parallel task at `../<repo>-wt-<id>` on branch `wt-<id>`, created only with a script you add, such as `tools/new_worktree.sh <id>` (the test-loop skill builds one). That script copy-on-write clones `<large generated caches, e.g. imports or build output>`, so the first run in a new worktree doesn't rebuild them.
- Remove the worktree in the same step as its merge, and only after a clean `git merge`.

## Test throughput

- At most `<N>` instances of `<the heavy tool, e.g. a build or an emulator>` machine-wide, taken through `<a slot script you add>` (mkdir locks, holder PID, dead holders reclaimed). Coding never waits for a slot.
- One check call per change: `tools/check.sh` runs the fast tests first and stops before taking a slot if they fail, then runs the targeted slow-test filters. A missing, empty or timed-out report is a failure.
- Every 3–4 merges: the full suite plus `<build and smoke test>` on main.

## Review proportionality

- Logic and state changes: a second-model code review.
- Small changes to <UI or layout>: tests plus one visual review.
- Visual changes: screenshots in the evidence directory, one reviewer, at most one fix round; the rest goes to a polish list.

## Owner questions

- Open questions for the owner live in `QUESTIONS.md`, each with a recommendation. Ask only about choices that change what <users> can do or see.
