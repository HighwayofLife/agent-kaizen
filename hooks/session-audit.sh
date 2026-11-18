#!/usr/bin/env bash
# Claude runs this hook asynchronously. The scheduler owns the deadline and lock.
# --- host helper ---
case ${KAIZEN_HOST:-} in
    claude|codex|copilot) kaizen_host=$KAIZEN_HOST ;;
    *)
        if [[ -n ${COPILOT_PLUGIN_ROOT:-} ]]; then
            kaizen_host=copilot
        elif [[ -n ${PLUGIN_ROOT:-} ]]; then
            kaizen_host=codex
        else
            kaizen_host=claude
        fi
        ;;
esac
kaizen_skill() {
    if [[ $kaizen_host == codex ]]; then
        printf '$agent-kaizen:%s' "$1"
    else
        printf '/agent-kaizen:%s' "$1"
    fi
}
kaizen_context() {
    if [[ $kaizen_host == copilot ]]; then
        jq -n --arg c "$2" '{additionalContext:$c}'
    elif [[ $1 == SessionStart ]]; then
        jq -n --arg c "$2" '{hookSpecificOutput:{hookEventName:"SessionStart",additionalContext:$c}}'
    else
        jq -n --arg event "$1" --arg message "$2" '{hookSpecificOutput:{hookEventName:$event,additionalContext:$message}}'
    fi
}
# --- end host helper ---
if [[ -f ${CLAUDE_CONFIG_DIR:-$HOME/.claude}/agent-kaizen/host-trace/on ]]; then
    # shellcheck source=hooks/lib/trace.sh
    source "$(dirname "${BASH_SOURCE[0]}")/lib/trace.sh"
    kaizen_input=$(cat)
    kaizen_trace "$kaizen_input"
fi
exec </dev/null >/dev/null 2>&1
root=${CLAUDE_PLUGIN_ROOT:-${PLUGIN_ROOT:-}}
[ -n "$root" ] || exit 0
umask 077
if [[ $kaizen_host == copilot ]]; then
    python3 "$root/scripts/kaizen-scheduled" auto-audit &
    exit 0
fi
python3 "$root/scripts/kaizen-scheduled" auto-audit
exit 0
