# Planner brief: port the unlanded 0.6.0 "friction" work onto current main (target release 0.13.0)

Sol reason: the plan covers a PostToolUse sampler hook (concurrency, atomic appends, hook deadlines), `allow-rule` and `host-fix` (they change permissions and edit host files, so they are security-sensitive), and a port across six releases of diverged code (0.6.0 → 0.11.0). It needs a design judgment per feature, not a pattern copy.

## Goal

The owner wants the friction features shipped. Write `plan.md` and one brief per packet in this directory (`docs/plans/2026-11-17-friction-port/`, repo root = this agent-kaizen checkout). Do not change code and do not commit.

## Background

- **The original plan** is in `out/plans/2026-10-30-friction-audit/`: `plan.md` (packet table at about line 200), `decisions.md` (the owner's decisions D1–D4: autonomy relaxations, merged-worktree removal, local kaizen commits, exact allow rules), `research.md` (hook facts), the review files and `briefs/`. Read `decisions.md` and the plan's Summary, Approach and packet table first.
- **The implementation** is on local branches `wt/b wt/p01 … wt/p15`, also tagged `archive/friction-0.6/<name>`. All of them branch from `599810c` (0.5.0). Commits are WIP and stacked: p10 contains most of the others. Use `git diff 599810c wt/<name> --stat` and `git show` to read them, never `git checkout` or switch branches in this checkout.
  - p01: Claude tool-call timing and the `friction` extract key.
  - p02: friction-catalog.json.
  - p03: config keys.
  - p04: Codex timeline and contention.
  - p05: host-probe.
  - p06: host-actions store.
  - p07: async sampler hook.
  - p08a: runner wiring.
  - p08b: scheduled allow rules and installer (partial).
  - p09: notice line for open host actions.
  - p10: friction skill (partial).
  - p12: host-fix with undo.
  - p13: allow-rule.
  - p14: worktree-prune.
  - p15: `kaizen-backup commit`.
  - A read-only review on 2026-11-17 found 13 complete but unlanded and 2 partial (p08b, p10).
- **Main moved on.** Releases 0.6.0–0.11.0 landed after `599810c` (see `CHANGELOG.md`).
  - token-audit, kaizen-scheduled, the hooks and the config were heavily changed.
  - Main now has `hooks/bash-burst.sh` (PostToolUse/PostToolUseFailure on Bash), `hooks/session-audit.sh`, `hooks/tier-guard.sh`, `scripts/kaizen-doctor`, `scripts/kaizen-scan`, `scripts/usage-db`, a format canary in token-audit, `dispatch-status` (which reports dirty worktrees), a context budget (`tools/context_budget.py`, `tools/context-budget.json`) and the `undo` skill.
  - Expect conflicts everywhere. Cherry-picking whole branches is probably wrong; decide per feature.
- **A parallel plan** in `docs/plans/2026-11-17-multi-host/` (another session; read its `plan.md`, do not edit it) targets 0.12.0 and edits `hooks/*`, `hooks/hooks.json`, the skill preambles, `scripts/kaizen-doctor`, script messages, CI and README. The friction plan lands after it. Name every file both plans touch, and say which packets must wait for 0.12.0 or rebase onto it.

## What the plan must decide

For each original feature, give one verdict with a reason from the current code:
- **port** (reuse the branch code, adapted);
- **rewrite** (same goal, new code on today's structure);
- **merge into an existing feature** (for example the sampler into `bash-burst.sh`, or the worktree flags into `dispatch-status`);
- **drop** (superseded or not worth it).

The owner's intent is to include whatever is useful, so dropping needs a concrete reason.

Then:
- Order the packets into groups that can run in parallel.
- Keep each packet under about 400 changed lines.
- Give every packet:
  - a risk tag (low/normal/high);
  - a model (Terra medium by default; Sol medium or high only with a `Sol reason:` line);
  - exact narrow check commands (`python3 -m unittest discover -s tests -p 'test_x.py'`, `shellcheck -S warning …`, `python3 tools/context_budget.py --root .`);
  - a `Changelog:` line.
- Mark `allow-rule`, `host-fix` and the scheduled-permission parts for a security review before landing.
- Keep the zero-token rule: collection is deterministic and the LLM reads only the prepared inputs.
- End the plan with:
  - a docs and release packet for 0.13.0 (CHANGELOG, version, README, CI file lists);
  - a real-input gate packet that runs each new command on a real install and records the output.
- Add a **Research needed** list for any Claude Code or Codex fact you could not confirm locally, for example current PostToolUse `duration_ms` availability.

## Constraints

- **Public repo.** No personal paths, emails, project names or machine details in any file (`tests/test_repo.py` enforces home-path bans).
- **Python 3.9 support.** Stdlib only.
- Every packet keeps `tools/ci-local --python 3.9` green, and its brief names the tests that pin config output (`tests/test_runner.py`) when it adds a config key. Lesson from 0.11: a new key broke runner tests that the packet did not run.
- Briefs stand alone: goal, files and line ranges in today's code, what to reuse from which `wt/*` branch (by `git show wt/pNN:path`), acceptance criteria, checks, and scope limits.

## Report

Reply in 20 lines or fewer:
- the per-feature verdict table;
- the packet count by model;
- the files shared with the multi-host plan;
- any decision that needs the owner, with your recommendation.
