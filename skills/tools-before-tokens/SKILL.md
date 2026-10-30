---
name: tools-before-tokens
description: "Make every agent use deterministic CLI tools (rg, fd, ast-grep, jq, yq, scripts) before spending model tokens."
disable-model-invocation: true
argument-hint: "[propose|safe|auto|yolo]"
---

# Tools before tokens

Anything a deterministic tool can do (search, count, parse, transform, measure) is done by the tool, not by a model reading and reasoning.

**Changes:** installs CLI tools, adds instruction rules and small scripts, after you approve.

**Autonomy:** follow `${CLAUDE_PLUGIN_ROOT}/docs/autonomy.md`. The mode comes from the skill argument (`propose`, `safe`, `auto` or `yolo`), else `docs/kaizen/config.json`, else `~/.claude/agent-kaizen.json`, else `propose`. In `safe` and `auto`, read every "wait for my OK" below as: apply it yourself if the mode allows (backup, verify, roll back on failure, ledger row), otherwise list it as a proposal. Hard stops always ask. At most `maxChangesPerRun` changes (default 3). End with a summary of what was applied, skipped and rolled back.

## Task

Make every agent (Claude and Codex) use deterministic tools before spending model tokens.

1. Check what is installed: rg, fd, ast-grep, jq, yq, shellcheck, a formatter for my
   languages, and media tools if this project has assets (ffprobe/ffmpeg, ImageMagick,
   gltf-transform). Propose install commands for the missing ones. Don't install anything
   without my OK.
2. Add a compact "tools before tokens" rule to the core instructions (CLAUDE.md and
   AGENTS.md), about 6 lines:
   - Find code with rg, fd, ast-grep or a code map, then read only the line ranges that matter.
   - Parse JSON and YAML with jq or yq. Count with wc, sort | uniq -c, or awk.
   - Do bulk or mechanical edits with ast-grep, sed or a script, then review the diff.
   - Send long logs and command output to a file; read them with tail or rg, never whole.
   - Measure media with tools; models judge only what tools can't.
   - When a manual step recurs, write a script for it.
3. Use the usage audit (docs/kaizen/) and recent transcripts to find the 5 steps
   agents most often do by hand: reading test results, summarising logs, finding a
   setting's value, checking asset budgets, and so on. For each, propose a small script
   under tools/ with a one-line usage, and list it in the instructions.
4. If agents fetch the same web pages again and again (research, docs), propose a cached
   fetch script: it stores each page once as plain text, and later searches grep the
   cached copy instead of refetching.

Show the plan, wait for my OK, then build the scripts with tests. Add ledger rows.

## Done when

fewer large reads in the next audit, and tool output in place of long agent summaries.
