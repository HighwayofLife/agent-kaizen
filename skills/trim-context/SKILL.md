---
name: trim-context
description: "Measure and trim what loads into every turn: MCP servers and tools, claude.ai connectors, plugins, skill and agent descriptions, and Codex MCP servers."
disable-model-invocation: true
argument-hint: "[propose|safe|auto|yolo]"
---

# Trim the always-loaded tool and context surface

Every MCP tool schema, connector, enabled plugin, skill description and custom-agent description can add tokens to every turn, even if you never use it. Removing what this project never uses saves tokens on every turn after that.

**Changes:** settings and config, after you approve. Back up each file changed, including `.claude/settings.local.json` when used, first.

**Autonomy:** follow `${CLAUDE_PLUGIN_ROOT}/docs/autonomy.md`. The mode comes from the skill argument (`propose`, `safe`, `auto` or `yolo`), else `docs/kaizen/config.json`, else `agent-kaizen.json` in your Claude config dir (`$CLAUDE_CONFIG_DIR` or `~/.claude`), else `propose`. In `safe` and `auto`, read every "wait for my OK" below as: apply it yourself if the mode allows (backup, verify, roll back on failure, ledger row), otherwise list it as a proposal. Hard stops always ask. At most `maxChangesPerRun` changes (default 3). End with a summary of what was applied, skipped and rolled back.

## Task

```text
1. Measure first. Ask me to run /context and paste the result. In a headless or autonomous
   run, estimate instead: file sizes / 4 for instruction files, plus counts of servers, tools,
   skills and agents. Then list:
   - MCP servers (`claude mcp list`), and which of their tools any transcript in the last
     30 days actually called (count tool names starting with mcp__ in ~/.claude/projects);
   - claude.ai connectors that show up in this project;
   - enabled plugins and their skills, agents and hooks;
   - custom agents and skills whose descriptions are listed every turn, and how often each
     was used (subagent types in transcripts, Skill tool calls);
   - Codex MCP servers in ~/.codex/config.toml, and how often Codex sessions used them.
2. Propose, each with the token or turn saving where you can estimate it. Check every
   setting name against the current Claude Code settings docs first:
   - use `Unused tools and MCP servers` in the audit to propose `permissions.deny`
     entries in `.claude/settings.local.json`. Check the current Claude Code settings
     docs for exact built-in tool and MCP server/tool deny syntax before writing;
   - never deny a tool named in the project's CLAUDE.md, agents, skills or hooks. Prefer
     denying a whole unused MCP server over its tools. Deferred tools cost only their name
     per turn, so prioritize servers loaded in full or carrying server instructions;
   - apply each deny between sessions: a changed tool set invalidates a resumed conversation's
     prompt cache. Each entry gets its own ledger row and `/agent-kaizen:undo` can reverse it;
   - deny servers or connectors this project never uses (settings key deniedMcpServers;
     disableClaudeAiConnectors to turn all claude.ai connectors off; for project .mcp.json
     servers, disabledMcpjsonServers or enabledMcpjsonServers). Prefer project-level
     settings when another project still needs the server;
   - keep MCP tool search on (ENABLE_TOOL_SEARCH unset or true), so tool schemas load only
     when needed;
   - disable plugins this project doesn't use;
   - mark user-triggered skills `disable-model-invocation: true`, so the model doesn't
     carry their descriptions;
   - shorten long agent and skill descriptions to one or two sentences that say when to
     use them, and merge or delete agents unused in 30 days;
   - in Codex, set enabled = false on MCP servers that most runs don't need, and enable
     them per run (codex exec -c mcp_servers.NAME.enabled=true);
   - prune stale [projects."..."] trust entries in ~/.codex/config.toml.
3. Note the trade-offs. Connecting or disconnecting MCP servers, switching models and
   compacting all invalidate the prompt cache, so make these changes between sessions,
   not in the middle of one.
Show each diff, wait for my OK, then ask me to run /context again so we can record the
before/after numbers in docs/kaizen/LEDGER.md.
```

## Done when

`/context` shows a smaller fixed overhead, and the ledger has the before/after numbers.
