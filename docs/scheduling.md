# Running the loop on a schedule

The loop has three periodic parts. Only one of them spends model tokens.

| Job | Spends tokens? | How often | Mechanism |
|---|---|---|---|
| Usage audit (`scripts/token-audit`) | No, it's a plain script | Every 3 days | launchd (macOS) or cron (Linux) |
| Unreviewed-audit notice | No | Every session start | The plugin's SessionStart hook (`hooks/audit-notice.sh`) |
| Propose-only review cycle (`/agent-kaizen:cycle propose-only`) | Yes, one headless run | Weekly (optional) | launchd or cron calling `claude -p` with read-only tools |

## Why local and not cloud

Cloud scheduled tasks (`/schedule` routines) run on a fresh clone with no access to your local files. They can't read `~/.claude/projects` transcripts or `~/.codex/sessions`, so they can't audit your usage. `/loop` only lives as long as an open session, and recurring loops expire. Both of the local options below can read your files:
- An OS scheduler (launchd or cron) calling the audit script, and optionally `claude -p`.
- A Claude Desktop scheduled task, which runs on your machine while it is awake.

## Install

```bash
# from your clone of this repo
scripts/install-schedule                # prints the job files it would install
scripts/install-schedule --apply        # installs the 3-day audit
scripts/install-schedule --apply --review --project-dir ~/code/my-project   # also the weekly propose-only review (uses tokens), run in that project
scripts/install-schedule --remove       # uninstalls both
```

The review job runs, from your main project directory:

```bash
python3 ~/.claude/bin/token-audit --out ~/.claude/audits >> ~/.claude/audits/run.log 2>&1
claude -p "/agent-kaizen:cycle propose-only" --model sonnet --max-turns 40 \
  --allowedTools "Read,Grep,Glob,WebFetch,WebSearch" \
  --permission-mode dontAsk > ~/.claude/audits/cycle-$(date +%F).md 2>> ~/.claude/audits/run.log
```

It runs the audit script first, then Claude with no shell, edit or write tools: the proposal is printed and the scheduler saves it as `~/.claude/audits/cycle-<date>.md`. Nothing else changes. The next time you open Claude Code, the notice points you at it. Run `/agent-kaizen:review` to act on it.

`--apply` copies `token-audit` to `~/.claude/bin/` and schedules that copy, so the job survives plugin updates and a moved clone; re-run `--apply` after updating. The weekly run uses `--model sonnet --max-turns 40` (override with `KAIZEN_REVIEW_MODEL` / `KAIZEN_REVIEW_MAX_TURNS`); API-key users can also add `--max-budget-usd`. Check the flags against `claude --help` for your version. The review run uses your normal login. Don't add `--bare`: it skips plugins and needs an API key.
