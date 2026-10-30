# Prompt evaluation

The skills started as 10 copy-paste prompts. Before publishing, we evaluated each one against four questions:
1. Does it measure before it changes anything?
2. Does it name real settings, fields and commands, and check them against the docs?
3. Is it safe (proposes, backs up, logs to the ledger)?
4. Does it fit the loop (records how it will be measured)?

This is what changed and why.

| Skill | First-draft problem | Fix |
|---|---|---|
| `start` | Didn't exist. Changes were one-offs with no record of their effect | New: ledger, loop README, baseline of what loads every turn |
| `audit` | Didn't say where transcripts live, missed subagent transcripts, would double-count tokens | Names `~/.claude/projects/<proj>/*.jsonl` plus `<session>/subagents/*.jsonl` and Codex `function_call`/`custom_tool_call`. De-duplicates by message id. Reports context × turns. Ships a working script instead of asking Claude to write one |
| `slim-instructions` | "Remove unneeded rules" risked losing rules silently | Must list every dropped or merged rule and why, plus a before/after token estimate per file |
| `lean-agents` | Assumed frontmatter and hook features exist | Tells Claude to check the docs (`omitClaudeMd`, `SubagentStart` `additionalContext`), warns that built-in agents still load CLAUDE.md, ships the hook and templates |
| `codex-dispatch` | Asked Claude to write a dispatcher from scratch | Ships a tested, portable dispatcher (resume rounds, checks outside the sandbox, overload retry, `--disable-mcp`, code-map prefetch) |
| `tools-before-tokens` | Generic | Adds "find the 5 steps agents repeat by hand from the audit and script them", plus a cached web fetch for research-heavy work |
| `code-map` | Too big to build in one step | "Plan first, then build", explicit query speed targets, and a check that agents actually use it (our first version was barely used because the rule never reached the agents) |
| `guardrails` | The first big-read guard had no override and blocked agents that really needed the whole file | Every guard documents its override in the deny message. The hooks are tested with sample JSON (blocked, allowed and override cases) |
| `batch-wakeups` | Was merged with the scheduled audit | Split out: batching turns and scheduling audits are different changes, measured differently |
| `planning` | Fine, but no exploration limit | Adds the ~60-call budget and "Research needed" instead of open-ended exploring |
| `test-loop` | Trusted engine "affected tests" features | Requires a spike first (ours never selected a test), and treats missing, empty or timed-out reports as failures |
| `schedule` | Cloud scheduling was an option | Cloud routines can't read local transcripts. Local launchd, cron or systemd only. The weekly review proposes by default, with restricted tools |
| `review` | Didn't exist | New: the recurring step, including a check that rules actually reach agents (by sampling transcripts) |
| `whats-new` | Didn't exist | New: release notes and new CLI tools vs the current setup, sources required |
| `models` | Didn't exist | New: available models vs routing rows, using real volumes from the audit, trialled one row at a time |
| `trim-context` | Didn't exist | New: MCP servers, connectors, plugins, skill and agent descriptions, Codex MCP, with cache-invalidation warnings |
| `roster` | Didn't exist. Routing assumed a fixed set of vendors | New: detects the CLIs and subscriptions you have (key names only, never values), researches strengths with sources, optionally runs a bake-off on your repo, then builds routing with fallbacks, escalation ladders and pool rules |
| `cycle` | Didn't exist | New: one entry point that runs the loop and decides which checks are due |

## Known limits

- Setting names and CLI flags are from late 2026 and may change. Every config-writing skill tells Claude to verify them against the current docs.
- The token audit reads Claude Code and Codex transcript formats, which aren't a stable public API. If a section comes out empty after an upgrade, the parser needs updating.
- Savings estimates in audits are rough. The ledger's measured effect, from the next audit, is what counts.
