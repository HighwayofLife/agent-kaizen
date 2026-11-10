#!/usr/bin/env bash
# PreToolUse(Read): require a range for files above READ_GUARD_MAX_LINES (default 400).
# READ_GUARD_EXTENSIONS (non-empty) replaces the default exempt extension regex, case-insensitively:
# md|markdown|mdx|rst|pdf|png|jpe?g|gif|webp|bmp|tiff?|ico|heic|exr|zip|gz|tgz|tar|bz2|xz|7z|jar|wasm|bin|so|dylib|dll|exe|o|a|class|woff2?|ttf|otf|mp3|mp4|mov|wav|ogg
# Any Read with an explicit limit passes, including a whole-file re-read with limit=<line count>.
# A Read with only an offset passes when the lines from that offset to the end are within the threshold.
# Missing jq disables the guard with a stderr notice.
command -v jq >/dev/null 2>&1 || { echo "jq missing: limit-big-read disabled" >&2; exit 0; }
MAX=${READ_GUARD_MAX_LINES:-400}
in=$(cat)
IFS='|' read -r limit offset path < <(jq -r '[(.tool_input.limit // ""), (.tool_input.offset // ""), (.tool_input.file_path // "")] | join("|")' <<<"$in" 2>/dev/null)
[[ -n "$path" && -z "$limit" && -f "$path" ]] || exit 0
shopt -s nocasematch
exempt=${READ_GUARD_EXTENSIONS:-md|markdown|mdx|rst|pdf|png|jpe?g|gif|webp|bmp|tiff?|ico|heic|exr|zip|gz|tgz|tar|bz2|xz|7z|jar|wasm|bin|so|dylib|dll|exe|o|a|class|woff2?|ttf|otf|mp3|mp4|mov|wav|ogg}
[[ "$path" =~ \.($exempt)$ ]] 2>/dev/null && exit 0
lines=$(wc -l <"$path" 2>/dev/null | tr -d ' ')
[[ "$lines" =~ ^[0-9]+$ ]] && (( lines > MAX )) || exit 0
if [[ "$offset" =~ ^[0-9]{1,9}$ ]]; then
    offset=$((10#$offset))
    (( offset > 0 )) || offset=1
    (( lines - offset + 1 <= MAX )) && exit 0
fi
printf -v quoted '%q' "$path"
hint="grep -n PATTERN $quoted"
command -v rg >/dev/null 2>&1 && hint="rg -n PATTERN $quoted"
[[ -x tools/codemap ]] && hint="tools/codemap outline $quoted (or $hint)"
jq -n --arg p "$path" --arg n "$lines" --arg h "$hint" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",
 permissionDecisionReason:($p + " has " + $n + " lines; read a range, not the whole file. Find the range with `" + $h + "`, then Read with offset and limit (at most ~300 lines). If you really need the whole file (e.g. reviewing or rewriting all of it), Read it again with offset 1 and limit " + $n + "; that is allowed.")}}'
