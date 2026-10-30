---
name: review
description: "The recurring step: compare the newest audit with the ledger, keep or revert past changes, and propose the next improvements."
disable-model-invocation: true
argument-hint: "[propose|safe|auto|yolo|propose-only]"
---

# Review the latest audit and improve (the recurring step)

The part of the loop that repeats. Check whether past changes paid off, keep the ones that did, revert the ones that didn't, and pick the next improvements.

**Changes:** proposes changes, then implements the ones you approve.

**Autonomy:** follow `${CLAUDE_PLUGIN_ROOT}/docs/autonomy.md`. The mode comes from the skill argument (`propose`, `safe`, `auto` or `yolo`), else `docs/kaizen/config.json`, else `~/.claude/agent-kaizen.json`, else `propose`. In `safe` and `auto`, read every "wait for my OK" below as: apply it yourself if the mode allows (backup, verify, roll back on failure, ledger row), otherwise list it as a proposal. Hard stops always ask. At most `maxChangesPerRun` changes (default 3). End with a summary of what was applied, skipped and rolled back.

## Task

**Propose-only mode:** if the arguments say `propose-only` (the scheduled headless run uses this), do steps 1–4 but change nothing: write the result to `~/.claude/audits/review-<yyyy-mm-dd>.md` (or print it, if writing isn't allowed) and stop.


Review the newest usage audit (docs/kaizen/ or ~/.claude/audits/) against the one
before it and docs/kaizen/LEDGER.md.

1. For every ledger row without a measured effect: fill it in from the audits, then say
   keep, tune or revert. Record API-equivalent dollars alongside tokens when available.
   If a change made things worse or nobody is using it (for
   example a tool that agents never call), propose the fix: better wording where agents
   actually read it, a hook, or a revert.
2. List the 5 largest remaining costs and any new patterns since the last review.
3. Check that the rules are reaching the agents. In propose-only mode (no shell), use the
   newest token-audit report only (the per-agent Bash and tool sections; use Grep to count, e.g.
   codemap vs rg calls); never Read raw transcripts. Interactively, pick 3 recent subagent transcripts and
   check whether they followed the key rules (code map first, ranged reads, tools before
   tokens). If not, find out why: the rule may be missing from their context, or worded
   too weakly.
4. Propose the next 3 changes, ranked by expected saving per unit of effort, each with
   how we'll measure it. Prefer small, reversible changes.
   For `Repeated failures across sessions`, propose one short fact line per candidate in
   the project's CLAUDE.md only when the "worked instead" hint or code confirms the form
   (for example, "Run tests with `python -m pytest`"). Propose dropping it if later audits
   show the failure persists or the fact is stale. For `Stuck turns` with a large share of
   cost, propose fixing the cause: a brief, agent instructions, a missing check script or
   a guardrail, not a live judge.
Wait for my OK, implement the approved ones (each with a ledger row), and mark the audit
reviewed.

## Done when

a short list of keeps, reverts and next steps. Over a few rounds the ledger becomes a record of what actually works for your setup.
