# fix-f round 3 (risk high, Sol high)

Read `fix-f-final-audit-scheduler.md` and `fix-f-round2.md` first; this file is their delta. The re-review of e17280c returned a narrow REVISE: the round-1 exploit is closed by the backup deny rules and the runner-held ownership, and the allow list shrank. Remaining issues:

1. **Arbitrary execution through allowed Bash tools (P1; this hole is also on main).** `Bash(rg:*)` is allowed in both auto and propose modes (`scripts/kaizen-scheduled` around l.115 and l.758). `rg --pre python3 x payload.py` runs a program the model wrote, and that bypasses every deny rule. Fix it at the root:
   - Shrink REVIEW_TOOLS and the auto Bash grants to a minimal vetted set. The Read, Grep and Glob tools cover searching and reading, so drop `rg` and any other tool that can execute programs or write files through flags. Audit every remaining Bash rule for exec/write escapes: `rg --pre`/`--hostname-bin`, `find -exec/-execdir/-ok/-delete/-fprint*`, `awk` `system()` and redirection, `sed` `e`/`w` commands and `-i`, `sort -o`, `git` options that run pagers or hooks or write files (`-c`, `--output`, `difftool`), `xargs`, `env`, `tee`, `less`, `man`, and redirection. Keep a tool only if no flag lets it execute or write. If unsure, drop it.
   - Add a test that pins the exact allowed-Bash list for each mode against a constant, with a comment beside each entry saying why it is safe. Any future addition then needs a deliberate test change.
   - Check that `skills/cycle/SKILL.md` and `agents/kaizen-auditor.md` do not tell scheduled runs to use a dropped tool. Interactive use may keep it.
2. **Symlink regression (round 2).** `scripts/kaizen-backup` around l.70-84 and l.112-114: `refuse_symlinks` runs on the raw user path and on CHANGE_DIR, so `begin <symlinked dir>/CLAUDE.md`, macOS `/tmp` or `/var/folders`, and `undo last` with a symlinked ROOT are all refused. Instead:
   - At `begin`, resolve user input first.
   - Resolve ROOT before the containment test.
   - At undo and finish, only require `path.resolve() == path` for stored entries, plus a final component that is not a symlink.
   - Test it with a symlinked HOME-style dir and with a ROOT behind a symlink.
3. **Partial rollback on directory targets.** `validate_entry` (around l.102-115) accepts a directory target, then `unlink()` fails mid-restore. In the preflight, require that every target is a non-directory, or absent for `created` entries, before restoring anything. Test it.
4. **Docs.** docs/scheduling.md around l.141 still lists `mkdir`, `token-audit` and others. Update it to the exact new allow lists for both modes, and explain why searching uses the Grep tool rather than Bash.

Do not commit, and do not bump versions. Verify: `python3 -m unittest discover -s tests`, `./scripts/rules-lint --repo .`, `git diff --check`.

**Orchestrator addendum: known vectors in today's READ_ONLY_BASH** (`ls, wc, head, tail, rg, git status, shasum, sha256sum, jq`):
- `rg --pre` is described in item 1.
- `git status` runs `core.fsmonitor`, hooks and the `diff.external`/textconv config from `.git/config` or `-c`. In auto mode the model can Write inside the project, so it can plant `.git/config`, and `git status` then executes it. Drop `git status`; the runner already reports git state. Alternatively, add Edit/Write deny rules for `**/.git/**` and keep it only as `git -c core.fsmonitor= status` with the config hardened, but dropping it is preferred.
- Also deny Edit/Write to `**/.git/**` in auto mode regardless, so hooks cannot be planted for the owner's next interactive git command.
- `jq`, `head`, `tail`, `wc`, `ls` and the sha tools have no known exec or write flag. Confirm this for the installed versions, e.g. jq has no `system`.
