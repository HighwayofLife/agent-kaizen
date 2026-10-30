#!/usr/bin/env bash
# SessionStart: notice an unreviewed audit at most once per day; never fail the session.
# AUDIT_DIR overrides the audits directory; CLAUDE_CONFIG_DIR selects the config directory.
# KAIZEN_NOTICE_ALL=1 also enables notices outside enrolled projects.
# Reads global enabled and global or project schedule from agent-kaizen config files.
command -v jq >/dev/null 2>&1 || exit 0
home=${CLAUDE_CONFIG_DIR:-$HOME/.claude}
dir=${AUDIT_DIR:-$home/audits}
cwd=$(jq -r '.cwd // empty' 2>/dev/null)
start=$(cd "${cwd:-$PWD}" 2>/dev/null && pwd -P) || exit 0

root=$start
while [ ! -d "$root/docs/kaizen" ]; do
    [ "$root" = / ] && { root=; break; }
    root=${root%/*}
    [ -n "$root" ] || root=/
done

key=
p=$start
while :; do
    key=$(jq -r --arg p "$p" '.projects[$p] | strings' "$dir/projects/index.json" 2>/dev/null)
    # A key is one folder name under projects/; ignore anything that could leave it.
    case $key in */*|.*) key= ;; esac
    [ -n "$key" ] && break
    [ "$p" = / ] && break
    p=${p%/*}
    [ -n "$p" ] || p=/
done
[ -n "$root" ] || [ -n "$key" ] || [ "${KAIZEN_NOTICE_ALL:-0}" = 1 ] || exit 0

[ "$(jq -r '.enabled == false' "$home/agent-kaizen.json" 2>/dev/null)" = true ] && exit 0
schedule=
if [ -n "$root" ]; then
    schedule=$(jq -r 'select(.schedule == "active" or .schedule == "always" or .schedule == "off") | .schedule' "$root/docs/kaizen/config.json" 2>/dev/null)
fi
if [ -z "$schedule" ]; then
    schedule=$(jq -r 'select(.schedule == "active" or .schedule == "always" or .schedule == "off") | .schedule' "$home/agent-kaizen.json" 2>/dev/null)
fi
[ "$schedule" = off ] && exit 0

latest=
proposal=
if [ -n "$key" ]; then
    latest=$(ls -t "$dir/projects/$key"/token-audit-*.md 2>/dev/null | head -1)
    if [ -n "$latest" ]; then
        proposal=$(ls -t "$dir/projects/$key"/cycle-*.md 2>/dev/null | head -1)
    fi
fi
if [ -z "$latest" ]; then
    while IFS= read -r report; do
        [ -n "$report" ] || continue
        scope=$(grep -m1 '^<!-- token-audit-scope ' "$report")
        if [ -z "$scope" ]; then
            latest=$report
            proposal=$(ls -t "$dir"/cycle-*.md 2>/dev/null | head -1)
            break
        fi
        scope=${scope#'<!-- token-audit-scope '}
        scope=${scope%' -->'}
        if printf '%s\n' "$scope" | jq -e '.project == null and .cwd == null and (.project_dirs | length) == 0' >/dev/null 2>&1; then
            latest=$report
            break
        fi
    done < <(ls -t "$dir"/token-audit-*.md 2>/dev/null)
fi
[ -n "$latest" ] && [ ! -e "${latest%.md}.reviewed" ] || exit 0
marker="${latest%.md}.noticed-$(date +%F)"
[ -e "$marker" ] && exit 0
extra=""
[ -n "$proposal" ] && [ "$proposal" -nt "$latest" ] && extra=" A propose-only review is ready too: $proposal."
msg="An unreviewed usage audit exists: $latest.$extra When there is a pause, run /agent-kaizen:review (read the headline and flagged sections, not the whole file), propose changes to the user, then touch ${latest%.md}.reviewed."
out=$(jq -n --arg c "$msg" '{hookSpecificOutput:{hookEventName:"SessionStart",additionalContext:$c}}') || exit 0
[ -n "$out" ] || exit 0
touch "$marker" 2>/dev/null
printf '%s\n' "$out"
