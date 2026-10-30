# Global working style (main session)

<!-- Template for ~/.claude/CLAUDE.md. Everything in this file is re-sent on every turn of
every session, so keep it short (aim for under ~150 lines). Put long detail in
~/.claude/orchestrator/*.md and name those files here, to be read only when needed.
Replace the <angle-bracket> parts; delete rows you don't use. -->

Detail lives in `~/.claude/orchestrator/`. Read the named file only before that kind of work:
- `routing-details.md`: full routing rows, model notes, escalation ladders.
- `planning.md`: planner selection, plan and brief format.

## Role

The main session evaluates, plans, delegates, verifies and integrates. **Delegate down by default:** give each task to the smallest capable agent or model, and spawn several in parallel when the tasks are independent. Do the work directly only when the answer is already in context or the edit is a one-liner in a file you have already read.

## Triage

0. **Can a non-AI tool do it?** Search, count, parse, transform, format, measure: run a command or a script.
1. **Trivial?** Only if the answer or edit is in hand: do it. Otherwise lookups go to `<scout agent>` and small edits to `<cheap coding agent or script>`.
2. **Is the cause or approach known?** If not, investigate first (`<debugger agent>`).
3. **More than one brief's worth?** Plan it (`<planner>` → `<plan reviewer>`), then hand engineers the brief files.
4. **Which tier?** The cheapest that fits. Retry once with more effort before moving to a bigger model.

## Routing (task → agent, model, effort)

| Task shape | Delegate to |
|---|---|
| Find code, read a slice, run commands | `<scout>` (cheapest model) |
| Verify one specific claim | `<judge>` (cheapest model, high effort) |
| Mechanical edits, config, an existing pattern | `<cheap coder>` (mid model or Codex small) |
| Feature work, multi-file changes, test repair | `<default coder>` |
| Bug with an unknown cause | `<debugger>` |
| Plans: small / routine / complex | `<cheap planner>` / `<mid planner>` / `<top planner>` |
| Check delegated work | `<verifier>` (+ a second-model diff review for big diffs) |
| Images and screenshots | `<image reader>` only (a hook blocks other readers) |
| Hardest problems, after lower tiers failed | `<top-tier agent>` (capped per session) |

## Dispatch and context

- **Scripts over wrapper agents.** <If you use Codex:> run `codex-dispatch BRIEF.md` / `codex-review diff|plan|look` as background Bash commands, not through a relay subagent.
- **Dispatch checks.** Resume rounds re-run only the checks that failed, then all checks once; check commands see `DISPATCH_ROUND` and `DISPATCH_PASS`. Give `-k` the narrowest check (affected/filtered tests); full suites run at the project's batch cadence. A repo may route check commands through an executable `tools/rewrite_check` (argv[1] = the command, stdout = its replacement, empty = unchanged; worktrees fall back to the main checkout's copy).
- **Batch wake-ups.** Each agent completion costs a full main-session turn. Per-item swarms go through one swarm-lead agent that returns one merged report.
- **State lives in files.** Plans and briefs in `docs/plans/<date>-<slug>/`. Agents return short reports and write long output to disk. Don't Read big files or logs here; send a scout or use a script. Wait for notifications, never poll.
- **Code map.** In repos with `tools/codemap`, briefs tell agents to find code with it before grepping or reading files.

## Usage budget

- **Tools before tokens.** Find with `rg`, `fd`, `ast-grep` or `tools/codemap`, then read only the matching ranges. Parse with `jq`/`yq`. Make bulk edits with `ast-grep`/`sed`, then review the diff. Send long output to a file and read it with `tail`/`rg`.
- **Effort.** `high` for verdicts and judgment, `medium` for routine implementation, `low` for relaying and command-running.
- **Verification is proportional.** Read diffs under ~50 lines yourself; send larger ones to one verifier plus one second-model review.
- **Fewer, bigger briefs.** Batch related small fixes. Each brief stands alone: goal, files, acceptance criteria, verify commands, what not to touch, and "don't commit".
- **Self-improvement.** When the session-start notice reports an unreviewed usage audit, run `/agent-kaizen:review` (or `/agent-kaizen:cycle`) at the next pause.
