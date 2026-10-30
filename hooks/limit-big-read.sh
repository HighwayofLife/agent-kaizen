#!/usr/bin/env bash
# PreToolUse(Read): a whole-file Read of a big code, data, scene or log file stays in context
# and is re-sent on every later turn. Above MAX lines, require a line range (offset/limit).
# Escape hatch: any Read with an explicit limit passes, so an agent that really needs the
# whole file re-reads it with limit=<line count>.
MAX=${READ_GUARD_MAX_LINES:-400}
in=$(cat)
path=$(jq -r '.tool_input.file_path // empty' <<<"$in" 2>/dev/null)
limit=$(jq -r '.tool_input.limit // empty' <<<"$in" 2>/dev/null)
[[ -n "$path" && -z "$limit" && -f "$path" ]] || exit 0
shopt -s nocasematch
[[ "$path" =~ \.(cs|py|sh|js|mjs|cjs|ts|tsx|jsx|go|rs|java|kt|swift|c|cc|cpp|h|hpp|gd|lua|rb|php|uss|uxml|css|scss|html|shader|hlsl|glsl|cginc|compute|json|ya?ml|toml|xml|csproj|asset|prefab|unity|mat|tscn|tres|log|csv|sql)$ ]] || exit 0
lines=$(wc -l <"$path" 2>/dev/null | tr -d ' ')
[[ "$lines" =~ ^[0-9]+$ ]] && (( lines > MAX )) || exit 0
hint="rg -n PATTERN $path"
[[ -x tools/codemap ]] && hint="tools/codemap outline $path (or $hint)"
jq -n --arg p "$path" --arg n "$lines" --arg h "$hint" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",
 permissionDecisionReason:($p + " has " + $n + " lines; read a range, not the whole file. Find the range with `" + $h + "`, then Read with offset and limit (at most ~300 lines). JSON: jq. YAML: yq. Logs: rg / tail. If you really need the whole file (e.g. reviewing or rewriting all of it), Read it again with offset 1 and limit " + $n + "; that is allowed.")}}'
