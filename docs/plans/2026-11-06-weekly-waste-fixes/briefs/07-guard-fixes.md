# 07: fix the review findings in the dispatch guards

Risk: normal. Model: Terra medium. Repo: `~/github/highwayoflife/agent-kaizen`. No commits.

## Goal

Packet 01 (brief `01-dispatch-guards.md`) added guards to `scripts/codex-dispatch`. A batch review found three defects. Fix them and add a regression test for each in `tests/test_dispatch_guards.py`. Use the existing `StubCase` / `FAKE_CODEX` pattern there.

## Findings

1. **Must-fix: a nested repo or untracked directory crashes the snapshot** (`tree_snapshot`, around line 100). `git status --porcelain` lists an untracked nested git repo as `?? sub/`. `path.read_bytes()` then raises `IsADirectoryError`, and the dispatch ends with `STATUS: CODEX FAILED` before Codex runs. The snapshot is taken on every run, so planner, none and `--allow-no-change` runs break too.
   - Fingerprint a directory entry without reading it as a file: use the `lstat` size and mtime_ns, plus `git -C <dir> rev-parse HEAD` and `status --porcelain` if it is a repo. Any other non-regular entry uses lstat as well.
   - Any OSError inside the snapshot must not fail the dispatch. Return `None`, so require-change is skipped, and print one `WARNING: tree snapshot failed: <reason>; require-change skipped` line.
   - Test: put an untracked nested git repo in the work tree. A planner run and an engineer run that changes a file must both complete normally.
2. **Should-fix: the dispatch's own logs count as a change** (around line 235). With `-o <dir inside cwd>` outside `out/`, the dispatch's own logs appear as untracked files, the fingerprint changes, and an empty engineer run passes.
   - Exclude the output directory from the fingerprint whenever it is inside cwd: skip porcelain entries at or under its relative path.
   - Test: `-o <work>/logs/x` with a Codex that changes nothing must give `FAIL: require-change`.
3. **Should-fix: the Sol guard checks the raw `-m` text** (around line 178). It runs `"sol" in (args.m or "").lower()`, so a Sol default (`-m` unset, `CODEX_DISPATCH_MODEL=sol`, line 17) skips it. A substring can also match unrelated names.
   - Check the model that will actually run. Use the resolved slug if the script resolves one; otherwise use `args.m` after the env default.
   - Match the family as a whole token: `re.search(r"(^|[^a-z0-9])sol([^a-z0-9]|$)", model.lower())`. That matches `sol`, `gpt-6.1-sol` and `sol-high`, but not `console` or `solid`.
   - Tests: `CODEX_DISPATCH_MODEL=sol`, no `-m`, and a brief without a reason must be refused. `-m console-model` must not be refused.

Also: in `README.md`, the bash-burst wording "every eight calls", if present, becomes "every eight calls by default". Check with `rg -n "eight" README.md`.

## Scope

- Change only `scripts/codex-dispatch`, `tests/test_dispatch_guards.py`, and `README.md` (that one wording fix).
- Don't touch `scripts/rules-lint.patterns`. It has an unrelated pending edit.
- No version bump: 0.8.0 is not released yet.

## Checks

- `python3 -m unittest tests.test_dispatch_guards tests.test_codex_portability tests.test_scripts`
- `git diff --check`
