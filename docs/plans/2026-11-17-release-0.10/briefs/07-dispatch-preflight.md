# 07: Opt-in `--brief-lint` preflight in `codex-dispatch`

## Goal and why

A brief that misses a section or names paths and commands that do not exist wastes a whole dispatch. Packet 03 adds `scripts/brief-lint`; this packet lets `codex-dispatch` run it first, behind a flag that is off by default so no existing user is affected.

## Context

- agent-kaizen is a Claude Code plugin; scripts are stdlib-only Python 3.9, tests in `tests/`. Read `AGENTS.md` (Rules).
- `scripts/brief-lint` (packet 03, already merged) interface: `brief-lint [--repo DIR] [--sections FILE.json] [--json] BRIEF.md...`; text lines `<path>: ok` or `<path>: N error(s), M warning(s)` then `error: <message>` / `warning: <message>` lines; exit 0 no errors (warnings allowed), 1 errors, 2 invalid usage or unreadable brief.
- `scripts/codex-dispatch`: `EPILOG` :14-21; `arguments()` :36-64 (flags at :39-57; add the new flag there with help text); `reason_guard` :245-263; `main()` :266 onward: cwd check :268-271; brief read and reason guard inside `if not args.resume:` :272-282 (early failure prints `Reason: ...` and `STATUS: CODEX FAILED`, returns 2); `warnings = []` is defined later at :293 and each warning is printed in the report as one line (`report()` :298-306). `here = Path(__file__).resolve().parent` is how the script finds sibling files (:353).
- Tests: `tests/test_dispatch_guards.py` (class `DispatchGuardTests(StubCase)`; `self.brief` is `Fix the example.\n`, which is not a valid brief); helpers in `tests/test_scripts.py:16-100` (`self.dispatch(*args, code=...)`, `self.calls()` reads what the stub Codex received, `self.report(result)`); resume example at :171. Run the real `brief-lint` from the repo `scripts/` directory.
- Decisions already made (orchestrator): off by default; lint runs only when `--brief-lint` is given and the dispatch is not a `--resume`; warnings never stop dispatch; errors stop it before any Codex process with `STATUS: CODEX FAILED` and exit 2 (same as the reason guard). This packet does not edit CHANGELOG.md.

## Scope / do not touch

Creates: nothing.
Edit only: `scripts/codex-dispatch`, `tests/test_dispatch_guards.py`.
Do not touch `scripts/brief-lint`, `skills/codex-dispatch/SKILL.md`, `README.md`, `scripts/README.md`, `CHANGELOG.md`.

## Steps

1. Add `--brief-lint` (store_true) with help text and an `EPILOG` line. In `main()`, inside the `if not args.resume:` block, after the reason guard and only when `text is not None`: run `[sys.executable, <here>/brief-lint, "--repo", str(cwd), str(brief path)]` with a 60 second timeout. Exit 0: collect its `warning: ...` lines. Exit 1: print `Reason: brief-lint: N error(s): <first up to 5 error messages joined with "; ">` and `STATUS: CODEX FAILED`, return 2. Anything else (script missing, OSError, timeout, exit 2): same output with `Reason: brief-lint failed: <detail>`, return 2.
2. Surface collected warnings in the report as `WARNING: brief-lint: <message>` lines, through the existing `warnings` list (define the lint list before the resume block and extend `warnings` when it is created at :293).
3. Tests.

## Acceptance criteria

1. `scripts/codex-dispatch --help` documents `--brief-lint` and says it is off by default.
2. Without the flag, a brief that fails lint dispatches exactly as before (stub Codex called, same output).
3. With the flag and a brief that has all four sections and existing paths and commands, dispatch proceeds and the stub Codex is called.
4. With the flag and a brief missing a section or naming a nonexistent path: exit 2, stdout contains `STATUS: CODEX FAILED` and `Reason: brief-lint`, the stub Codex is never called, and the `out/dispatch` (external) run directory is not created.
5. Warnings only (a brief over 200 lines): dispatch proceeds and the report contains `WARNING: brief-lint:`; the 25-line report limit still holds (`self.report`).
6. Path checks are relative to `-C`: a brief naming `sub/inside` passes when `-C` is the repo root containing it and fails when `-C` points elsewhere.
7. `--resume` with an invalid brief and `--brief-lint`: lint is skipped and behaviour is unchanged.
8. Missing tool when opted in: run a copy of the `scripts/` directory (`shutil.copytree`) with `brief-lint` removed; exit 2 with `Reason: brief-lint failed`. Without the flag the same copy dispatches normally.

## Verification

```sh
python3 -m unittest discover -s tests -p 'test_dispatch_guards.py' -v
scripts/codex-dispatch --help
python3 -m unittest discover -s tests -p 'test_scripts.py'
```

## Reporting

At most 20 lines: files changed, test results, limitations, one proposed CHANGELOG bullet (do not edit CHANGELOG.md). Do not commit or push. Stop and report if `scripts/brief-lint` is missing or its interface differs from the one above.

## Suggested agent / model / effort and risk

`codex-engineer` / Terra medium. Risk: **normal**. Estimated size: 150 lines. Batch reviewer regression modules: `test_dispatch_guards`, `test_scripts`, `test_brief_lint`.
