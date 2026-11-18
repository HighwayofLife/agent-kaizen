#!/usr/bin/env bash
trap '' PIPE
# SessionStart: show daily audit, experiment and usage regression notices; never fail the session.
# AUDIT_DIR overrides the audits directory; CLAUDE_CONFIG_DIR selects the config directory.
# KAIZEN_NOTICE_ALL=1 also enables notices outside enrolled projects.
# Reads global enabled and global or project schedule from agent-kaizen config files.
emitted=0
trap '[ "$emitted" = 1 ] || printf "{}\n"' EXIT
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
        audit_msg="An unreviewed usage audit exists: $latest.$extra When there is a pause, run $(kaizen_skill review) (read the headline and flagged sections, not the whole file), propose changes to the user, then touch ${latest%.md}.reviewed."
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
When there is a pause, run $(kaizen_skill review)."
        fi
    fi
fi

regression_msg=
regression_marker=
checker=$plugin_root/scripts/usage-db
if [ -f "$checker" ] && command -v python3 >/dev/null 2>&1 &&
    { [ -n "${KAIZEN_USAGE_DB:-}" ] || [ -f "$home/kaizen-usage.db" ]; } &&
    today=$(date -u +%F 2>/dev/null) && [ ! -e "$dir/usage-regression.noticed-$today" ]; then
    # Python provides the deadline on macOS too, without coreutils or a watchdog shell.
    output=$(python3 -c '
import subprocess, sys
result = subprocess.run([sys.executable, "-B", sys.argv[1], "guard"], capture_output=True,
                        text=True, timeout=2, check=True)
print(result.stdout.partition("\n")[0])
' "$checker" 2>/dev/null) || output=
    number='[0-9]+([.][0-9]+)?([eE][+-]?[0-9]+)?'
    finding="^REGRESSION [a-zA-Z][a-zA-Z0-9_.-]{0,80} $number vs $number$"
    if [[ $output =~ $finding ]] && today=$(date -u +%F 2>/dev/null) && mkdir -p "$dir" 2>/dev/null &&
        (set -o noclobber; : > "$dir/usage-regression.noticed-$today") 2>/dev/null; then
        regression_marker="$dir/usage-regression.noticed-$today"
        regression_msg=$output
    fi
fi

actions_msg=
actions_marker=
if [ -n "$root" ] && command -v python3 >/dev/null 2>&1 && [ -f "$plugin_root/scripts/kaizen-scheduled" ]; then
    for setting in friction hostActions; do
        values='(. == "off" or . == "on")'
        [ "$setting" = hostActions ] && values='(. == "off" or . == "suggest" or . == "apply")'
        value=$(jq -r --arg s "$setting" "select(.[\$s] | $values) | .[\$s]" "$root/docs/kaizen/config.json" 2>/dev/null)
        [ -n "$value" ] || value=$(jq -r --arg s "$setting" "select(.[\$s] | $values) | .[\$s]" "$home/agent-kaizen.json" 2>/dev/null)
        [ "$value" = off ] && break
    done
    if [ "$value" != off ]; then
        # The store validates ownership, links, size, records and the canonical project.
        result=$(python3 - "$plugin_root/scripts/kaizen-scheduled" "$dir" "$root" <<'PYCODE' 2>/dev/null
import hashlib, runpy, sys
try:
    runner = runpy.run_path(sys.argv[1])
    host = runpy.run_path(str(runner['HERE'] / 'kaizen_friction_actions.py'))['HostActions']
    rows = host(sys.argv[2], runner['backup_root'](), runner['action_project'], runner['key']).scoped(sys.argv[3])
    opened = [row for row in rows if row['status'] == 'open']
    if opened:
        project = opened[0]['canonical_project']
        print(len(opened), hashlib.sha256(project.encode('utf-8', 'surrogateescape')).hexdigest())
except (OSError, ValueError, RuntimeError, KeyError, UnicodeError):
    pass
PYCODE
        )
        read -r count scope_hash <<< "$result"
        if [[ $count =~ ^[1-9][0-9]*$ && $scope_hash =~ ^[0-9a-f]{64}$ ]] && today=$(date +%F 2>/dev/null); then
            marker="$dir/host-actions-$scope_hash.noticed-$today"
            if (umask 077; set -o noclobber; : > "$marker") 2>/dev/null; then
                actions_marker=$marker
                actions_msg="$count open host action(s): run kaizen-scheduled actions list --for ."
            fi
        fi
    fi
fi

msg=$audit_msg
if [ -n "$experiment_msg" ]; then
    msg="${msg:+$msg

}$experiment_msg"
fi
if [ -n "$regression_msg" ]; then
    msg="${msg:+$msg

}$regression_msg"
fi
if [ -n "$actions_msg" ]; then
    msg="${msg:+$msg

}$actions_msg"
fi
[ -n "$msg" ] || exit 0
if ! out=$(kaizen_context SessionStart "$msg") ||
    [ -z "$out" ]; then
    [ -n "$audit_marker" ] && rm -f "$audit_marker"
    [ -n "$experiment_marker" ] && rm -f "$experiment_marker"
    [ -n "$regression_marker" ] && rm -f "$regression_marker"
    [ -n "$actions_marker" ] && rm -f "$actions_marker"
    exit 0
fi
if printf '%s\n' "$out"; then
    emitted=1
else
    [ -n "$audit_marker" ] && rm -f "$audit_marker"
    [ -n "$experiment_marker" ] && rm -f "$experiment_marker"
    [ -n "$regression_marker" ] && rm -f "$regression_marker"
    [ -n "$actions_marker" ] && rm -f "$actions_marker"
    emitted=1
fi
exit 0
