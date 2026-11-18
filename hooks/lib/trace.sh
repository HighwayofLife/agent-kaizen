#!/usr/bin/env bash
# Sourced only when the host trace switch exists. Never affect hook output.
kaizen_trace() {
    (
        local payload=$1 dir=${CLAUDE_CONFIG_DIR:-${HOME:-}/.claude}/agent-kaizen/host-trace
        local ts env_names='' name line
        ts=$(date -u '+%Y-%m-%dT%H:%M:%SZ') || exit 0
        for name in CLAUDE_PLUGIN_ROOT CODEX_HOME COPILOT_HOME COPILOT_PLUGIN_ROOT KAIZEN_HOST PLUGIN_ROOT; do
            if [[ ${!name+x} ]]; then env_names+="${env_names:+,}\"$name\""; fi
        done
        if command -v jq >/dev/null 2>&1; then
            line=$(jq -cn --arg ts "$ts" --arg hook "${0##*/}" --arg host "${kaizen_host:-claude}" --argjson env "[$env_names]" --arg payload "$payload" '
                def safe: if . == null then null elif type == "string" and test("\\A[A-Za-z0-9_.:-]{1,64}\\z") then . else "<other>" end;
                ($payload | try fromjson catch {} | if type == "object" then . else {} end) as $p |
                {ts:$ts,hook:$hook,host:$host,event:(($p.hook_event_name // $p.hookEventName // $p.event) | safe),tool:(($p.tool_name // $p.toolName) | safe),keys:($p|keys|map(safe)),env:$env}') || exit 0
        else
            line="{\"ts\":\"$ts\",\"hook\":\"${0##*/}\",\"host\":\"$kaizen_host\",\"event\":null,\"tool\":null,\"keys\":null,\"env\":[$env_names],\"note\":\"jq missing\"}"
        fi
        printf '%s\n' "$line" >> "$dir/trace.jsonl"
    ) 2>/dev/null || :
}
