# 01: codex-dispatch guards

Repo: agent-kaizen (cwd). Do not commit. Do not edit `.claude-plugin/plugin.json`, `CHANGELOG.md`, or any file outside the list below.

## Why
A weekly review found two problems:
1. Orchestrators add `-k 'test -n "$(git status --porcelain)"'` to prove Codex changed something. On a checkout that was already dirty this always passes, so an empty run looks like success.
2. Sol is used far more than the rule "Sol only with a named reason" intends (219 Sol sessions vs 149 Terra in a week).

## Change `scripts/codex-dispatch` (and `scripts/codex_common.py` only if a helper belongs there)
1. **Tree snapshot.** Before the first Codex run, if `-C` is inside a git work tree, record a fingerprint: the output of `git status --porcelain=v1 -uall` plus a sha256 of `git diff HEAD --binary` plus sha256 of the contents of each untracked file listed (keep it simple and fast; skip untracked files over 5 MB by size+mtime). If the tree is not a git work tree, skip all of this silently.
2. **Dirty-tree warning.** If the snapshot shows changes before Codex runs, add one report line `WARNING: tree was dirty before dispatch (N paths)`.
3. **Require change (default on for `-p engineer`, off for `-p planner` and `-p none`).** After each Codex run and before the checks, compare the fingerprint. If unchanged, treat it like a failed check named `require-change` (so it gets the normal resume rounds, with a resume prompt saying no files changed). Add `--allow-no-change` to turn it off. When the dispatch ends with no change, STATUS must not be a success status; use the existing failed-checks status.
4. **Sol reason.** If the resolved model is in the Sol family (alias `sol`, or a slug whose family resolves to sol via the existing model helper; look at how `-m` is resolved), the brief file must contain a line matching `^\s*Sol reason:\s*\S` (case-insensitive). If missing, exit non-zero before running Codex, with a one-line error. `--resume` runs are exempt. Record the reason text in the report as `Sol reason: ...`.
5. Keep the report at its current line limit.

## Tests
Add tests in a new `tests/test_dispatch_guards.py`, following the fake-codex pattern in `tests/test_codex_portability.py`: no change -> require-change fails; change -> passes; dirty-before + no new change -> fails and warning line present; `--allow-no-change` passes; `-p planner` not enforced; Sol without reason exits before Codex runs; Sol with reason runs and reports it; non-git `-C` unaffected.

## Docs
Update the codex-dispatch section of `README.md` (or the doc under `docs/` that documents codex-dispatch flags; find it with `rg -n "codex-dispatch" README.md docs`) with the three behaviours, in short plain sentences.

## Verify
`python3 -m unittest tests.test_dispatch_guards tests.test_codex_portability tests.test_scripts`
