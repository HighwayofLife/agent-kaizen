# fix-d: ledger guard hardening (risk high, Sol medium)

Repo: agent-kaizen, `scripts/kaizen-scheduled`. Packet 09 added a post-run ledger integrity guard; see briefs 09-fix2.md and docs/scheduling.md. Its final review approved it with notes. The owner keeps New World in `auto` mode, so close these gaps. Each fix needs a test that fails without it. Keep the code generic and do not bump versions. Do not commit.

1. **About l.693-697:** keep the old ledger bytes in memory, in the guard's entry, and restore from memory. Do not re-read the snapshot file, because the run can overwrite it. The snapshot file may stay as a debugging aid. Test: the run truncates both the ledger and the snapshot, and the ledger is still restored.
2. **About l.721:** reject a symlinked ledger path at snapshot time, failing closed with a clear message. Do not restore over the symlink. Docs: ledger paths must be regular files.
3. **About l.649 and `load_config` l.138-150:** when the global config file exists but is unreadable or malformed, a scheduled review or cycle must not launch. Exit non-zero with a clear status. A missing file keeps today's behaviour.
4. **About l.953:** set the violation flag before writing the violation report or state. If those writes raise, housekeeping and the remaining projects are still skipped.
5. **About l.706:** compare timeline lines with trailing `\r\n` stripped, so a last line without a newline does not cause a false positive.
6. **docs/scheduling.md, wording only:**
   - The CSV is checked by prefix hash, so it is append-only.
   - The timeline check ensures old rows are kept in order. It does not prevent extra text being inserted between them.
   - The guard protects the ledger files only. Other edits made by the cycle remain, and background processes started by the run are not stopped.

Verify: `python3 -m unittest discover -s tests`, `./scripts/rules-lint --repo .`, `git diff --check`.
