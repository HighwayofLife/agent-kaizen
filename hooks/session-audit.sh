#!/usr/bin/env bash
# Claude runs this hook asynchronously. The scheduler owns the deadline and lock.
exec </dev/null >/dev/null 2>&1
[ -n "${CLAUDE_PLUGIN_ROOT:-}" ] || exit 0
python3 "$CLAUDE_PLUGIN_ROOT/scripts/kaizen-scheduled" auto-audit
exit 0
