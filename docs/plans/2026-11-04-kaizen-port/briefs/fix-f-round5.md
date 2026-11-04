# fix-f round 5, the final round (risk high, Sol high)

Read `fix-f-round4.md` and `../live-probe-result.md` (both probes). Orchestrator decisions:

1. **Remove the exfiltration channel.** Drop `WebFetch` and `WebSearch` from the scheduled tool sets in both modes (`REVIEW_AVAILABLE`, `REVIEW_TOOLS`, `AUTO_AVAILABLE` and the auto allow list). `curl` and `wget` already hard-stop. Scheduled cycles then have no network egress, so a credential a run manages to read cannot leave the machine. Update `skills/cycle/SKILL.md` and `agents/kaizen-auditor.md` so that scheduled runs skip the model and release web checks; interactive runs keep them. Keep the wording short. Pin it in the test.
2. **Backup copies are not readable by the model.** Add `Read` to `backup_deny()` (`<root>/**`, resolved and unresolved). The model only needs `kaizen-backup list`. `kaizen-backup begin` must refuse paths that match the credential deny list (share one constant) and exit non-zero with a clear message. Test both.
3. **Defence in depth.** Add auto and propose hard-stop denies for the built-in read-only commands that take directories or many files: `Bash(grep:*)`, `Bash(egrep:*)`, `Bash(fgrep:*)`, `Bash(rg:*)`, `Bash(find:*)`, `Bash(cat:*)`, `Bash(strings:*)`, `Bash(xxd:*)`, `Bash(od:*)`, `Bash(base64:*)`. The Read, Grep and Glob tools cover legitimate use. Make sure the `notes-ledger add` and `kaizen-backup` allow rules still match. Pin the lists in the test.
4. **Docs (docs/scheduling.md, docs/autonomy.md):**
   - Unattended auto runs cannot edit `.claude` instruction files (CLAUDE.md, `.claude/rules`): Claude Code protects those paths in `-p` mode, as the probe showed. Auto changes are limited to other files, and instruction-file proposals go into the report for the owner.
   - The credential protection rests on having no network egress, with the deny lists as a second layer.
   - `**/.env.*` also hides `.env.example`.
5. **Probe.** Fix `tests/test_schedule_live_probe.py` so it can log in: use the approach in `../live-probe-real-config.py`, with new files under denied paths, a decoy it creates and deletes, and cleanup in `finally`. Keep it opt-in (`KAIZEN_LIVE_PROBE=1`). Expectations:
   - `grep -r` must now be denied;
   - WebFetch must be unavailable;
   - the `.claude/*.md` writes are expected to be denied, and the test documents that.

Do not commit, and do not bump versions. Verify: `python3 -m unittest discover -s tests`, `./scripts/rules-lint --repo .`, `git diff --check`. The orchestrator will run the live probe.
