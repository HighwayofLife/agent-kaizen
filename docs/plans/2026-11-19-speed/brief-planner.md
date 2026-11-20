# Planner brief: a `speed` skill and a `check-profile` script

## Goal

Write `plan.md` and one brief per packet in this directory (`docs/plans/2026-11-19-speed/`; repo root = this agent-kaizen checkout). Do not change code and do not commit. Target: 3–4 packets.

The plugin should find what makes a project's tests and checks slow, measure it, and propose fixes ranked by measured seconds saved. Today nothing does this:
- `skills/friction` covers agent tool-call time and host contention (Spotlight, Defender…), not time lost inside a test process.
- `skills/test-loop` restructures game/engine suites into tiers; it is game-specific and about structure, not root causes.
- `projectCommands.<project>.slowTests` and `.speedReport` (see `scripts/kaizen-scheduled` `valid_project_commands` and `scripts/kaizen-project-report` around line 124) already run a user-supplied command into the project report, but the plugin ships no command to put there.

Motivating case (CHANGELOG 0.13.3): on macOS every `git` call went through the `/usr/bin/git` xcrun launcher and cost 170–390 ms; one backup step took over 10 s and macOS CI runs timed out. Nothing in the plugin would have flagged it. This repo's own `python3 -m unittest discover -s tests` takes over two minutes, so it is the first dogfood target.

## Settled design (owner approved; do not re-litigate)

1. **`scripts/check-profile`**, Python 3.9+, stdlib only, executable, answers `--help`, follows the style of the other scripts (argparse subcommands, JSON + short Markdown output, no network). Subcommands:
   - `probe [--programs git,python3,node,...]`: time the startup of common programs on this host (`<prog> --version`, median of N runs, resolved real path via `shutil.which` + `os.path.realpath`). Flags programs whose median startup is above a threshold (default 100 ms). This alone catches the xcrun Git launcher.
   - `run [--trace PROGS] [--junit PATH] [--out DIR] -- CMD...`: run a check command once untraced (wall time, user+sys CPU of children via `resource.getrusage(RUSAGE_CHILDREN)` where available, exit code), then, if `--trace` is given, once more with a temp directory of timing wrappers placed first on PATH for each named program. Each wrapper execs the real binary (resolved before PATH is changed, so no recursion) and appends one line (program, argv[1] truncated, elapsed ms) to a log. Report per program: calls, total ms, median ms, top argv[1] values. State that the traced run's wall time includes wrapper overhead and the untraced run is the baseline. Calls by absolute path bypass the wrappers; say so in the report. On Windows, skip tracing with a clear note (degrade, don't fail). If `--junit` names a JUnit XML file the command writes, parse per-test times and list the slowest.
   - `unittest [-s DIR] [-p PATTERN] [--top N]`: run stdlib unittest discovery with a timing result class and print the slowest tests and per-module totals (pass/fail preserved in the exit code). Covers projects (like this one) whose runner has no durations option.
   - `hints [PATHS...]`: regex scan of test files for likely time sinks: sleeps (`time.sleep`, `sleep `, `setTimeout`), large literal timeouts, real network calls (`urlopen`, `requests.`, `http://`/`https://` hosts other than localhost), subprocess spawns per file. Output is labeled **hypotheses**, never measured results.
   - `compare BASE.json NEW.json [--threshold PCT]`: diff two `run`/`unittest` JSON results; exit non-zero and print the regressed items when total or a per-test/per-program figure got slower by more than the threshold (default 20%). This is the command a user puts in `projectCommands.<project>.speedReport`, so the existing scheduled project report shows regressions with no scheduler change.
   - Write outputs only under the `--out` directory (default `out/speed/` in the cwd).
   - Tests in `tests/test_check_profile.py` using tiny fixture commands and a fake slow program (a script that sleeps) so `probe` and `--trace` flag it deterministically and quickly. Keep the new tests fast (whole file well under 10 s).

2. **`skills/speed/SKILL.md`**: frontmatter `name: speed`, quoted `description`, `disable-model-invocation: true`, `argument-hint` like the other skills; same Plugin root / Not in Claude Code / autonomy header lines as `skills/friction/SKILL.md` and `skills/test-loop/SKILL.md`. Procedure: find the project's check commands (AGENTS.md/CLAUDE.md, CI workflow, package.json, Makefile); `probe`; baseline with `run` (or `unittest`); `run --trace` with programs the suite spawns; `hints`; compare per-test times across platforms when CI logs exist (`gh run view --log` if `gh` is available, otherwise skip); rank findings by measured seconds with basis and sample count, separate from hypotheses; propose fixes; host-level causes (indexers, AV) point to `/agent-kaizen:friction`, suite restructuring points to `/agent-kaizen:test-loop`; apply only per `docs/autonomy.md`; every applied fix gets a before/after measurement and a ledger row as the autonomy doc describes; write `docs/kaizen/speed-<date>.md`; suggest setting `projectCommands.<project>.speedReport` to a `check-profile compare` command against the saved baseline.

3. **Docs and release**: README skills table row (tests check every skill is listed) and a short mention near the friction text; `scripts/README.md` section for `check-profile`; `docs/scheduling.md` note on using `speedReport` with `check-profile compare`; bump `version` in `.claude-plugin/plugin.json` (current 0.13.4 → 0.14.0) and add a `## 0.14.0 (2026-11-19)` CHANGELOG entry. Writing rules in AGENTS.md apply: plain, short sentences, no marketing, no numbers that are not measured.

4. **Dogfood measurement** (last packet, orchestrator may run it): run `check-profile unittest -s tests` and `check-profile probe` on this repo; record results in `plan.md`. If a pre-0.13.3 checkout is practical (`git worktree add out/wt-0132 42efb34`), run `check-profile run --trace git -- python3 -m unittest tests.test_backup_commit` there and record whether the git wrapper shows the slow calls on macOS. Remove the worktree afterwards.

## Constraints

- AGENTS.md rules: stdlib only, Python 3.9+, `python3` not `python`, no home paths or personal data in tracked files, scratch output in `out/`, `token-audit` untouched.
- Must work for any user/project on macOS, Linux and Windows (Windows may skip tracing); no assumptions about the owner's machine.
- Check commands for briefs: `python3 -m unittest tests.test_check_profile`, `python3 -m unittest tests.test_repo` (repo consistency, skills table, privacy), `shellcheck -S warning hooks/*.sh` only if a hook changes (none should), `claude plugin validate .`. Do not run the full suite per packet (it takes minutes); the full suite runs once at the end.
- Risk tags: script packet `normal`, skill and docs packets `low`.
- Do not touch `token-audit`, `kaizen-scheduled` or `kaizen-project-report` unless a packet proves a change is needed; the existing `speedReport` key should be enough.
