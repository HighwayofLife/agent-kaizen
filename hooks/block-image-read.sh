#!/usr/bin/env bash
# PreToolUse(Read): images stay in context and are re-sent every turn, so only designated
# image agents read them. Allowed agent types: IMAGE_AGENTS (space-separated, default "image-reader").
# Escape hatch: set ALLOW_IMAGE_READS=1 in the environment to disable the guard.
[[ "${ALLOW_IMAGE_READS:-0}" == 1 ]] && exit 0
in=$(cat)
path=$(jq -r '.tool_input.file_path // empty' <<<"$in" 2>/dev/null)
shopt -s nocasematch
[[ "$path" =~ \.(png|jpe?g|gif|webp|bmp|tiff?|exr|heic)$ ]] || exit 0
type=$(jq -r '.agent_type // "main"' <<<"$in" 2>/dev/null)
for allowed in ${IMAGE_AGENTS:-image-reader}; do [[ "$type" == "$allowed" ]] && exit 0; done
jq -n --arg p "$path" --arg a "${IMAGE_AGENTS:-image-reader}" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",
 permissionDecisionReason:("Images are read by an image agent (" + $a + "), not in this context. Spawn it with the question and " + $p + ", or use a review script (e.g. codex-review look). For sizes, formats or pixel diffs use `magick identify` / `magick compare`.")}}'
