#!/usr/bin/env bash
# Optional SessionStart notices. Never fail the session.
if ! command -v jq >/dev/null 2>&1; then
  echo 'session-notes: jq is not installed; skipping notices' >&2
  exit 0
fi

msg=
add() { msg="${msg:+$msg
}$1"; }
find_tool() {
  if command -v "$1" >/dev/null 2>&1; then
    command -v "$1"
  elif [ -x "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/bin/$1" ]; then
    printf '%s\n' "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/bin/$1"
  fi
}

dispatch=$(find_tool dispatch-status)
if [ -n "$dispatch" ]; then
  if command -v timeout >/dev/null 2>&1; then
    ds=$(timeout "${SESSION_NOTES_TIMEOUT:-20}" "$dispatch" 2>/dev/null)
  elif command -v gtimeout >/dev/null 2>&1; then
    ds=$(gtimeout "${SESSION_NOTES_TIMEOUT:-20}" "$dispatch" 2>/dev/null)
  else
    ds=$(
      tmp=$(mktemp) || exit 0
      "$dispatch" >"$tmp" 2>/dev/null &
      pid=$!
      (sleep "${SESSION_NOTES_TIMEOUT:-20}"; kill "$pid" 2>/dev/null) >/dev/null 2>&1 &
      watchdog=$!
      wait "$pid" 2>/dev/null
      kill "$watchdog" 2>/dev/null
      wait "$watchdog" 2>/dev/null
      cat "$tmp"
      rm -f "$tmp"
    )
  fi
  ds=$(printf '%s\n' "$ds" | awk '
    /^RUNNING/ {s="r"; next} /^DIRTY WORKTREES/ {s="d"; next} /^[A-Z]/ {s=""; next}
    s=="r" && NF {r=r "\n" $0} s=="d" && NF {d=d "\n" $0}
    END {if (r) printf "Running dispatches:%s\n", r; if (d) printf "Dirty worktrees:%s\n", d}')
  [ -n "$ds" ] && add "In-flight work (dispatch-status):
$ds"
fi

if [ -f docs/kaizen/LEDGER.md ]; then
  n=$(python3 - docs/kaizen/LEDGER.md 2>/dev/null <<'PY'
import datetime
import sys

columns = None
count = 0
today = datetime.date.today()
with open(sys.argv[1], encoding="utf-8", errors="replace") as ledger:
    for line in ledger:
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if columns is None:
            names = [cell.lower() for cell in cells]
            if "date" in names and "measured effect" in names:
                columns = (names.index("date"), names.index("measured effect"))
            continue
        date_col, effect_col = columns
        if len(cells) <= max(columns):
            continue
        try:
            date = datetime.date.fromisoformat(cells[date_col])
        except ValueError:
            continue
        if cells[effect_col].lower() == "pending" and (today - date).days > 6:
            count += 1
print(count)
PY
)
  [ "${n:-0}" -gt 0 ] 2>/dev/null && add "$n ledger rows still pending after two audits: see docs/kaizen/LEDGER.md"
fi

lint=$(find_tool rules-lint)
if [ -n "$lint" ]; then
  rl=$("$lint" --repo "$PWD" 2>/dev/null | tail -1)
  case "$rl" in
    ""|"rules-lint: 0 "*|*"no patterns configured"*) ;;
    *) add "$rl (run rules-lint --repo . for details)" ;;
  esac
fi

[ -n "$msg" ] && jq -n --arg c "$msg" '{hookSpecificOutput:{hookEventName:"SessionStart",additionalContext:$c}}' 2>/dev/null
exit 0
