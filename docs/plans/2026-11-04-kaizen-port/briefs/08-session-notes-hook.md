# 08: `session-notes.sh` hook (SessionStart notices)

## Goal and why
The owner's `~/.claude/hooks/session-notes.sh` prints short SessionStart notices (unreviewed audit, in-flight dispatches, ledger rows pending after two audits, stale-rule hits). It is the only hook of the three listed that the plugin lacks (`after-compact.sh` and `limit-big-read.sh` already exist in `hooks/` as generic supersets). Port it generically and offer it as an opt-in hook.

## Context
- Repo: ~/github/highwayoflife/agent-kaizen. Read `AGENTS.md`. Hook rules: `shellcheck -S warning hooks/*.sh` must be clean; hooks never fail the session (always `exit 0`); `jq` missing degrades with a stderr notice. Existing hooks to copy style from: `hooks/audit-notice.sh` (reads the config dir and per-project reports; already registered in `hooks/hooks.json`) and `hooks/after-compact.sh`. Tests for hooks: see `tests/test_hooks.py` (`run()` helper pipes JSON to `bash hooks/X.sh`).
- Reference (read-only): `~/.claude/hooks/session-notes.sh` (the file is ~60 lines). Generic version differences: (a) the unreviewed-audit notice is already done by `audit-notice.sh`, so omit it; (b) in-flight section: run `dispatch-status` if it is on PATH or at `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/bin/dispatch-status`, keep only the `RUNNING` and `DIRTY WORKTREES` sections that have rows, under a 20-second timeout (use `timeout` if present); drop the `tools/land_packet.sh` condition and all project names; (c) pending ledger: project `docs/kaizen/LEDGER.md` rows whose `measured effect` is `pending` and older than 6 days (the embedded python snippet in the reference; keep it but find the columns by name); (d) stale rules: if `rules-lint` is on PATH or in the bin dir above, run it with `--repo "$PWD"` and add a notice unless its last line starts with `rules-lint: 0 ` or is empty or says `no patterns configured`; (e) output via `jq -n` `hookSpecificOutput` with `hookEventName: SessionStart` exactly like the reference; nothing printed when there is nothing to say.
- `templates/settings.example.json` already shows opt-in hook entries (after-compact, subagent-context, block-image-read, limit-big-read); add a `SessionStart` entry for `session-notes.sh` with matcher `startup|resume` next to them, using the same `bash ~/.claude/hooks/...` command style as its neighbours.

## Scope / do not touch
Create `hooks/session-notes.sh` (executable, same mode as its siblings) and `tests/test_session_notes.py`. Edit `templates/settings.example.json` (one entry). Do not touch `hooks/hooks.json` (the plugin registers only audit-notice), other hooks, or `~/.claude`. No version/CHANGELOG edits. No personal paths or project names.

## Acceptance criteria
1. In a temp project with a `docs/kaizen/LEDGER.md` containing a row pending for >6 days, the hook prints valid JSON with an `additionalContext` mentioning N pending rows; with none pending and no tools, it prints nothing and exits 0.
2. With a stub `dispatch-status` on PATH that prints a RUNNING row, the notice includes it; a stub that hangs is cut off by the timeout without failing the hook (use a short override env var `SESSION_NOTES_TIMEOUT`, default 20).
3. With a stub `rules-lint` printing `rules-lint: 3 stale-rule hit(s)` the notice mentions it; `rules-lint: 0 stale-rule hit(s)` and `rules-lint: no patterns configured` add nothing.
4. `jq` missing: exits 0 with a stderr notice.
5. `templates/settings.example.json` still parses (`jq empty`) and `tests/test_repo.py` passes.
6. `shellcheck -S warning hooks/*.sh` is clean; full suite passes.

## Verification
```
cd ~/github/highwayoflife/agent-kaizen
python3 -m unittest tests.test_session_notes tests.test_hooks tests.test_repo -v
python3 -m unittest discover -s tests
shellcheck -S warning hooks/*.sh
jq empty templates/settings.example.json
```

## Working tree
Codex packets run in their own git worktree (`git worktree add ~/github/highwayoflife/agent-kaizen-wt-08 -b kz-08`, created by the orchestrator). Work only there and run the commands from that directory.

## Reporting
Files changed, test counts. Do not commit or push.

## Suggested agent / model / effort
codex-engineer, Terra, medium. Risk: normal.
