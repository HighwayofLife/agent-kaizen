---
name: models
description: "Check which Claude and Codex models are available now, compare price, speed and strengths with the models in my routing, and propose updates."
disable-model-invocation: true
argument-hint: "[propose|safe|auto|yolo|propose-only]"
---

# Check for new models

New models often change the best choice for a routing row: a newer small model can take over work from a mid-tier one, or a new top model can make an escalation rung unnecessary. Run this monthly, or when a provider announces a release.

**Changes:** none until you approve. With `propose-only`, write the proposal to `~/.claude/audits/models-<yyyy-mm-dd>.md` and stop.

**Autonomy:** follow `${CLAUDE_PLUGIN_ROOT}/docs/autonomy.md`. The mode comes from the skill argument (`propose`, `safe`, `auto` or `yolo`), else `docs/kaizen/config.json`, else `~/.claude/agent-kaizen.json`, else `propose`. In `safe` and `auto`, read every "wait for my OK" below as: apply it yourself if the mode allows (backup, verify, roll back on failure, ledger row), otherwise list it as a proposal. Hard stops always ask. At most `maxChangesPerRun` changes (default 3). End with a summary of what was applied, skipped and rolled back.

## Task

```text
0. If docs/kaizen/model-roster.md exists, start from it: it lists my subscriptions,
   pools and the strengths found last time. Update it with what you find here.
1. List the models I currently route to. Find every model name or alias in
   ~/.claude/settings.json (model, modelSettings, env CLAUDE_CODE_SUBAGENT_MODEL),
   ~/.claude/agents/*.md and .claude/agents/*.md (model:), the routing table in CLAUDE.md,
   ~/.codex/config.toml, and any dispatch scripts or env vars that pass -m.
2. Find what is available today, from primary sources:
   - Claude: the Claude Code model configuration docs and Anthropic's models overview and
     pricing pages (current model ids, aliases, context windows, prices).
   - Codex / OpenAI: the Codex CLI docs or release notes for the models it accepts, and
     their pricing or plan limits.
   - Any other agent CLI I use.
   Cite the URL for every model fact.
3. Compare. For each routing row (scout, judge, coder, planner, reviewer, debugger, image
   reader, top tier), is there a model that is cheaper at similar quality, or better at the
   same price? Note deprecations and retirement dates for models I still use.
4. Check what my usage audit (docs/kaizen/ or ~/.claude/audits/) says each tier costs,
   so the saving estimate uses my real volumes.
5. Propose at most 5 changes, each with the expected effect, the risk, how to try it
   safely (one routing row first, for a week), and how the next audit will show whether
   it worked.
Wait for my OK. Add a ledger row (docs/kaizen/LEDGER.md) for each change we make.
```

## Done when

You have a short, sourced table (current model → candidate → why → expected effect) and, after approval, changed routing rows with ledger entries.
