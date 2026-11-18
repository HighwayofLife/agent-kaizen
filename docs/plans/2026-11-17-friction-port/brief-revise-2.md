# Planner revise brief, round 2: the last 3 contract gaps

Revise `docs/plans/2026-11-17-friction-port/plan.md` and the named briefs in place. Fix exactly the three OPEN or BLOCKING items in `review-codex-2.md`. Everything else in that review is RESOLVED: leave it alone.

1. **B3, P24: recovery order.** The brief must follow the plan's recovery order:
   1. record the verified effect as pending bookkeeping;
   2. write and verify the ledger row;
   3. mark the action terminal;
   4. acknowledge.

   Add an acceptance test for a crash after the effect but before the ledger row, and for a crash after the row but before terminal. Make plan.md:~60 and `briefs/24-scheduled-actions.md` say the same.
2. **B8, P20/P20b/P24b: installer inventory.** Each helper module must be registered in the scheduler install inventory (`install-schedule`; see the 0.12.0 version via `git show multi-host:scripts/install-schedule`, around lines 425–429) in the same packet that first exposes a CLI command using it. That packet must test the command through a copied install (`install-schedule --apply` into a temp config home). Update the plan table's owned files and the checks accordingly. Keep file ownership disjoint within each parallel group; if that forces a move, re-sequence.
3. **P16/P24a/P25: ledger attestation proof.** Define the proof's wire shape in plan.md's "Approach and contracts" (field names, types, version, how it is verified). Have P16, P24a and P25 cite that section and use one shared fixture file. Name its path and owner packet.

Also confirm that no file in the plan directory contains an absolute home path. A privacy test bans absolute user home paths on macOS and Linux.

Do not change code and do not commit. Reply in 6 lines or fewer, one line per item plus any re-sequencing.
