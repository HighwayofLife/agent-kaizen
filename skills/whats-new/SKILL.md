---
name: whats-new
description: "Check recent Claude Code and Codex releases and new CLI tools for features that replace workarounds or cut cost."
disable-model-invocation: true
argument-hint: "[propose|safe|auto|yolo]"
---

# What's new: tools and features worth adopting

Claude Code, Codex and the CLI ecosystem change quickly. Check what's new now and then, and adopt what cuts cost or time, instead of carrying old workarounds forever.

**Changes:** none until you approve a proposal.

**Autonomy:** follow `${CLAUDE_PLUGIN_ROOT}/docs/autonomy.md`. The mode comes from the skill argument (`propose`, `safe`, `auto` or `yolo`), else `docs/kaizen/config.json`, else `~/.claude/agent-kaizen.json`, else `propose`. In `safe` and `auto`, read every "wait for my OK" below as: apply it yourself if the mode allows (backup, verify, roll back on failure, ledger row), otherwise list it as a proposal. Hard stops always ask. At most `maxChangesPerRun` changes (default 3). End with a summary of what was applied, skipped and rolled back.

## Task

Check for new features and tools that could make my workflow faster or cheaper.

1. Read the recent release notes and changelogs for Claude Code and the Codex CLI (and any
   other agent CLI I use), and the current docs pages for subagents, hooks, settings,
   skills and model selection. List features since my config was last changed (see
   docs/kaizen/LEDGER.md) that affect:
   - context size;
   - model or effort selection;
   - subagent cost;
   - caching;
   - compaction;
   - parallelism;
   - background work.
2. Compare them with my current setup (agents, hooks, settings, scripts). Point out:
   - workarounds I built that a new built-in feature now replaces;
   - settings I'm missing;
   - newer or cheaper models that fit some of my routing rows.
3. Check for newer or better CLI tools for this project's languages and engine (search,
   refactoring, formatting, asset inspection, test runners) that agents could use
   instead of model reasoning.
4. Propose at most 5 adoptions, each with the expected effect, the risk, and how to
   measure it in the next audit.
Cite the source page for every claim. Wait for my OK before changing anything; add
ledger rows for what we adopt.

## Done when

a short, sourced list of upgrades, and sometimes a chance to delete a workaround of your own.
