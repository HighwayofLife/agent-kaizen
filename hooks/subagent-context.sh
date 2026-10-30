#!/usr/bin/env bash
# SubagentStart: give a custom subagent only the project rules for its role, instead of the
# whole CLAUDE.md. Reads <repo>/.claude/agent-context/common.md plus one role file.
# Role lookup: <repo>/.claude/agent-context/roles.conf lines "agent-type=role"
# (e.g. "verifier=review"); else <agent-type>.md if present. Never fails the spawn.
in=$(cat)
type=$(jq -r '.agent_type // empty' <<<"$in" 2>/dev/null)
cwd=$(jq -r '.cwd // empty' <<<"$in" 2>/dev/null)
[ -n "$type" ] || exit 0
root=$(git -C "${cwd:-$PWD}" rev-parse --show-toplevel 2>/dev/null) || exit 0
dir="$root/.claude/agent-context"
[ -d "$dir" ] || exit 0
role=""
[ -f "$dir/roles.conf" ] && role=$(awk -F= -v t="$type" '$1==t {print $2; exit}' "$dir/roles.conf")
[ -z "$role" ] && [ -f "$dir/$type.md" ] && role="$type"
[ -n "$role" ] || exit 0   # unlisted (e.g. built-in) agents load CLAUDE.md themselves
ctx=""
for f in "$dir/common.md" "$dir/$role.md"; do [ -f "$f" ] && ctx+="$(cat "$f")"$'\n\n'; done
[ -n "$ctx" ] || exit 0
jq -n --arg c "Project context for $type:"$'\n\n'"$ctx" '{hookSpecificOutput:{hookEventName:"SubagentStart",additionalContext:$c}}'
