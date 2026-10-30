#!/usr/bin/env bash
# SessionStart (matcher "compact"): after a compaction, point the session back at on-disk
# state (git, plans) instead of re-deriving it from a lossy summary. Never fails the session.
cwd=$(jq -r '.cwd // empty' 2>/dev/null); cd "${cwd:-$PWD}" 2>/dev/null || exit 0
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0
plans_glob=${PLANS_GLOB:-docs/plans/*/plan.md}
{
  echo "Context was just compacted. Recover state from disk, not memory:"
  echo "- Branch: $(git branch --show-current); last commits:"; git log --oneline -5 2>/dev/null | sed 's/^/    /'
  echo "- Uncommitted: $(git status --porcelain | wc -l | tr -d ' ') paths"
  [ "$(git worktree list | wc -l)" -gt 1 ] && { echo "- Worktrees:"; git worktree list | sed 's/^/    /'; }
  # shellcheck disable=SC2086
  plans=$(ls -t $plans_glob 2>/dev/null | head -3)
  [ -n "$plans" ] && { echo "- Most recently changed plans (read their status tables before launching work):"; echo "$plans" | sed 's/^/    /'; }
  echo "- Background agents may still be running: wait for their notifications before relaunching the same task."
} | jq -Rs '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: .}}'
