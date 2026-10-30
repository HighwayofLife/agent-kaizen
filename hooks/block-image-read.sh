#!/usr/bin/env bash
# PreToolUse(Read): guard images when an image agent is installed.
# ALLOW_IMAGE_READS=1 disables the guard; IMAGE_AGENTS lists names (default image-reader).
# Agent files are looked up in ${CLAUDE_CONFIG_DIR:-$HOME/.claude}/agents and
# .claude/agents in ${cwd:-$PWD} and its git root, where cwd comes from the hook input.
# Missing jq disables the guard with a stderr notice.
[[ "${ALLOW_IMAGE_READS:-0}" == 1 ]] && exit 0
command -v jq >/dev/null 2>&1 || { echo "jq missing: block-image-read disabled" >&2; exit 0; }
in=$(cat)
path=$(jq -r '.tool_input.file_path // empty' <<<"$in" 2>/dev/null)
shopt -s nocasematch
[[ "$path" =~ \.(png|jpe?g|gif|webp|bmp|tiff?|exr|heic)$ ]] || exit 0
cwd=$(jq -r '.cwd // empty' <<<"$in" 2>/dev/null)
names=${IMAGE_AGENTS:-image-reader}
top=$(git -C "${cwd:-$PWD}" rev-parse --show-toplevel 2>/dev/null)
found=0
for name in $names; do
    if [[ -f "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/agents/$name.md" || -f "${cwd:-$PWD}/.claude/agents/$name.md" ||
          ( -n "$top" && -f "$top/.claude/agents/$name.md" ) ]]; then
        found=1
        break
    fi
done
[[ "$found" == 1 ]] || exit 0
type=$(jq -r '.agent_type // "main"' <<<"$in" 2>/dev/null)
for allowed in $names; do [[ "$type" == "$allowed" ]] && exit 0; done
reason="Images are read by an image agent ($names), not in this context. Spawn it with the question and $path"
command -v codex-review >/dev/null 2>&1 && reason="$reason, or use codex-review look"
reason="$reason."
command -v magick >/dev/null 2>&1 && reason="$reason For sizes, formats or pixel diffs use magick identify / magick compare."
jq -n --arg reason "$reason" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$reason}}'
