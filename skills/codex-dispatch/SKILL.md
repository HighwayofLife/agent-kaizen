---
name: codex-dispatch
description: "Hand coding work to the Codex CLI through a dispatch script (checks, resume rounds, short report) instead of a relay subagent."
disable-model-invocation: true
argument-hint: "[propose|safe|auto|yolo]"
---

# Hand coding to Codex by script, not by a wrapper agent

If you use OpenAI Codex as well as Claude, send it work through a script that runs it, runs the checks, loops failures back and prints a short report. A Claude subagent that only relays Codex output costs a full agent context for nothing.

**Changes:** installs the bundled scripts and adds a CLAUDE.md section, after you approve.

**Autonomy:** follow `${CLAUDE_PLUGIN_ROOT}/docs/autonomy.md`. The mode comes from the skill argument (`propose`, `safe`, `auto` or `yolo`), else `docs/kaizen/config.json`, else `agent-kaizen.json` in your Claude config dir (`$CLAUDE_CONFIG_DIR` or `~/.claude`), else `propose`. In `safe` and `auto`, read every "wait for my OK" below as: apply it yourself if the mode allows (backup, verify, roll back on failure, ledger row), otherwise list it as a proposal. Hard stops always ask. At most `maxChangesPerRun` changes (default 3). End with a summary of what was applied, skipped and rolled back.

## Task

I use the Codex CLI for coding. Check how work reaches it now (look for subagents that
run `codex exec`, and the usage audit's spawn counts for them).

Install the bundled toolkit instead of writing one. Run
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kaizen-link --apply` (it links the scripts, or
copies them when the plugin sits in a cache), then confirm `codex-dispatch --help` and
`codex-review --help` run. Show me what it will do before you apply it.

1. `codex-dispatch [-m MODEL] [-e EFFORT] [-C DIR] [-k CHECK]... [-p engineer|planner|none]
   [-r ROUNDS] [-i IMAGE] [-o OUTDIR] [--disable-mcp NAME] [--allow-no-change]
   [--check-timeout SECONDS] [--codex-timeout SECONDS] [--resume THREAD_ID] BRIEF.md`
   - Prepends a short role preamble to the brief, runs `codex exec --json` in DIR and
     captures the thread id.
   - Runs each `-k` check outside the Codex sandbox (the sandbox may have no network).
   - On a failed check, resumes the same thread with the failing output trimmed to the
     relevant lines, for at most `-r` rounds.
   - An engineer run must change files. Pass `--allow-no-change` when none is expected.
   - A check is killed after `--check-timeout` seconds (default 1800; 0 = no limit). A
     Codex run is killed after `--codex-timeout` seconds (default 0 = no limit).
   - Resume rounds re-run only the checks that failed, then all checks once; check commands see `DISPATCH_ROUND` and `DISPATCH_PASS`. Give `-k` the narrowest check (affected/filtered tests); full suites run at the project's batch cadence. A repo may route check commands through an executable `tools/rewrite_check` (argv[1] = the command, stdout = its replacement, empty = unchanged; worktrees fall back to the main checkout's copy). `DISPATCH_PASS` is `initial`, `retry`, or `final`.
   - Writes full logs under out/dispatch/<timestamp>/ and prints a short report ending in
     `STATUS: DONE`, `STATUS: CHECKS FAILING` or `STATUS: CODEX FAILED`.
2. `codex-review diff | plan PLAN_FILE | visual --criteria FILE IMG... | look --question TEXT IMG...`,
   each with `[-m MODEL]`: a read-only review of the diff, of a plan file, or of images.
   Prints findings and ends with `STATUS: DONE` or `STATUS: REVIEW FAILED`.
3. A Codex server error, or a run that ends with no final message, is retried once
   automatically and is not counted as a failure.

Flags and environment variables are listed in `scripts/README.md` and by `--help`.

Then update CLAUDE.md so the main session runs these as background shell commands instead
of spawning wrapper agents, and keep any wrapper agents only as a fallback. Add a ledger row.

## Bundled resources

Working versions are bundled in `${CLAUDE_PLUGIN_ROOT}/scripts/` (`codex-dispatch`, `codex-run`, `codex_common.py`, `codex-review`, `dispatch-status`, `preambles/`, `prompts/`; see `scripts/README.md`). `kaizen-link` installs them; adapt them rather than writing new ones.

## Done when

fewer subagent spawns, short reports that fit in a few lines, and fix rounds that resume the same Codex thread instead of starting from scratch.
