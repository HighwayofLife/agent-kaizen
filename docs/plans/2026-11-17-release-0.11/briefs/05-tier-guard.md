# 05: Opt-in Agent tier guard

## Goal and why

Prevent unexplained expensive agent spawns while keeping the guard escapable and fail-open.

## Context

`skills/guardrails/SKILL.md:12,44-50` installs opt-in hooks; `hooks/limit-big-read.sh:27` returns JSON denial with exit 0. Read synthetic `tests/fixtures/hooks/pretooluse_agent.json`; PreToolUse input includes `subagent_type` and optional `model`. The event is an allowed spawn request, not proof of a completed spawn.

## Constraints
Read `AGENTS.md`. Python 3.9 stdlib only; scripts under `scripts/` are executable and answer `--help`. Hooks use macOS bash 3.2, shellcheck, bounded work and exit 0 even on errors; an intentional denial is JSON with exit 0. Do not edit `.github/workflows/ci.yml`. Use `rg -n` and narrow `sed` ranges (no `tools/codemap` exists). Propose a changelog bullet; on each packet landing the integrator bumps the manifest and adds a dated changelog entry before checks, as required by AGENTS.md. Do not edit these shared files in parallel worktrees. Skills require quoted description, matching name, `disable-model-invocation: true`, and README table row. Never commit or push. Stop and report wrong assumptions or if the packet exceeds ~400 changed lines; do not drop criteria.

## Scope / do not touch

Create `hooks/tier-guard.sh`, `tests/test_tier_guard.py`; edit `skills/guardrails/SKILL.md`, `templates/settings.example.json`. Do not register guard globally or edit `hooks/hooks.json`.

## Steps

Read the existing fixture; do not create it. Define a `guardrails` section in the existing global configuration `<Claude config dir>/agent-kaizen.json` (the current repository has no guardrails configuration section): `pattern | free spawns per session | reason regex`. Glob matches `tool_input.subagent_type`; first matching row wins. Missing `model` does not bypass a matched rule. Validate and fail open on malformed rows/regex. Count per session and matched rule atomically with a private, owned directory and a bounded `mkdir` lock with a fixed retry count and short sleep, including stale lock handling; no `flock`, `wait -n`, or `timeout(1)`; no session ID means allow. First N eligible spawns silent; thereafter deny with `Tier reason: <why>` instruction unless prompt matches configured regex and has non-empty reason. Allow matching retry, log only timestamp, rule and supplied reason in private state (no prompt); denied retries do not consume allowances. Explain install, disable, overrides, storage and privacy in guardrails skill and template. Deny with exit 0 JSON `hookSpecificOutput.permissionDecision: "deny"` and `permissionDecisionReason`; never use `onFailure: block`. Never emit a denial after a state/log/parse/lock error; bounded retries limit foreground delay. Document that the counter counts allowed PreToolUse spawn requests, not completed spawns.

## Acceptance criteria

1. Fixture confirms event extraction; free allowance, above-limit denial, compliant retry and reason logging work.
2. Invalid config, missing fields/jq, unreadable/private-state errors and lock timeout exit 0 and allow, without leaking prompt.
3. Concurrent calls preserve allowance; non-Agent tools and unmatched rules are silent. Shell passes bash 3.2 and shellcheck.
4. Guard exists only in opt-in configuration.

## Verification

```sh
python3 -m unittest discover -s tests -p 'test_tier_guard.py' -v
python3 -m unittest discover -s tests -p 'test_hooks.py' -v
shellcheck -S warning hooks/tier-guard.sh
python3 -m unittest discover -s tests -p 'test_repo.py' -v
```

## Reporting

Report files, results, limitations and baseline/after measurements where applicable. Do not commit or push.

Changelog: Add an opt-in agent tier guard.

## Suggested agent / model / effort and risk

`codex-engineer` / Sol high (concurrent allowance state). Risk: **high**.
