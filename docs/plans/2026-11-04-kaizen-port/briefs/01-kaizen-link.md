# 01: `kaizen-link` (link or copy plugin scripts into the Claude config dir, plus drift check)

## Goal and why
Make the plugin's `scripts/` and `hooks/` the single source of truth. A new script `scripts/kaizen-link` puts each plugin script into `<claude home>/bin` (and each hook into `<claude home>/hooks`) as a symlink, or as a copy when the plugin lives under a plugin cache directory whose path changes per version. `kaizen-link --check` reports any installed file that differs from its plugin source (drift). Today `~/.claude/bin` copies were made by hand or by `install-schedule --apply` (copy) and have drifted from the plugin.

## Context
- Repo: ~/github/highwayoflife/agent-kaizen (Claude Code plugin; Python 3.9+, stdlib only; no tools/codemap here, use `rg -n` and `sed -n`). Read `AGENTS.md` first.
- Claude config dir = `$CLAUDE_CONFIG_DIR` or `~/.claude`. Copy the "paths helper" block (`claude_home()`, lines 17-29 of `scripts/token-audit`, bracketed by `# --- paths helper ---` / `# --- end paths helper ---`) rather than importing.
- Decisions already made: symlink by default when the plugin's real path does not contain `/plugins/cache/`; copy otherwise; no wrapper scripts. Names that intentionally differ from the plugin are listed in the global setting `localScripts` (a JSON list of bin/hook file names in `<claude home>/agent-kaizen.json`) and are reported as LOCAL, never as drift. Read that JSON file directly (do not import `kaizen-scheduled`).
- Managed names (bin name -> plugin file under `scripts/`): `token-audit`, `kaizen-token-audit` (alias of token-audit), `kaizen-scheduled`, `kaizen-backup`, `pricing.json` and `kaizen-pricing.json` (both -> pricing.json), `rules-lint.patterns`, `install-schedule`, `usage-series`, `usage-compare`, `rules-lint`, `packet-report`, `kaizen-project-report`, `notes-ledger`, `kaizen-link`, `codex-review`, `codex-dispatch`, `codex-run`, `codex_common.py`, `dispatch-status`; directories `prompts` and `preambles`. Runtime dependencies matter in copy mode: `usage-series` and `usage-compare` load `token-audit` and `pricing.json` by those exact names from their own folder, and `rules-lint` reads `rules-lint.patterns` next to itself, so these three are managed under their canonical names too.
- Directory semantics: in link mode a directory (`prompts`, `preambles`) is one symlink to the plugin directory. In copy mode every file of the plugin directory is copied into a real directory of the same name (extra files already there, such as an owner's `3d.md`, are left alone). Compare = every plugin file exists in the target directory and is byte-identical; extras are ignored. `--replace` on a differing directory renames the whole directory to `NAME.replaced-<yyyymmdd>`.
- Mutation safety (review finding): every mutating action (`--apply`, `--replace`, `--unlink`) must skip a name listed in `localScripts` and say `skip LOCAL NAME`. A LOCAL directory (for example `preambles`) must stay byte-identical, including after `--apply --replace`. Files not yet present in `scripts/` (later packets add rules-lint, packet-report, kaizen-project-report, notes-ledger) are skipped silently. Hooks (`hooks/NAME.sh` -> `<claude home>/hooks/NAME.sh`): after-compact, block-image-read, limit-big-read, subagent-context, session-notes (skip if absent). `audit-notice.sh` is registered by the plugin itself; do not manage it.
- Live state for reference: `~/.claude/bin/kaizen-backup` is identical to the plugin's; most others differ (see `diff -q scripts/X ~/.claude/bin/X`). Do not touch `~/.claude` in this packet; tests use a temporary config dir via `CLAUDE_CONFIG_DIR`.

## Scope / do not touch
Create only `scripts/kaizen-link` (executable, `#!/usr/bin/env python3`) and `tests/test_kaizen_link.py`. Do not edit `install-schedule` or `kaizen-scheduled` (packet 09 wires them). No version or CHANGELOG edits. No personal paths in code, docs or fixtures (tests/test_repo.py enforces this).

## CLI
```
kaizen-link [--bin DIR] [--hooks-dir DIR] [--mode auto|link|copy] [--only NAME,...]
            [--apply | --check | --unlink] [--replace | --replace-prefixed] [--restore-replaced] [--json]
```
- No action flag: print the plan (one line per name: `would link|copy|skip NAME ...`), change nothing.
- `--apply`: create missing links/copies; fix a symlink that points elsewhere; leave an existing correct link/identical copy alone. A differing regular file is NOT overwritten unless `--replace`, which renames it to `NAME.replaced-<yyyymmdd>` first. Never deletes user files.
- `--check`: for each managed name present in the target dir print one status: `OK` (correct symlink or byte-identical copy), `DRIFT` (regular file differing from source, or symlink to a different target), `BROKEN` (dangling symlink), `LOCAL` (name in `localScripts`), `ABSENT` (not installed; informational). Final line `kaizen-link: N drift, M broken, K local`. Exit 0 when drift+broken == 0, else 1. A copy that differs is DRIFT with the hint `re-run kaizen-link --apply --replace`.
- `--replace-prefixed`: like `--replace` but only for names starting `kaizen-` (the plugin's own namespace); other differing files are left alone and reported DRIFT. `install-schedule` uses this so it never renames another tool's generically named file.
- `--unlink`: remove only symlinks that point into this plugin (never follow them; never touch the plugin files). With `--restore-replaced`, afterwards rename the newest `NAME.replaced-<date>` back to `NAME` when `NAME` is absent. Rollback order for callers: `--unlink` FIRST, then `kaizen-backup undo`, because `kaizen-backup undo` copies with `shutil.copy2`, which writes through a symlink into the plugin source.
- `--json`: machine-readable `{"entries":[{"name","kind","status","detail"}],"drift":N,"broken":N,"local":N}`.
- `--help` must work (CI runs it).

## Acceptance criteria
1. `python3 scripts/kaizen-link --help` exits 0; with `CLAUDE_CONFIG_DIR` pointing at an empty temp dir, `--check` prints ABSENT rows and exits 0.
2. `--apply` in a temp dir creates symlinks whose targets are the plugin files; a second `--apply` changes nothing; `--check` then exits 0.
3. A differing regular file is reported DRIFT (exit 1), is not overwritten by `--apply`, and is renamed to `.replaced-<date>` and linked by `--apply --replace`.
4. A dangling symlink is BROKEN (exit 1). A name listed in `localScripts` with a differing file is LOCAL and does not affect the exit code.
5. `--mode auto` chooses copy when the plugin path contains `/plugins/cache/` (tested by passing a fake plugin root through a hidden `--plugin-root DIR` option used by tests) and link otherwise. In copy mode, `--check` flags a stale copy as DRIFT.
6. Scripts linked into the temp bin still run: `bin/token-audit --help` and `bin/kaizen-scheduled --help` exit 0 (their sibling lookups use `Path(__file__).resolve()`, which follows the link). If this fails for any script, stop and report; do not patch other scripts.
7. `--unlink` removes only plugin-pointing symlinks and leaves others.
8. LOCAL safety: with `localScripts` naming `codex-review` and `preambles` and differing live copies in the temp bin, `--apply --replace` and `--unlink` leave those byte-identical (compare sha256 before/after) and print `skip LOCAL`.
9. Rollback rehearsal in temp dirs (`KAIZEN_BACKUP_DIR` temp): `kaizen-backup begin` a regular file, `--apply --replace` links over it, then `kaizen-backup undo` WITHOUT `--unlink` would write through the link (assert this is why the order matters by checking the plugin source is changed in a scratch COPY of the plugin dir, never the real one); with `--unlink` first, undo restores the original and the plugin source sha256 is unchanged.
10. Copy mode installs the dependencies: after `--apply --mode copy` into a temp bin, `bin/usage-series --help`, `bin/usage-compare --help` and `bin/rules-lint --repo <fixture>` all work (they find `token-audit`, `pricing.json`, `rules-lint.patterns` beside them).
11. Directory semantics above are tested for link, copy, compare and `--replace`.
12. Full suite passes: `python3 -m unittest discover -s tests`.

## Verification
```
cd ~/github/highwayoflife/agent-kaizen
python3 -m unittest tests.test_kaizen_link -v
python3 -m unittest discover -s tests
python3 scripts/kaizen-link --help
CLAUDE_CONFIG_DIR=$(mktemp -d) python3 scripts/kaizen-link --check
```

## Working tree
Codex packets run in their own git worktree (`git worktree add ~/github/highwayoflife/agent-kaizen-wt-01 -b kz-01` created by the orchestrator). Work only there; run the commands below from that directory instead of the main clone.

## Reporting
Report files changed, test counts, and anything surprising (especially acceptance 6). Do not commit or push. Stop and report if an assumption above is wrong.

## Suggested agent / model / effort
codex-engineer, Terra, medium. Risk: normal (it writes into the user's config dir when `--apply` is used, but only through the guarded paths above).
