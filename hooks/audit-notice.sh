#!/usr/bin/env bash
# SessionStart: notice an unreviewed audit at most once per day; never fail the session.
# AUDIT_DIR overrides the audits directory; CLAUDE_CONFIG_DIR selects the config directory.
# KAIZEN_NOTICE_ALL=1 also enables notices outside enrolled projects.
# Reads global enabled and global or project schedule from agent-kaizen config files.
emitted=0
trap '[ "$emitted" = 1 ] || printf "{}\n"' EXIT
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
audit_msg=
audit_marker=
if [ -n "$latest" ] && [ ! -e "${latest%.md}.reviewed" ]; then
    marker="${latest%.md}.noticed-$(date +%F)"
    if (set -o noclobber; : > "$marker") 2>/dev/null; then
        audit_marker=$marker
        extra=""
        [ -n "$proposal" ] && [ "$proposal" -nt "$latest" ] && extra=" A propose-only review is ready too: $proposal."
        audit_msg="An unreviewed usage audit exists: $latest.$extra When there is a pause, run /agent-kaizen:review (read the headline and flagged sections, not the whole file), propose changes to the user, then touch ${latest%.md}.reviewed."
    fi
fi

experiment_msg=
experiment_marker=
plugin_root=${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd)}
checker=$plugin_root/scripts/experiment-check
if { [ -n "$root" ] || [ -n "$key" ]; } && command -v python3 >/dev/null 2>&1 && [ -f "$checker" ]; then
    [ -n "$root" ] || root=$start
    checksum=$(printf '%s' "${key:-$root}" | cksum)
    checksum=${checksum%% *}
    marker="$dir/experiments-$checksum.noticed-$(date +%F)"
    check_args=()
    [ -n "$key" ] && check_args=(--checks --state-file "$dir/projects/$key/checks.json")
    if [ -n "$checksum" ] && [ ! -e "$marker" ]; then
        if command -v timeout >/dev/null 2>&1; then
            output=$(timeout -k 1 "${KAIZEN_NOTICE_TIMEOUT:-10}" python3 "$checker" --project "$root" "${check_args[@]}" 2>/dev/null)
            status=$?
        elif command -v gtimeout >/dev/null 2>&1; then
            output=$(gtimeout -k 1 "${KAIZEN_NOTICE_TIMEOUT:-10}" python3 "$checker" --project "$root" "${check_args[@]}" 2>/dev/null)
            status=$?
        else
            output=$(
                tmp=$(mktemp) || exit 2
                python3 "$checker" --project "$root" "${check_args[@]}" >"$tmp" 2>/dev/null &
                pid=$!
                (sleep "${KAIZEN_NOTICE_TIMEOUT:-10}"; kill "$pid" 2>/dev/null; sleep 1; kill -KILL "$pid" 2>/dev/null) >/dev/null 2>&1 &
                watchdog=$!
                wait "$pid" 2>/dev/null
                status=$?
                kill "$watchdog" 2>/dev/null
                wait "$watchdog" 2>/dev/null
                head -n 12 "$tmp"
                rm -f "$tmp"
                exit "$status"
            )
            status=$?
        fi
        if [ "$status" -eq 1 ] && mkdir -p "$dir" 2>/dev/null &&
            (set -o noclobber; : > "$marker") 2>/dev/null; then
            experiment_marker=$marker
            output=$(printf '%s\n' "$output" | head -n 12)
            experiment_msg="Experiments need attention in this project (docs/kaizen/LEDGER.md):
$output
When there is a pause, run /agent-kaizen:review."
        fi
    fi
fi

msg=$audit_msg
if [ -n "$experiment_msg" ]; then
    msg="${msg:+$msg

}$experiment_msg"
fi
[ -n "$msg" ] || exit 0
out=$(jq -n --arg c "$msg" '{hookSpecificOutput:{hookEventName:"SessionStart",additionalContext:$c}}')
if [ -z "$out" ]; then
    [ -n "$audit_marker" ] && rm -f "$audit_marker"
    [ -n "$experiment_marker" ] && rm -f "$experiment_marker"
    exit 0
fi
printf '%s\n' "$out"
emitted=1
exit 0
