#!/usr/bin/env bash
# Nudge the main session after repeated Bash calls within one user turn.
# PostToolUse and PostToolUseFailure count a call; UserPromptSubmit resets the count.
# KAIZEN_BASH_BURST=N nudges every N calls (default 8; non-numeric uses 8); 0 turns the hook off.
# enabled=false in ${CLAUDE_CONFIG_DIR:-$HOME/.claude}/agent-kaizen.json also turns it off.
# State: one byte per call appended to a file in a private per-user temp directory.
[[ ${KAIZEN_BASH_BURST-} == 0 ]] && exit 0
command -v jq >/dev/null 2>&1 || exit 0
config=${CLAUDE_CONFIG_DIR:-${HOME-}/.claude}/agent-kaizen.json
if [[ -r $config ]]; then
    settings=$(<"$config")
    if [[ $settings =~ \"enabled\"[[:space:]]*:[[:space:]]*false ]]; then
        [[ $(jq -r '.enabled == false' <<<"$settings" 2>/dev/null) == true ]] && exit 0
    fi
fi
in=$(cat)
IFS='|' read -r event tool agent interrupt session < <(jq -r 'select(type == "object") |
    [(.hook_event_name | strings // "-"), (.tool_name | strings // "-"), (has("agent_id") | tostring),
     (.is_interrupt == true | tostring), (.session_id | strings | select(length > 0) // "")] | join("|")' <<<"$in" 2>/dev/null)
session=${session//[^A-Za-z0-9_-]/_}
[[ -n $session ]] || exit 0
dir=${TMPDIR:-/tmp}/kaizen-bash-burst-$UID
if [[ -L $dir || ( -e $dir && ! ( -d $dir && -O $dir ) ) ]]; then exit 0; fi
case "$event" in
    UserPromptSubmit)
        [[ -e $dir/$session ]] && : > "$dir/$session" 2>/dev/null
        ;;
    PostToolUse|PostToolUseFailure)
        [[ $tool == Bash && $agent == false && $interrupt == false ]] || exit 0
        threshold=${KAIZEN_BASH_BURST:-8}
        [[ $threshold =~ ^[1-9][0-9]*$ && ${#threshold} -le 6 ]] || threshold=8
        [[ -d $dir ]] || mkdir -m 700 -- "$dir" 2>/dev/null   # a parallel call may win the race
        [[ -d $dir && ! -L $dir && -O $dir ]] || exit 0
        printf x >> "$dir/$session" 2>/dev/null || exit 0
        count=$(wc -c < "$dir/$session" 2>/dev/null)
        count=${count//[^0-9]/}
        [[ -n $count && ${#count} -le 9 ]] || exit 0
        count=$((10#$count))
        if (( count % threshold == 0 )); then
            message="$count Bash calls this turn. Chain the remaining steps into one command or script that prints a summary, or hand the investigation to a cheaper read-only subagent."
            jq -n --arg event "$event" --arg message "$message" '{hookSpecificOutput:{hookEventName:$event,additionalContext:$message}}'
        fi
        ;;
esac
exit 0
