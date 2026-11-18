# BF17c Batch-9 review fixes: friction skill and docs text

Fix-Origin: batch-review (batch 9). Fixes: P26. Risk: normal. Model: terra / high.

## Goal
Batch review 9 found that P26's instructions do not match the real CLI. A model following them fails. Check every command against `--help` and the code of `scripts/kaizen-scheduled`, `scripts/token-audit`, `scripts/kaizen-backup` and `scripts/kaizen_friction_prepare.py`:

1. `skills/friction/SKILL.md:17`: interactive preparation runs without refreshing the required host probe. With default settings, all friction analysis is skipped on fresh installs and whenever the probe is over an hour old. Add the refresh step (the real command and its freshness rule) before `friction prepare`.
2. `skills/cycle/SKILL.md:25`: the refresh uses a single `--cwd .`, but preparation requires the full canonical project path set. Projects with linked worktrees reject the freshly refreshed report. Use the real way to pass every path (find how the scheduled runner builds it) or the CLI's helper for it.
3. `skills/friction/SKILL.md:24`: the skill allows any ID in the view and gives the model no way to check `apply` eligibility. A flag ID, or an `apply` request under `hostActions=suggest`, rejects the entire batch. Say which IDs are actionable and how to read eligibility and the hostActions setting before building a request.
4. `docs/autonomy.md:75`: the backup recipe for the new local-commit exception omits `kaizen-backup begin --repo DIR`. Without it there is no clean-start baseline and `kaizen-backup commit` refuses. Fix the recipe order.
5. `skills/review/SKILL.md:24`: review picks the newest audit on its own, ignoring the runner-supplied report. A scheduled cycle can then rank ledger findings against a different scope or window than its prepared friction evidence. When a report is supplied, use it.

Keep skill text short (context budget). Add or extend `tests/test_friction_skill.py` assertions that pin the corrected commands.

## Rules
- First confirm or refute each finding against the code (and a failing test where practical). Fix the confirmed ones at their cause, test first. List refuted ones in the report with evidence.
- Never weaken, skip or delete an existing test. Do ALL items.
- Do not touch `.claude-plugin/plugin.json`, `CHANGELOG.md` or the version. Write a player-facing-style changelog fragment to `docs/plans/2026-11-17-friction-port/changelog/BF17c.md` only if a user would notice the fix; otherwise none.
- Gated items G1–G10 in plan.md stay out of scope. Do not commit or push.
- Report: per item CONFIRMED+fixed / REFUTED (evidence), files changed, checks run.

## Verify
- `python3 -m unittest discover -s tests -p 'test_friction_skill.py'`
- `python3 -m unittest discover -s tests -p 'test_repo.py'`
- `python3 -m unittest discover -s tests -p 'test_rules_lint.py'`
- `python3 -m unittest discover -s tests -p 'test_context_budget.py'`
- `python3 tools/context_budget.py`
