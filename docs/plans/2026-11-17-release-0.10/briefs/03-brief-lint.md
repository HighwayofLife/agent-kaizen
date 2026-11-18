# 03: Brief preflight (`brief-lint`)

## Goal and why

Briefs that miss a required section (verify commands, acceptance, scope) or name paths and commands that do not exist cost whole dispatch rounds. Add a deterministic preflight, `scripts/brief-lint`, that checks a brief before dispatch. Packet 07 wires it behind an opt-in `codex-dispatch` flag and relies on the exit codes and text lines below.

## Context

- agent-kaizen is a Claude Code plugin; scripts are stdlib-only Python 3.9 in `scripts/`, tests in `tests/`. Read `AGENTS.md` (Rules).
- The shipped brief template is `templates/plan/briefs/01-example.md`: headings `Goal and why`, `Code locations`, `What is known`, `Scope`, `Acceptance criteria`, `Verify`, `Report`; its Scope line reads `Edit only: <files>. Don't touch: <files or areas>. Under ~400 changed lines. ...`. Other users' templates differ (this repo's own plan briefs use `Verification` and `Scope / do not touch`), so section names are configurable.
- Test style: `tests/test_packet_report.py:1-17`. CI runs `--help` on every tracked script (`.github/workflows/ci.yml:46-50`): `#!/usr/bin/env python3`, executable bit.
- Decisions already made (orchestrator):
  - A brief declares the files it creates on a line starting `Creates:` (case-insensitive, optional bold) in its Scope section, listing paths as inline code, or by writing ` (new)` right after an inline-code path. A path that exists only in a user's project or at run time is marked ` (external)` the same way. A path declared anywhere in a brief is not checked for existence anywhere in that brief. This repo's plan briefs follow this convention. Write the convention into `templates/plan/briefs/01-example.md` (add `Creates: <new files, or none>.` to the Scope section, and one sentence about `(external)`).
  - Exit codes: 0 no errors (warnings allowed), 1 at least one error, 2 invalid usage (unreadable brief, bad `--sections` file).
- This packet does not edit CHANGELOG.md. Packet 07 (later) calls `brief-lint --repo <dir> BRIEF` from `codex-dispatch`; packet 11 registers the script for installed copies.

## Scope / do not touch

Creates: `scripts/brief-lint`, `tests/test_brief_lint.py`.
Edit only: `templates/plan/briefs/01-example.md` (the Scope line).
Do not touch `scripts/codex-dispatch`, `scripts/README.md`, `README.md`, `CHANGELOG.md`, `scripts/install-schedule`, `scripts/kaizen-link`.

## Interface (fixed; packet 07 depends on it)

`brief-lint [--repo DIR] [--sections FILE.json] [--json] BRIEF.md...` (one or more briefs; default repo is the current directory).

Text: per brief a first line `<path>: ok` or `<path>: N error(s), M warning(s)`, then one line per finding, `error: <message>` or `warning: <message>`. JSON: one object `{"status": "ok"|"errors", "files": [{"path", "errors": [str], "warnings": [str]}]}`.

