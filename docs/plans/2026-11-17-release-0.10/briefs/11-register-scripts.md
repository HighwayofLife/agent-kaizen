# 11: Register the new scripts for installed copies and document them

## Goal and why

Installed copies only get the scripts named in two lists, so a scheduled runner installed from the plugin cache would silently skip a sibling `experiment-check` it never received, and `codex-dispatch --brief-lint` would find no `brief-lint` beside it. This packet is the only one that edits those lists, after every new script exists. It also documents the new scripts in `scripts/README.md`.

## Context

- agent-kaizen is a Claude Code plugin; scripts are stdlib-only Python 3.9, tests in `tests/`. Read `AGENTS.md` (Rules).
- New scripts to register (all already merged): `packet-event` (packet 01), `experiment-check` (02), `brief-lint` (03), `flow-report` (05).
- Lists: `scripts/install-schedule:50-56` `MANAGED_NAMES` (a tuple; the filter that keeps only existing files is at :425, `names = [name for name in MANAGED_NAMES if (HERE / aliases.get(name, name)).exists()]`); `scripts/kaizen-link:28-39` `SCRIPTS` (dict, target name to source name; both scripts end with an `if __name__ == "__main__"` guard, so `runpy.run_path` can load them). Today `set(SCRIPTS.values())` equals every entry of `scripts/` except `README.md`.
- `scripts/kaizen-scheduled:901-908` `sibling()` finds helper scripts next to itself (`HERE`), and `scripts/codex-dispatch` finds `brief-lint` next to itself the same way, so a copy-mode install needs the files in the same bin folder.
- Existing tests to extend: `tests/test_kaizen_link.py:120-135` (`test_copy_auto_dependencies_and_directories`: copies `scripts/` into a fake plugin cache, `run_link("--apply", root=fake)`, runs installed scripts with `run_script`); `tests/test_schedule.py:127-130` (after `install-schedule --apply --review`, a tuple of `(source, target)` names is compared byte for byte with the installed files in `~/.claude/bin`); `tests/test_install_schedule.py`.
- `scripts/README.md` layout: one `## <script>` section per script with a `usage:` block and a short description (see `## packet-report` at :535-547, `## kaizen-link` at :517); `## codex-dispatch` at :25, `## kaizen-scheduled` at :238.
- Decisions already made (orchestrator): this packet is the sole owner of the registration lists and of `scripts/README.md` for new scripts. No scheduled step needed registration earlier because the scheduler tests run from the repo `scripts/` folder. This packet does not edit CHANGELOG.md or the top-level README.md (packet 12 does).

## Scope / do not touch

Creates: nothing.
Edit only: `scripts/install-schedule` (`MANAGED_NAMES`), `scripts/kaizen-link` (`SCRIPTS`), `scripts/README.md`, `tests/test_kaizen_link.py`, `tests/test_schedule.py` (the name tuple at :127-130), `tests/test_install_schedule.py` (only if needed).
Do not touch the new scripts themselves, `scripts/kaizen-scheduled`, `scripts/codex-dispatch`, `README.md`, `CHANGELOG.md`.

## Steps

1. Add `packet-event`, `flow-report`, `experiment-check` and `brief-lint` to `MANAGED_NAMES` and to `SCRIPTS` (identity mapping, same style as the neighbours).
2. Add a `## <name>` section to `scripts/README.md` for each of the four (usage block copied from `<script> --help`, then two or three plain sentences and one example, exit codes included). Also add: under `## codex-dispatch` the `--brief-lint` flag (opt-in, runs `brief-lint --repo <-C dir>` before Codex, errors stop the dispatch, warnings are reported, skipped on `--resume`); under `## kaizen-scheduled` the `checks path|record` commands, the `pendingDays` key and the `## Experiments` section of the checks report.
3. Tests, then run the checks.

## Acceptance criteria

1. `python3 -c` style check or test shows all four names in `MANAGED_NAMES` and in `SCRIPTS`.
2. Guard test in `tests/test_kaizen_link.py`: load `SCRIPTS` with `runpy.run_path`; every entry of `scripts/` (ignoring `README.md`, `__pycache__` and dotfiles) appears among `set(SCRIPTS.values())`; a new unregistered script makes it fail.
3. Copy-mode test in `tests/test_kaizen_link.py`: copy `scripts/` to a fake plugin cache, `--apply`, and in the bin folder: each of the four is a real file (not a symlink) and executable, answers `--help` with exit 0 and `packet-event` appends a valid line to a temp file; loading the installed `kaizen-scheduled` with `runpy.run_path` gives a `sibling(None, "experiment-check")` that resolves inside the bin folder; the installed `codex-dispatch --brief-lint -C <temp dir> <invalid brief>` exits 2 with `Reason: brief-lint:` (not `not found`).
4. `tests/test_schedule.py` byte-for-byte tuple includes the four scripts, and the `install-schedule --apply --review` flow installs them.
5. `kaizen-link --check` after `--apply` still reports `0 drift, 0 broken` (the existing assertion in `tests/test_schedule.py:134-137`).
6. `scripts/README.md` has the four sections, the `--brief-lint` flag and the `checks` commands; the usage blocks equal the scripts' current `--help` output (compare by eye or with `diff <(scripts/<name> --help) ...`; report any mismatch).

## Verification

```sh
python3 -m unittest discover -s tests -p 'test_kaizen_link.py' -v
python3 -m unittest discover -s tests -p 'test_schedule.py' -v
python3 -m unittest discover -s tests -p 'test_install_schedule.py' -v
python3 -m unittest discover -s tests -p 'test_repo.py'
for s in packet-event flow-report experiment-check brief-lint; do scripts/$s --help > /dev/null && echo "$s ok"; done
```

## Reporting

At most 20 lines: files changed, test results, limitations, one proposed CHANGELOG bullet (do not edit CHANGELOG.md; mention that `kaizen-link --check` will report the new scripts as drift on machines that have an older linked bin until the user re-runs `kaizen-link --apply`). Do not commit or push. Stop and report if a new script is missing or a list has a different shape from the lines above.

## Suggested agent / model / effort and risk

`codex-engineer` / Terra medium. Risk: **normal** (installer lists affect every user's linked bin). Estimated size: 250 lines. Batch reviewer regression modules: `test_kaizen_link`, `test_schedule`, `test_install_schedule`, `test_repo`.
