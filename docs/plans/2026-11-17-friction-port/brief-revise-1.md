# Planner revise brief, round 1: friction port plan (0.13.0)

Sol reason: the open findings are trust and recovery contracts for scheduled mutations (commit baseline handoff, action import/journal/ack ordering, the mutation budget, undo ledger rows, and evidence for persistent permission grants). These are security- and concurrency-sensitive design decisions.

Revise `docs/plans/2026-11-17-friction-port/plan.md`, `context.md` and `briefs/*.md` in place so that every BLOCKING and MUST-FIX finding in both reviews is resolved:
- `review-codex.md`: Sol, 12 BLOCKING and 3 ADVISORY.
- `review-sonnet.md`: Sonnet, 7 MUST-FIX plus advisories.

Do ALL items, not a subset. The original planner brief is `brief-planner.md`, and its constraints still apply.

Notes:
- **0.12.0 contracts.** The multi-host 0.12.0 work is on local branch `multi-host` (not merged to main yet). Read its plan and files with `git show multi-host:<path>` / `git diff main multi-host --stat`, and cite that branch for 0.12.0 contracts: the skill preamble, the openai.yaml sidecar, the hook-manifest checks, and `tools/host-probe`. Do not check out branches.
- **kaizen-link registration.** `tests/test_kaizen_link.py` requires every `scripts/` file to be registered in kaizen-link `SCRIPTS`. Pick one approach and apply it everywhere: either each packet registers its own new script, or Group A pre-registers all of them. Make sure ci-local stays green after every packet.
- **Oversized packets.** Split each into core plus hardening packets so each one stays near 400 changed lines including tests. Use the measured reference sizes in review-sonnet.md. Renumber or suffix (12a/12b) as you like, but keep the packet table, dependencies, groups and traceability consistent.
- **Security sign-off.** Every high-risk mutation packet states "security review before landing" in its brief and in plan.md.
- **Corruption.** Clean the corrupted title, Changelog and owned-file lines in P14 and P24, and check every other brief for the same corruption.
- **Design contracts.** When a finding needs one (payload schema, stable action-ID derivation, ordering of import → journal → execute → acknowledge, quota resolution, the ledger row with undo lookup by action ID, accepted-prompt evidence per literal and scope, fingerprint binding to window/threshold/basis), write it once in plan.md's "Approach and contracts" section. Then make the owning packet's acceptance criteria test it, including the interruption cases the review asks for.
- **Decisions.** Keep O1/O2 as settled. Raise a new owner decision only if a finding cannot be settled from code and docs, and give your recommendation.

Do not change code and do not commit. Reply in 12 lines or fewer, covering:
- each finding id/packet and how it was resolved, in one phrase each;
- the new packet count by model;
- any new decision.
