---
name: code-map
description: "Build a local SQLite code map (symbols, settings keys, ids, scenes) so agents find code in one query instead of grep-and-read loops."
disable-model-invocation: true
argument-hint: "[propose|safe|auto|yolo]"
---

# Code map: a symbol index for agents

Agents find code with one indexed query that gives exact line ranges, instead of grep → read → grep loops. This is usually the single biggest saving for planners and engineers in a large codebase.

**Changes:** adds a tool under `tools/` with tests, plus an instruction rule, after you approve.

**Autonomy:** follow `${CLAUDE_PLUGIN_ROOT}/docs/autonomy.md`. The mode comes from the skill argument (`propose`, `safe`, `auto` or `yolo`), else `docs/kaizen/config.json`, else `~/.claude/agent-kaizen.json`, else `propose`. In `safe` and `auto`, read every "wait for my OK" below as: apply it yourself if the mode allows (backup, verify, roll back on failure, ledger row), otherwise list it as a proposal. Hard stops always ask. At most `maxChangesPerRun` changes (default 3). End with a summary of what was applied, skipped and rolled back.

## Task

Plan first, then build: a tools/codemap command, a local SQLite index of this repository.

Requirements:
- Index only git-tracked files and store the database under out/ (git-ignored).
  Rebuild incrementally whenever a query runs and files have changed. A full build should
  take seconds, a query under about 1 s.
- Contents: types and members with line ranges for my languages (for example C#,
  GDScript, C++, TypeScript); scene, prefab and resource files; config and settings keys
  with their values; localisation ids and their text; shaders; shell and Python scripts;
  doc headings.
- Commands:
  - find <name|regex> [--kind ...] [--in <path>]: where something is defined.
  - outline <file>: the file's types and members with line ranges.
  - refs <name>: textual usages, grouped by file.
  - setting <key> and lang <id>: the line and value, plus code references.
  - tests <fragment>: matching test methods, for building test filters.
  - tree [<dir>] [--depth N]: files, lines and top types per directory.
  - brief <file>: reads a task or brief and prints the code locations it names, as
    a "Code locations" block to paste into a prompt.
  - --json and --limit N on every query.
- Use the standard library where possible (sqlite3, regex or tree-sitter if already
  installed). Don't add heavy dependencies without asking.
- Tests: a fixture repo with one file per language. Timing checks for build and query.

After it works, add a rule to the instructions and agent context: "find code with
tools/codemap first, then read only the ranges it prints". If I have a dispatch script for
another coding agent, make it run `codemap brief` on the brief and insert the result
into the prompt automatically. Re-run the usage audit after a week and fill in the
ledger row.

## Done when

planners and engineers use noticeably fewer exploration calls. The audit should show codemap calls replacing grep and read calls. If it doesn't, the rule isn't reaching the agents. Check the agent context files and the dispatch preamble.
