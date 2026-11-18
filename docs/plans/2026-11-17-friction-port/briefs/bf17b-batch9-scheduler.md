# BF17b Batch-9 review fixes: scheduler and preparation

Fix-Origin: batch-review (batch 9). Fixes: BF15b, BF16. Risk: normal. Model: terra / high.

## Goal
Batch review 9 (Sol, range bb32242..3f91471) reported these against `scripts/kaizen-scheduled` and `scripts/kaizen_friction_prepare.py`:

1. `scripts/kaizen-scheduled:2475` (BF15b): when publication recovery refuses a marker, the entire project is skipped. A user editing a published report before recovery can block later scheduled reviews until the marker or report is removed by hand. Recovery must resolve that case (e.g. treat the edited report as published or abandon the marker with a logged reason) instead of blocking the project indefinitely, without overwriting the user's edit.
2. `scripts/kaizen_friction_prepare.py:416` (BF15b): suggestions imported before a failed publish are suppressed on retry. The new audit or probe changes the generation, so unchanged suggestions that were never published disappear from the next proposal. Only suggestions that were actually published (or acknowledged) may be suppressed.
3. `scripts/kaizen_friction_prepare.py:429` (BF15b): `schedule` is missing from the frozen policy. Switching a project to `schedule=off` before reconciliation still lets the in-flight review import suggestions. Freeze it with the other policy fields and honour it at import.
4. `scripts/kaizen-scheduled:3020` (BF16): during degraded recovery (an unrelated interrupted-run recovery error), acknowledgement is skipped even for successfully published suggestion-only reviews, so each due review proposes the same evidence again while the error persists. Acknowledge successfully published suggestion-only reviews, but keep BF16's invariant: never advance acknowledged_generation while recovery failed for that project's actions or actions are pending (see tests/test_friction_apply.py around line 634).

## Rules
- First confirm or refute each finding against the code (and a failing test where practical). Fix the confirmed ones at their cause, test first. List refuted ones in the report with evidence.
- Never weaken, skip or delete an existing test. Do ALL items.
- Do not touch `.claude-plugin/plugin.json`, `CHANGELOG.md` or the version. Write a player-facing-style changelog fragment to `docs/plans/2026-11-17-friction-port/changelog/BF17b.md` only if a user would notice the fix; otherwise none.
- Gated items G1–G10 in plan.md stay out of scope. Do not commit or push.
- Report: per item CONFIRMED+fixed / REFUTED (evidence), files changed, checks run.

## Verify
- `python3 -m unittest discover -s tests -p 'test_friction_review.py'`
- `python3 -m unittest discover -s tests -p 'test_friction_prepare.py'`
- `python3 -m unittest discover -s tests -p 'test_friction_apply.py'`
- `python3 -m unittest discover -s tests -p 'test_schedule_robustness.py'`
