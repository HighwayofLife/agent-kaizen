# What we learned

These notes come from tuning a real setup: a solo game project with a Claude Code main session coordinating Claude subagents and the Codex CLI, over several weeks. The numbers are from our usage audits. Yours will differ, which is why the loop starts by measuring.

## Where the tokens actually went

The first audit surprised us. The expensive things were not the obvious ones:

| Finding | Why it cost so much | What we did |
|---|---|---|
| Main sessions reached 450k–560k context | Cost is roughly context × turns; every turn re-sends everything | Auto-compact at 250k (`modelSettings.<model>.autoCompactWindow`), plus a SessionStart `compact` hook that points the session back at its plan files and git state |
| About 150 spawns of a "Codex wrapper" subagent, ~80k tokens each | The agent only ran `codex exec` and relayed the output, but each spawn loaded a full agent context | Replaced it with a dispatch script run as a background Bash command (`scripts/codex-dispatch`) that prints at most 25 lines |
| 67 images read into the main context | An image stays in context and is re-sent on every later turn | A PreToolUse hook blocks image reads except in designated image agents (`hooks/block-image-read.sh`) |
| Planners making a median of ~190 tool calls, at ~216k context | grep → read → grep exploration loops | A code map (`tools/codemap brief <file>` gives the locations a brief names in one call), an exploration budget of about 60 calls, and the top-tier planner kept for complex plans only |
| ~390 curl calls by per-item judges re-fetching the same history sources | Each judge re-fetched and re-parsed the pages | A cached fetch script: each page is fetched once, and later calls grep the cached text |
| Many small agent spawns | Each completion wakes the main session for a full-context turn | A swarm-lead agent spawns the N workers and returns one merged table. The verifier starts the second-model review itself, so one wake-up covers both |
| Whole-file reads of 600+ line files | They stay in context for the rest of the session | A Read hook that requires a line range above 400 lines, with an explicit override (re-read with `limit`) |

## Slimming the always-loaded files

- **Every line of `CLAUDE.md` is re-sent every turn**, in the main session and in every subagent that loads it. We split ours three ways:
  - a short core with only the rules nearly every task needs;
  - topic docs (`docs/agents/*.md`) that agents read only when the task matches;
  - an orchestrator-only file, `@`-imported by the main session, that subagents and Codex never load.
- **Subagents don't need the whole constitution.** Custom agents set `omitClaudeMd: true`, and a `SubagentStart` hook injects `common.md` (about 10 lines of red lines and conventions) plus one role file (coding, planning, review or research). Built-in agents such as general-purpose still load everything, so the main session prefers custom ones.
- **Dated stories and rationale moved out.** "Why we have this rule" goes in a rationale doc, and the rule itself stays one line.
- **`AGENTS.md` for Codex** is a symlink to (or a pointer at) the same project file, and `~/.codex/AGENTS.md` holds only cross-project habits (about 15 lines).
- **Short role preambles for Codex.** The dispatch script prepends a 3–4 line preamble per role instead of a long system prompt.

## Trimming MCP servers, connectors and tool surface

Tool schemas count as context too.
- **Unused claude.ai connectors.** We had connectors such as calendar, mail, drive and design tools attached to the account but never used in the game repo. We denied them in that project's `.claude/settings.json` with `deniedMcpServers` (by server name). The server then doesn't load at all, which removes more than a permission deny rule does (a deny rule only hides the tools). `disableClaudeAiConnectors` turns all of them off at once.
- **Project `.mcp.json` servers** are controlled with `disabledMcpjsonServers` / `enabledMcpjsonServers`.
- **Tool search stays on** (`ENABLE_TOOL_SEARCH` unset or `true`), so MCP tool schemas are deferred until a tool is actually needed.
- **Codex MCP servers per run.** Our Codex config has engine and DCC MCP servers (a game engine and a 3D tool). Code-only runs disable them with `-c mcp_servers.NAME.enabled=false`, which keeps their tool lists out of the run and stops a run from touching an open editor by accident.
- **Skill and agent descriptions** are listed every turn. Skills you only trigger yourself get `disable-model-invocation: true`, and agent descriptions stay at one or two sentences.
- **Cache awareness.** Connecting or disconnecting servers, switching models and compacting all invalidate the prompt cache. Make these changes between sessions.

## Routing and models

- **Our roster, as an example.** Each vendor does what it is best at, within the subscriptions we have:
  - Claude runs orchestration, judgment, planning, review and produced documents;
  - the Codex CLI is the default for coding, with a separate model for front-end, 3D and visual work, and reviews Claude's code;
  - Grok handles web research and tie-break reviews, plus overflow coding when the Codex cap is tight;
  - Gemini covers whole-repo or very long document analysis, and breaks ties on visual reviews;
  - small Claude and Codex models do reading, command-running and single-claim judging.

  Each routing row has a fallback on another vendor and an escalation ladder. If you don't have a vendor, its rows fall back. `/agent-kaizen:roster` builds this for whatever you have.

- **Delegate down by default:** cheapest capable model first, and retry with more effort before moving to a bigger model. The top tier is capped per session.
- **Use a different vendor to review.** Codex reviews Claude's code and Claude reviews Codex's code. Mixing model families catches more than same-model review.
- **Set the default subagent model** (`CLAUDE_CODE_SUBAGENT_MODEL=sonnet`), so ad-hoc spawns don't inherit the expensive main model.
- **Check for new models periodically** (`/agent-kaizen:models`): a new small model can take over a whole routing row.

## Tools before tokens

- Installing `rg`, `fd`, `ast-grep`, `jq`, `yq` and `shellcheck`, and saying "use them first" in the instructions, moved a lot of work from model reasoning to deterministic commands.
- Each recurring manual step became a script. Ours read test results, summarise batch runs, report test timings, build polygon tables and check asset budgets.
- **Web calls send a normal browser User-Agent.** Several sites refuse default library user agents. We set it once in `~/.curlrc` / `~/.wgetrc` and explicitly in Python scripts. On python.org builds of Python on macOS, also check that the CA bundle exists. Ours was missing, so every urllib HTTPS call failed until we pointed it at the system bundle.

## Test loop (game projects)

- Game logic lives in a plain library with fast unit tests (seconds, no editor). Agents run those first.
- There is one check command per change: the fast tests run first and stop before the engine launches if they fail, then targeted engine filters plus named regression guards run. A **missing, empty or timed-out report is a failure**: one timed-out run wrote no results file at all.
- The full engine suite (sharded), a player build and a smoke test run every 3–4 merges, not per change.
- At most 2 engine instances run machine-wide, through a mkdir-lock slot script.
- Worktrees are created by a script that copy-on-write clones the engine's import cache, so a new worktree takes seconds instead of a 30-minute reimport.
- **Spike "affected tests" features before trusting them.** Our engine's native "run only affected tests" option never selected anything in two spikes, so we kept the tiers above instead.

## Things that didn't work, or needed a second try

- **Rules that agents never see don't help.** After the code map shipped, agents still used it rarely: 5 codemap calls against about 137 grep calls. The rule was in `CLAUDE.md`, which the lean subagents no longer loaded. It had to go into the role context files and the Codex preamble, and the dispatch script now inserts the code locations into the prompt automatically.
- **Guardrails need an override.** The first big-read guard denied whole-file reads with no way around them. Agents that really needed the whole file (to review or rewrite it) got stuck, so the deny message now spells out the override.
- **Measure before and after.** Every change gets a ledger row, and the next audit fills in the measured effect. Some changes we expected to help barely moved the numbers. Without the ledger we'd have kept them on faith.
