# Review (sonnet): friction port 0.13.0

Verdict: REVISE. Approach, decomposition, ordering and group file ownership hold up. Seven blocking defects are fixable without changing the approach.

## Blocking findings

1. All packets that add a file under scripts/ (P01, P04, P06, P07, P12, P14, P15, P18, P20, P24): CI breaks until P21.
   - Evidence: tests/test_kaizen_link.py:138-142 `test_all_scripts_are_registered` asserts every file in scripts/ is a value in kaizen-link `SCRIPTS`. `tools/ci-local --python 3.9` (run in every brief) discovers it.
   - P21 only registers the files late and in the same group as P20 (which adds kaizen_friction_prepare.py). P24 adds kaizen_friction_apply.py and says to "register when needed", but scripts/kaizen-link is not in P24's owned files.
   - Fix: make each packet that adds a scripts/ file also own its `SCRIPTS` entry in scripts/kaizen-link, or add a Group A packet that pre-registers all planned names. Also add scripts/kaizen-link to P24's owned list. install-schedule's `aliases` dict (scripts/install-schedule:426) needs `kaizen-*` to file mappings, which P21 covers.
2. P14 (sample-writer): brief is corrupted and its owned files are wrong.
   - Title and Changelog line end in "; tools/host-probe; tests/test_host_probe.py". That text would flow into CHANGELOG via P27.
   - The Owned files list is mangled ("tests/test_housekeep.py test_host_probe.py") and omits tools/host-probe and tests/test_host_probe.py, though step 1 requires edits there.
   - Evidence: the multi-host plan P01 hard-checks exactly 4 Codex registrations (multi-host plan.md:122), and a second PostToolUse command makes 5, so ci-local's `host probe` stage fails.
   - Fix: clean the title and changelog; own `tools/host-probe` and `tests/test_host_probe.py` as separate lines; state that this edit is required for ci-local.
3. P24 (scheduled-actions): same corruption. Title and Changelog carry "; scripts/kaizen-link; tests/test_kaizen_link.py", and the owned list has "tests/test_friction_apply.py test_kaizen_link.py". Fix the text and own scripts/kaizen-link explicitly (finding 1).
4. P06 and P10, plus the plan table's "First narrow check" for both: wrong test file.
   - The briefs own `tests/test_friction_host_probe.py` but verify with `-p 'test_host_probe.py'`, which is the 0.12.0 installer-probe file. On the 0.11.0 base it runs 0 tests ("NO TESTS RAN"); on 0.12.0 it tests something else.
   - Fix: use `-p 'test_friction_host_probe.py'` in the briefs and the table. Keep test_host_probe.py as an extra regression check.
5. Size: P12, P15, P16, P18 (and P14, P01) are far over 400 changed lines if the reference code is reused.
   - Reference sizes (`git diff 599810c wt/<b> --stat`): worktree-prune 373 plus tests 589 (P12 estimate ~390); host-fix 404 plus tests 908 (P15 ~380 and P19 ~310); allow-rule 329 plus tests 692 (P18 ~385); kaizen-backup +291 plus tests 756 (P16 ~390); friction-catalog.json 613 lines plus tests 160 (P01 ~300).
   - Each brief only says "coordinate a split if over 400" and the requirements are stricter than the originals (journals, recovery, CAS).
   - Fix: re-estimate from the reference. Pre-split P12, P15, P16 and P18 into a core packet (happy path plus refusals) and a hardening packet (journal, recovery, injected-failure tests), or state an explicit raised cap. Do not leave it to the engineer.
6. P12 and P16: no explicit security-review step.
   - Both are high risk, but unlike P15, P18, P19, P24 and P25 they lack the "Secure an explicit security review before landing" item (step 3 is the generic diff-confined check). plan.md says only "likewise need review of destructive/ref paths".
   - The requirement names worktree-prune and backup commit as security-sensitive.
   - Fix: add the same security-review step to both briefs and say "security sign-off" for all seven packets in plan.md.
7. P26: the new skills/friction/SKILL.md must carry the exact 0.12.0 preamble, and the sidecar must match the 0.12.0 content.
   - Multi-host P04 and P02 add repo tests that require a preamble in every skill and an agents/openai.yaml with exactly `policy:\n  allow_implicit_invocation: false\n`.
   - P26 only says "preserve 0.12.0 preambles". The new skill fails those tests if it lacks the preamble.
   - Fix: add acceptance criteria for the preamble (exact text from the merged test_repo) and the exact sidecar bytes.

