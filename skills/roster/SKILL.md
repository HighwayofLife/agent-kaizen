---
name: roster
description: "Find out which AI models and subscriptions you actually have, research what each is best at, and set up agents, routing, fallbacks and escalation ladders that use their strengths."
disable-model-invocation: true
argument-hint: "[propose|safe|auto|yolo|re-evaluate]"
---

# Build your agent roster: who does what, with fallbacks and escalation

The best routing depends on what *you* have. One example: if you have a Grok subscription, it can be an excellent research agent with okay coding ability. Gemini can handle very long documents or act as a visual tie-breaker. Codex can take most coding off your Claude usage, and a local model can do bulk text transforms for free. None of that matters if you don't have the subscription. This skill:
- finds out what you have;
- researches each model's strengths from current sources;
- optionally tests the models on your own repo;
- builds agents, dispatch scripts, a routing table with fallbacks and escalation, and per-vendor instructions.

**Changes:** creates agents, scripts and instruction sections, after you approve each part. With `re-evaluate`, it re-checks an existing roster and proposes changes only.

**Autonomy:** follow `${CLAUDE_PLUGIN_ROOT}/docs/autonomy.md`. The mode comes from the skill argument (`propose`, `safe`, `auto` or `yolo`), else `docs/kaizen/config.json`, else `agent-kaizen.json` in your Claude config dir (`$CLAUDE_CONFIG_DIR` or `~/.claude`), else `propose`. In `safe` and `auto`, read every "wait for my OK" below as: apply it yourself if the mode allows (backup, verify, roll back on failure, ledger row), otherwise list it as a proposal. Hard stops always ask. At most `maxChangesPerRun` changes (default 3). End with a summary of what was applied, skipped and rolled back.

## Task

```text
Build (or, with "re-evaluate", re-check) my agent roster. Work in phases and stop for my
OK at the end of each phase.

Phase 1: discover what I have. Never print, copy or store secret values.
- Look for agent and model CLIs on PATH and report their versions (claude, codex, gemini,
  agy, grok, cursor-agent, aider, opencode, ollama, llm, gh copilot, and any others you
  find).
- Check each one's sign-in status with its own status command, where one exists.
- List which API-key environment variables are SET, by name only, with exactly this command
  (it prints names, never values):
  env | sed -En 's/^([A-Za-z0-9_]*(API_KEY|TOKEN|SECRET)[A-Za-z0-9_]*)=.*/\1/p' | sort
  Never run env, printenv or grep on the environment in a way that prints values, and never
  read .env files.
- List local models (ollama list), configured MCP servers, and my existing agents
  (~/.claude/agents, .claude/agents).
- Then ask me to confirm and complete the list in one question, covering each provider's
  plan or tier, its known limits (5-hour windows, weekly caps, quotas), whether I want it
  used, and anything you couldn't detect. Ask which pool I most want to protect (for
  example "keep Claude usage for orchestration").

Phase 2: research strengths, as of today.
- For each model I will use, gather from primary sources (official model pages, docs,
  pricing, rate limits, changelogs), plus recent independent benchmarks and practitioner
  reports, with a source URL and date for every claim:
  - strengths and weaknesses: coding, refactoring, front-end and visual work, image
    understanding, web research, long context, planning, review, speed;
  - context window, price or quota, and tool support;
  - any headless or non-interactive mode, and its sandbox and read-only options.
- Write docs/kaizen/model-roster.md: a capability matrix (model × task type, rated
  strong/ok/weak with a confidence level and sources), the pools and their limits, and
  the date. Mark benchmark claims as leads, not facts.

Phase 3 (optional, ask me first): bake-off on my own repo. This sends repo code to each
vendor: list which vendors would see it and get my OK for each one.
- Pick 2–3 small, representative tasks from this repo (a bounded fix, a test to write, a
  code question) and run each candidate model on them in a throwaway git worktree.
- Measure the results: checks pass or fail, wall time, tokens or quota used, review
  findings. My repo beats generic benchmarks. Put the results in model-roster.md.

Phase 4: design the routing.
- A routing table: task shape → primary agent/model/effort → fallback (same tier, other
  vendor) → escalation (next tier up). Cover at least: lookups and reading, single-claim
  verification, mechanical edits, feature work, hard bugs, planning (small, routine,
  complex), code review, security review, visual or UI work, image review, research,
  long-document analysis, produced documents, bulk text transforms.
- Rules:
  - cheapest capable model first;
  - retry once with a sharper brief and more effort before moving up a tier;
  - the reviewer comes from a different vendor than the author;
  - cap the top tier per session;
  - on a quota or rate-limit error, stop routing to that pool for the session and use
    the fallback;
  - spread bulk work to the pools with the most headroom.
- Show the table and ladders and wait for my OK.

Phase 5: build it.
- For each external CLI, prefer a dispatch script over a relay agent:
  - it runs the CLI headless in the safest mode that works (read-only for reviewers and
    researchers, sandboxed for coders);
  - it runs the checks outside the sandbox and prints a short report.
  Use the bundled codex-dispatch / codex-review scripts as the pattern.
- Create a thin agent only where an isolated context really helps. Give it
  `omitClaudeMd: true`, a tools allowlist, the right model and effort, and a one-line
  description that says when to use it and when not to.
- Write each vendor's own instruction file (for example ~/.codex/AGENTS.md, or the
  equivalent for other CLIs) from templates/codex-AGENTS.md: short, with the same
  red lines.
- Add the routing table, ladders and pool rules to ~/.claude/CLAUDE.md (keep it compact;
  long detail goes in ~/.claude/orchestrator/routing-details.md).
- Map every new agent to a role in .claude/agent-context/roles.conf, if I use the
  subagent-context hook.
- Back up everything you touch first. Keys stay in the environment or the CLI's own login,
  never in a file that could be committed.

Phase 6: verify and record.
- Smoke-test each agent and script with a tiny read-only task, and report pass or fail.
- Add a ledger row per vendor or agent added (docs/kaizen/LEDGER.md), with how the next
  audit will show whether it helps (per-pool usage, per-agent cost and success rate).
- Remind me that /agent-kaizen:models and /agent-kaizen:cycle re-check the roster
  periodically.
```

## Bundled resources

- Pattern scripts: `${CLAUDE_PLUGIN_ROOT}/scripts/codex-dispatch`, `${CLAUDE_PLUGIN_ROOT}/scripts/codex-review` and `${CLAUDE_PLUGIN_ROOT}/scripts/README.md`.
- Agent templates: `${CLAUDE_PLUGIN_ROOT}/templates/agents/*.md`. Role context: `${CLAUDE_PLUGIN_ROOT}/templates/agent-context/`.
- Routing table skeleton: `${CLAUDE_PLUGIN_ROOT}/templates/global-CLAUDE.md` (the Routing section). An example of a multi-vendor roster: `${CLAUDE_PLUGIN_ROOT}/docs/what-we-learned.md` ("Routing and models").

## Done when

`docs/kaizen/model-roster.md` exists with sourced strengths, and every routing row has a primary, a fallback and an escalation rung. Each new agent or script passed a smoke test, and the ledger has a row for each.
