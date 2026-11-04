# fix-f round 6, a final small delta (Terra medium)

Context: `fix-f-round5.md`. The Sol review of 9ae6155 found three issues; fix exactly these:

1. **Drop the explicit read-only Bash grants** (`scripts/kaizen-scheduled` around l.117 and l.702). `head` and `tail` can read backup copies and credential files, and the Read tool covers legitimate reading. Set `READ_ONLY_BASH` to empty in both modes, so the only Bash allow rules left are the exact `notes-ledger add` and `kaizen-backup begin|finish|list` helper rules (auto only). Update the pinned-list test and docs/scheduling.md. Check that skills/cycle/SKILL.md and agents/kaizen-auditor.md do not tell scheduled runs to use `ls`/`head`/`tail`/`shasum`.
2. **Installer prefix** (`scripts/install-schedule` around l.50). `kaizen_credentials.py` is not covered by the `kaizen-` replacement prefix, so a differing installed copy stays stale and fails the final check. Make the replace logic include it (e.g. also accept the `kaizen_` prefix, or list the module explicitly), and test it.
3. **Docs only** (docs/scheduling.md, where credential protection is described). `kaizen-backup begin` checks credential patterns on the given path and its resolved target. A credential reached only through a symlink with an ordinary-looking name can still be copied, but the copy lands in the backup root, which the model cannot read, and scheduled runs have no network egress. Say this in one or two sentences.

Do not commit, and do not bump versions. Verify: `python3 -m unittest discover -s tests`, `./scripts/rules-lint --repo .`, `git diff --check`.
