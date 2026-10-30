#!/usr/bin/env bash
# SessionStart (startup|resume): short notice when the newest usage audit has not been reviewed.
# - Only token-audit-*.md reports count (proposal files like cycle-*.md are mentioned, not counted).
# - Only in projects that use the loop (have docs/kaizen/), unless KAIZEN_NOTICE_ALL=1.
# - At most once per day per audit (a .noticed-<date> marker). Never fails the session.
dir=${AUDIT_DIR:-$HOME/.claude/audits}
cwd=$(jq -r '.cwd // empty' 2>/dev/null)
[[ "${KAIZEN_NOTICE_ALL:-0}" == 1 || -d "${cwd:-$PWD}/docs/kaizen" ]] || exit 0
latest=$(ls -t "$dir"/token-audit-*.md 2>/dev/null | head -1)
[ -n "$latest" ] && [ ! -e "${latest%.md}.reviewed" ] || exit 0
marker="${latest%.md}.noticed-$(date +%F)"
[ -e "$marker" ] && exit 0
touch "$marker" 2>/dev/null
proposal=$(ls -t "$dir"/cycle-*.md 2>/dev/null | head -1)
extra=""
[ -n "$proposal" ] && [ "$proposal" -nt "$latest" ] && extra=" A propose-only review is ready too: $proposal."
msg="An unreviewed usage audit exists: $latest.$extra When there is a pause, run /agent-kaizen:review (read the headline and flagged sections, not the whole file), propose changes to the user, then touch ${latest%.md}.reviewed."
jq -n --arg c "$msg" '{hookSpecificOutput:{hookEventName:"SessionStart",additionalContext:$c}}'
