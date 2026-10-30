---
name: codex-dispatch
description: "Hand coding work to the Codex CLI through a dispatch script (checks, resume rounds, short report) instead of a relay subagent."
disable-model-invocation: true
argument-hint: "[propose|safe|auto|yolo]"
---

# Hand coding to Codex by script, not by a wrapper agent

If you use OpenAI Codex as well as Claude, send it work through a script that runs it, runs the checks, loops failures back and prints a short report. A Claude subagent that only relays Codex output costs a full agent context for nothing.

**Changes:** creates scripts, their tests and a CLAUDE.md section, after you approve.

**Autonomy:** follow `${CLAUDE_PLUGIN_ROOT}/docs/autonomy.md`. The mode comes from the skill argument (`propose`, `safe`, `auto` or `yolo`), else `docs/kaizen/config.json`, else `~/.claude/agent-kaizen.json`, else `propose`. In `safe` and `auto`, read every "wait for my OK" below as: apply it yourself if the mode allows (backup, verify, roll back on failure, ledger row), otherwise list it as a proposal. Hard stops always ask. At most `maxChangesPerRun` changes (default 3). End with a summary of what was applied, skipped and rolled back.

## Task

I use the Codex CLI for coding. Check how work reaches it now (look for subagents that
run `codex exec`, and the usage audit's spawn counts for them).

Build a small dispatch toolkit, with tests, in ~/.claude/bin/ (or tools/ if I prefer it
in the repo):

1. codex-dispatch [-m MODEL] [-e EFFORT] [-C DIR] [-k CHECK]... [-p engineer|planner]
   [--resume THREAD_ID] BRIEF.md
   - Prepends a short role preamble (from preambles/<p>.md) to the brief.
   - Runs `codex exec --json` non-interactively in DIR, and captures the thread id.
   - Then runs each -k check command outside the Codex sandbox (the sandbox may have no
     network, and no engine or editor).
   - On a failed check, resumes the same thread (`codex exec resume <id>`) with the
     failing output trimmed to the relevant lines. At most 2 rounds. Retry only failed
     checks; once they pass, confirm the skipped checks. Checks receive `DISPATCH_ROUND`
     and `DISPATCH_PASS` (`initial`, `retry`, or `final`).
   - Writes full logs under out/dispatch/<timestamp>/ and prints at most 25 lines:
     model, thread id, Codex's summary, git diff --stat, each check PASS/FAIL, and
     STATUS: DONE | FAILED | BLOCKED.
2. codex-review diff | plan DIR | visual --criteria FILE IMG... | look --question TEXT IMG... [-m MODEL]: a read-only review of
   uncommitted changes, of a plan directory, or of images. Prints findings and a verdict
   line.
3. Treat a Codex server error, or a run that ends with no final message, as retryable
   (one automatic retry) and not as a failure.

Then update CLAUDE.md so the main session runs these as background shell commands instead
of spawning wrapper agents, and keep any wrapper agents only as a fallback. Show me the
scripts and tests before installing them. Add a ledger row.

## Bundled resources

Working versions are bundled in `${CLAUDE_PLUGIN_ROOT}/scripts/` (`codex-dispatch`, `codex-run`, `codex_common.py`, `codex-review`, `dispatch-status`, `preambles/`, `prompts/`; see `scripts/README.md`). Install them all with `cp -R ${CLAUDE_PLUGIN_ROOT}/scripts/. ~/.claude/bin/` and adapt them, rather than writing new ones.

## Done when

fewer subagent spawns, short reports that fit in a few lines, and fix rounds that resume the same Codex thread instead of starting from scratch.