Checks:
1. Required sections (error when missing or empty): `goal`, `acceptance`, `verify`, `scope`. Headings (any level `#`) are matched case-insensitively after stripping punctuation; a heading matches when its text starts with an alias. Default aliases: goal = `goal and why`, `goal`, `why`; acceptance = `acceptance criteria`, `acceptance`; verify = `verify`, `verification`, `verify commands`; scope = `scope`, `do not touch`, `don't touch`. `--sections` is a JSON object mapping any of those four keys to a list of alias strings; keys given replace that key's defaults; invalid JSON, a non-object, or an unknown key exits 2. A section is empty when no non-blank line follows its heading before the next heading.
2. Paths (error `path not found: X`): inline-code spans (outside fenced blocks) that contain `/`, have no whitespace and none of `* ? [ ] { } < > $` or `://`, do not start with `-`, `~` or `/`, and look like a repo path: the first segment is an existing directory under `--repo`, or the last segment has a file extension (so `keep/revert`, `n/a` and `out/x` without an extension are not checked). Strip a trailing `:LINE`, `:LINE-LINE` or `:LINE,LINE`. Resolve against `--repo`. Skip paths declared `Creates:`, `(new)` or `(external)` (see Context). State in `--help` and the docstring what is and is not checked; bare file names without `/` and paths in prose are not checked.
3. Verify commands: each non-blank, non-`#` line of fenced blocks inside the verify section, after stripping a leading `$ `. Split with `shlex` (punctuation mode so `&&`, `||`, `;`, `|` separate commands); skip leading `NAME=value` tokens; for each command's first word: shell builtins (`cd`, `export`, `set`, `echo`, `test`, `[`, `source`, `.`, `exit`, `true`, `false`, `unset`, `:`) pass; a word with `/` or starting `./` must exist under `--repo` (error `command not found: X`); otherwise `shutil.which` or an executable under `--repo` (error `command not found: X`). Placeholders (word starting `<`) and dynamic words (`$`, backtick) and unparsable lines give warning `cannot check command: <line>`, never an error. Commands are never executed.
4. Size warning when the brief is over 200 lines or 12288 bytes.

## Steps

1. Core first: sections, size, exit codes, text and JSON output, `--sections`, tests. Then paths and commands, then the template edit.
2. Run the tests; then run `scripts/brief-lint --repo . templates/plan/briefs/01-example.md` (expect exit 0: its placeholders are warnings, not errors).

## Acceptance criteria

1. `scripts/brief-lint --help` exits 0 and documents flags, exit codes, default aliases and what paths and commands are checked.
2. The shipped template lints with exit 0. A brief missing each of the four sections gives an error naming that section; a heading with no body gives an empty-section error. Aliases work case-insensitively (`## VERIFICATION`, `### Goal`).
3. `--sections` replaces only the keys given; bad file, bad JSON and unknown key exit 2; an unreadable brief exits 2.
4. Fixture file `scripts/new-tool` (new), absent from the temp repo: a brief that names it in inline code, with a Scope line `Creates:` followed by that path in inline code, passes against a temp repo where the file does not exist; the same brief without the `Creates:` line, and without ` (new)`, fails with `path not found: scripts/new-tool`; with ` (new)` after the path it passes; ` (external)` works the same, and a declaration at one occurrence waives every occurrence in that brief. A real feature brief modelled on `docs/plans/2026-11-17-release-0.10/briefs/01-flow-event.md` (copied into the test as a fixture string) passes in a temp repo that lacks the files it creates.
5. `:LINE` suffixes, globs, placeholders, URLs, `~/x`, absolute paths, prose paths, `keep/revert` and `n/a` are not reported. A path that exists passes.
6. Commands: `python3 -m unittest ...` and `scripts/x --help` (file exists in temp repo) pass; an unknown first word errors; `cd dir && missing-tool` errors on `missing-tool`; `FOO=1 python3 -c 'x'` resolves `python3`; `<exact commands>`, `$(cmd)` and an unterminated quote warn; a command that would create a marker file is never run.
7. Size warning at 201 lines and at 12289 bytes, none at the limits; warnings alone exit 0.
8. Multiple files in one call: each reported, exit 1 if any has an error. `--json` output parses and matches the interface.

## Verification

```sh
python3 -m unittest discover -s tests -p 'test_brief_lint.py' -v
scripts/brief-lint --help
scripts/brief-lint --repo . templates/plan/briefs/01-example.md; echo "exit $?"
python3 -m unittest discover -s tests -p 'test_repo.py'
```

## Reporting

At most 20 lines: files changed, test results, limitations, one proposed CHANGELOG bullet (do not edit CHANGELOG.md). Do not commit or push. Split trigger: if the packet exceeds about 400 changed lines, finish the core (sections, size, output, exit codes, `--sections`, template edit) with tests, then stop and list the unfinished path and command checks for a follow-up packet.

## Suggested agent / model / effort and risk

`codex-engineer` / Terra medium. Risk: **normal**. Estimated size: 400 lines. Batch reviewer regression modules: `test_repo` (privacy scan), plus a manual look at the template diff.
