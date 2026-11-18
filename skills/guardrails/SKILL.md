---
name: guardrails
description: "Install hooks for big reads, images, compaction, and Agent tier allowances, each with an override."
disable-model-invocation: true
argument-hint: "[propose|safe|auto|yolo]"
---

# Guardrail hooks, each with an escape hatch

Stop the most expensive habits automatically: whole-file reads of big files, images landing in the wrong context, and sessions that grow without limit. Each guardrail has a documented override, so an agent with a real need is never blocked.

**Changes:** adds hook scripts and `settings.json` entries, after you approve. Back up `settings.json` first.

**Autonomy:** follow `${CLAUDE_PLUGIN_ROOT}/docs/autonomy.md`. The mode comes from the skill argument (`propose`, `safe`, `auto` or `yolo`), else `docs/kaizen/config.json`, else `agent-kaizen.json` in your Claude config dir (`$CLAUDE_CONFIG_DIR` or `~/.claude`), else `propose`. In `safe` and `auto`, read every "wait for my OK" below as: apply it yourself if the mode allows (backup, verify, roll back on failure, ledger row), otherwise list it as a proposal. Hard stops always ask. At most `maxChangesPerRun` changes (default 3). End with a summary of what was applied, skipped and rolled back.

In this skill, `<Claude config dir>` means `$CLAUDE_CONFIG_DIR` or `~/.claude`, and `<Codex home>` means `$CODEX_HOME` or `~/.codex`.

## Task

Propose Claude Code hooks that stop wasteful patterns. Check the current Claude Code hooks
documentation for the exact input fields and the deny/allow output format before writing
any script.

The plugin ships no live loop guard. Use `Stuck turns` as the evidence gate: if they
are a large share of cost over two audits, first propose fixes for their causes. A
heuristic hook with no model call is a later option, not a shipped guard.

1. Big-read guard (PreToolUse on Read): deny a Read of a code, data, scene or log file
   over ~400 lines when no line limit is given. The denial message must:
   - name the file and its line count;
   - point at the cheaper path (tools/codemap outline FILE, rg -n PATTERN FILE, jq or
     yq for data, tail or rg for logs);
   - say plainly: "If you really need the whole file, Read it again with an explicit
     limit; that is allowed."
   Any Read with an explicit limit passes. Never block small files or non-code files.
2. Image guard: if images are being read by the main session or by agents that don't
   review visuals (see the audit), deny those Reads and point at one designated image
   reviewer (an agent or a script). Allow the image-review agents.
3. Compaction: check the docs for a setting that controls when a session auto-compacts
   (a context window or threshold). If one exists, propose a value that suits me
   (the author used 250k with a large-context main model), plus a SessionStart hook on "compact" that tells the session to
   re-read its plan files and git status instead of relying on memory.

For each hook: write the script under <Claude config dir>/hooks/, test it by piping sample JSON
into it (blocked case, allowed case, override case), then show me the settings.json
change. Back up settings.json first. Add ledger rows.

## Bundled resources

Bundled, tested hooks: `${CLAUDE_PLUGIN_ROOT}/hooks/limit-big-read.sh`, `${CLAUDE_PLUGIN_ROOT}/hooks/block-image-read.sh`, `${CLAUDE_PLUGIN_ROOT}/hooks/after-compact.sh`, `${CLAUDE_PLUGIN_ROOT}/hooks/subagent-context.sh`, with wiring in `${CLAUDE_PLUGIN_ROOT}/templates/settings.example.json`. Copy them to <Claude config dir>/hooks/ and adapt them, rather than writing new ones.

## Opt-in Agent tier guard

Copy `${CLAUDE_PLUGIN_ROOT}/hooks/tier-guard.sh` to `<Claude config dir>/hooks/` and
merge the settings template's `PreToolUse` entry with matcher `Agent`. Install
`jq` and Python 3.9 or later if needed. Add rules to `<Claude config dir>/agent-kaizen.json`.

```json
{"guardrails": {"agentTiers": [
  {"pattern": "deep-*", "freeSpawns": 2, "reasonRegex": "^Tier reason:[ \\t]*\\S"}
]}}
```

The first case-sensitive glob matching `tool_input.subagent_type` sets the free
allowance per session, including requests that omit `model`. After the allowance,
retry with a non-empty `Tier reason: <why>` line. The guard searches the prompt
with the configured Python regex and multiline anchors. Disable it by
removing the `Agent` entry, clearing `agentTiers`, or setting global `enabled` to `false`.

The counter tracks allowed PreToolUse requests even if the spawn later fails.
Owner-only state lives in `<Claude config dir>/kaizen-tier-guard/`. Log entries
contain only a timestamp, rule and supplied reason. Keep sensitive details out
of the reason. Input, config, dependency, state and lock errors allow the request.

## Done when

fewer whole-file reads and images in the audit, and shorter sessions. Nothing becomes impossible; the expensive path just needs an explicit choice.
