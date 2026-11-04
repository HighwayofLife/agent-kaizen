# 05b: `codex-review diff --paths` and `dispatch-status` dirty worktrees

## Goal and why
Two small improvements exist only in the owner's `~/.claude/bin`: (a) `codex-review diff --paths PATH...` limits a review to given paths; (b) `dispatch-status` lists worktrees with uncommitted work. Port both generically.

## Context
- Repo: ~/github/highwayoflife/agent-kaizen. Python 3.9+ stdlib; read `AGENTS.md`. No personal paths or project names in tracked files. Tests run offline with stub executables (see `tests/test_scripts.py` for the stub-`codex` pattern).
- (a) `scripts/codex-review`: arguments at lines ~17-40 (`diff` mode takes `--base`, `--commit`, `--uncommitted`); the diff prompt is built around lines ~74-100. Reference (read-only): `~/.claude/bin/codex-review` line 27 `p.add_argument("--paths", nargs="+", default=[])` (diff mode) and lines 90-95: when set the prompt gets `Paths: review only \`<git command> -- <shell-quoted paths>\`; ignore changes outside these paths.` followed by `Paths:` and a bullet per path. `<git command>` is `git diff BASE...HEAD`, `git show COMMIT`, or `git diff HEAD`.
- (b) `scripts/dispatch-status` is a 34-line Python script: RUNNING codex-dispatch processes and the latest `out/dispatch/*/report.md` STATUS per directory argument. Reference (read-only, owner-specific zsh): `~/.claude/bin/dispatch-status`. Port only the generic part: a final section headed exactly `DIRTY WORKTREES (uncommitted paths outside out/, newest change age)` listing, for the given directories (default: the current directory plus every `git worktree list --porcelain` entry of it), each worktree with uncommitted paths (`git status --porcelain --untracked-files=all -- . ':!out'`): path count, age of the newest changed file (m/h/d; for deleted files use the nearest existing parent's mtime) and the last commit subject (70 chars). Skip clean worktrees. No Unity or project-name logic. Keep all existing output unchanged above it. Session-start hooks parse the headings `RUNNING` and `DIRTY WORKTREES`; keep those words.

## Scope / do not touch
Edit `scripts/codex-review` (args and prompt only) and `scripts/dispatch-status`. Create `tests/test_review_paths.py` and `tests/test_dispatch_status.py`. Do not touch token-audit (packet 05a), `~/.claude`, version or CHANGELOG.

## Acceptance criteria
1. `codex-review diff --paths a "b c"` (stub codex) puts the `Paths:` line and bullets in the prompt, quoting the path with a space; without `--paths` the prompt is byte-identical to the current output (test against a recorded prompt).
2. `dispatch-status` in a temp git repo with one dirty worktree prints the heading and one row (count, age, subject); a clean tree prints no row; the old sections are unchanged.
3. Full suite passes.

## Verification
```
cd ~/github/highwayoflife/agent-kaizen   # your worktree
python3 -m unittest tests.test_review_paths tests.test_dispatch_status -v
python3 -m unittest discover -s tests
python3 scripts/codex-review diff --help && python3 scripts/dispatch-status --help
```

## Working tree
Codex packets run in their own git worktree (`git worktree add ~/github/highwayoflife/agent-kaizen-wt-05b -b kz-05b`, created by the orchestrator). Work only there.

## Reporting
Files changed, test counts. Do not commit or push.

## Suggested agent / model / effort
codex-engineer, Terra, medium. Risk: normal.