## Advisory

- Shared helper and catalogue resolution: copied installs get prefixed names (`kaizen-friction-catalog.json`, `kaizen_*.py`). P01, P04, P06 and P14 should resolve both names, as pricing does (`sibling(None, "kaizen-pricing.json", "pricing.json")`, scripts/kaizen-scheduled:945).
- P06 output name: main already retains `projects/*/host-probe-*.json` and `projects/*/friction-inputs-*.json` (scripts/kaizen-scheduled:1227, tests/test_housekeep.py:41-50, docs/scheduling.md:171). Pin the filenames to those patterns. Main also already documents `host-actions.json` and `host-fixes/` as untouched by housekeeping.
- P14: it modifies kaizen-scheduled retention (a `samples` kind) but does not run tests/test_runner.py (retentionOverrides cases at 137-151). Add it. Also the sampler is registered on PostToolUse only, so timeouts (which arrive as PostToolUseFailure) get no samples. Say so or register both events.
- P22: budget headroom is about 200 bytes (1024 budget, 823 total per multi-host plan.md:170). State the byte cap on the new notice text.
- context.md cites multi-host `plan.md:149-159,176-179` for "hooks.json unchanged / four Codex registrations". At commit 06564ed those lines are P04 and P07 notes. The right references are plan.md:76, 105, 110, 122, 166 and 170. The multi-host plan exists only on branch `multi-host`, not in this checkout's docs/plans, so say where to read it.
- P27 before P28: if the real-input gate fails a capability, no packet owns the doc/claim downgrade (P28 owns only plan.md and gate-results.md). Add "re-run P27 claims" or put the gate first.
- P28 gate-results.md lives under docs/plans, which tests/test_repo.py scans for home paths. Tell the engineer to replace home paths with `~` before saving.
- Briefs put 10+ requirements into one numbered paragraph. Split into a testable list for the high-risk packets.
- P18 depends on P14 and P09/P13 chains look spurious (allow-rule needs only P05). Harmless but widens the serial tail P23 to P24 to P25 to P26 to P27 to P28.

## Verified OK

- All `wt/*:path` references exist and the named symbols are present in each branch (checked with `git cat-file` and grep for about 60 symbols).
- Main line ranges I sampled match: token-audit def boundaries, kaizen-scheduled (SCHEMA 117, review_command 1187, RETENTION_KINDS 1225, housekeep 1284, rollback 1661, _run_review 1877, main 2172), kaizen-backup parser, hooks.json, context_budget.py:70-111.
- Group ownership is disjoint inside every group; shared files (token-audit, kaizen-scheduled, host-fix, kaizen-backup) are serialized across groups.
- P02 is the only packet that adds config keys, and it runs test_runner.py, test_config_keys.py and the named runner tests. P07, P11, P20, P23 and P24 also run test_runner.py.
- O1 (ls, ls -a, ls -l) and O2 (manual macOS action until same-target proof) match P05, P18, P19, P24 and P27.
- No personal paths, emails or project names in the plan directory (`rg` clean; tests.test_repo passes).
- Sol reason lines are present for every Sol packet; the zero-token rule is kept; a Research needed list (S1-S6) exists; P27 is the only version/CHANGELOG editor; P28 is the real-input gate.

## Coverage

- Every original feature maps to a packet. wt/b (scratch p02/p03) is covered by P01 and P02.
- No unrequested scope found.

## Packets

P01 OK (see 1, 5) | P02 OK | P03 OK | P04 OK (see 1) | P05 OK | P06 fix (4) | P07 OK (see 1) | P08 OK | P09 OK | P10 fix (4) | P11 OK | P12 fix (1, 5, 6) | P13 OK | P14 fix (1, 2, 5) | P15 fix (1, 5) | P16 fix (5, 6) | P17 OK | P18 fix (1, 5) | P19 OK (size 5) | P20 fix (1) | P21 OK | P22 OK | P23 OK | P24 fix (1, 3) | P25 OK | P26 fix (7) | P27 OK | P28 OK

Size check: stated total is about 8,200 changed lines over 28 packets. The reference code suggests P12, P15, P16, P18 and P14 each run 700 to 1,300 lines if ported at full test depth.

Not verified: no tests were run beyond tests.test_repo and a single no-op discover; host clients and S1-S6 research items are untested.
