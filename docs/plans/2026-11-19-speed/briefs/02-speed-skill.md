# Brief 02: `speed` skill, sidecar, and README entry

## Goal and why

Add the `/agent-kaizen:speed` skill (`skills/speed/SKILL.md`), its Codex visibility sidecar (`skills/speed/agents/openai.yaml`), and its `README.md` entries. The skill guides an agent through profiling a project's tests and checks with `scripts/check-profile`, ranking measured time sinks separately from static hypotheses, proposing or applying verified fixes under `docs/autonomy.md`, writing `docs/kaizen/speed-<date>.md`, and wiring `projectCommands.<project>.speedReport`.

## Context

- Depends on Packet 01 (`scripts/check-profile` must exist on disk because `tests/test_repo.py:110-121` verifies every `${CLAUDE_PLUGIN_ROOT}/<path>` reference in `skills/*/SKILL.md`).
- `tests/test_repo.py:44-52` (`test_skill_preamble`) requires every `skills/*/SKILL.md` to have:
  1. Frontmatter with `name: speed`, double-quoted `description: "..."`, `disable-model-invocation: true`, and `argument-hint: "[propose|safe|auto|yolo]"`.
  2. A top-level `# ...` heading followed by a blank line and the exact two-line `PREAMBLE` (copy verbatim from `skills/test-loop/SKILL.md:10-11` or `skills/friction/SKILL.md:10-11`).
- `tests/test_repo.py:94-100` (`test_skills_have_codex_visibility_sidecar`) and `tools/context_budget.py:80-85` require `skills/speed/agents/openai.yaml` with exact content:
  ```yaml
  policy:
    allow_implicit_invocation: false
  ```
- `tests/test_repo.py:123-127` (`test_readme_lists_every_skill`) requires every skill folder under `skills/` to appear as `` `/agent-kaizen:<name>` `` in `README.md`. Therefore `README.md` must be updated in this same packet.
- `scripts/kaizen-project-report:22` runs each `projectCommands` entry with `shell=False` and a 120-second timeout, and `scripts/kaizen-scheduled:654` runs scheduled jobs with a minimal `PATH`. Because a full profile run can exceed 120 seconds, `speedReport` must only run `check-profile compare --exit-zero` against a `NEW.json` produced by a separate step (CI, cron, or a manual `check-profile unittest|run --out ...`), using absolute paths (no `~` expansion).
- Follow `AGENTS.md` writing rules: plain, short sentences; no marketing language; no unmeasured numbers presented as results; no personal home paths (`/Users/...` or `/home/...`).

## Scope / do not touch

Creates: `skills/speed/SKILL.md`, `skills/speed/agents/openai.yaml`
Modifies: `README.md`

Do not touch `scripts/README.md`, `docs/scheduling.md`, `.claude-plugin/plugin.json`, or `CHANGELOG.md` (Packet 03 owns those in parallel).

## Steps

1. Create `skills/speed/agents/openai.yaml` with the two-line policy matching `skills/test-loop/agents/openai.yaml`.
2. Create `skills/speed/SKILL.md` with frontmatter (`name: speed`, quoted `description`, `disable-model-invocation: true`, `argument-hint: "[propose|safe|auto|yolo]"`), `# Speed: profile and speed up tests and checks`, the exact two-line plugin-root / non-Claude Code preamble, the `**Changes:**` and `**Autonomy:**` lines following `${CLAUDE_PLUGIN_ROOT}/docs/autonomy.md` (same pattern as `skills/test-loop/SKILL.md:15-17`), and a `## Task` procedure covering:
   - Finding the project's test and check commands from `AGENTS.md`, `CLAUDE.md`, `.github/workflows/*.yml`, `package.json`, `Makefile`, or `pyproject.toml`.
   - Running `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check-profile" probe --out out/speed` to time tool startup (`<prog> --version` median and real path) and flag slow shims (> 100 ms, such as the macOS `/usr/bin/git` `xcrun` launcher).
   - Taking a baseline with `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check-profile" run --out out/speed -- <check-cmd>` (adding `--junit <path>` when JUnit XML is available) or `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check-profile" unittest -s tests --out out/speed` for Python `unittest` suites without a durations flag, and saving the baseline JSON (for example `docs/kaizen/speed-baseline.json` or `out/speed/baseline.json`).
   - Running `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check-profile" run --trace <progs> --out out/speed -- <check-cmd>` for programs the suite spawns (`git,python3,node,...`), noting that traced wall time includes wrapper overhead (untraced is the baseline) and calls by absolute path bypass `PATH` wrappers.
   - Running `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check-profile" hints` on the test directory to collect static hypotheses (sleeps, large literal timeouts, non-localhost network calls, subprocess spawns per file).
   - Comparing per-test or job times across platforms when CI logs exist (`gh run view --log` if `gh` is available and authenticated; otherwise skip).
   - Ranking findings by **measured seconds saved** with basis and sample count, kept strictly separate from **hypotheses** (`hints`).
   - Pointing host-level contention (indexers, AV, tool-call stalls) to `/agent-kaizen:friction` and game/engine suite tier restructuring to `/agent-kaizen:test-loop`.
   - Writing the report to `docs/kaizen/speed-<date>.md`.
   - Applying fixes only per `${CLAUDE_PLUGIN_ROOT}/docs/autonomy.md`: backup with `kaizen-backup`, verify immediately, take a before/after `check-profile` measurement for every applied fix, roll back on failure or no improvement, and add a row to `docs/kaizen/LEDGER.md` (with before/after measurement, metric command, and review date).
   - Suggesting setting `projectCommands.<project>.speedReport` in the global `agent-kaizen.json` to an absolute-path argv list such as `["<abs config dir>/bin/check-profile", "compare", "--exit-zero", "<abs base.json>", "<abs new.json>"]`. Explain that `kaizen-project-report` runs `speedReport` with a 120 s timeout (`shell=False`, no `~` expansion, minimal scheduler `PATH`), so the profile run that writes `<abs new.json>` must happen in a separate step (CI, cron, or a manual `check-profile unittest|run --out ...`) and a stale `<abs new.json>` will show a stale result.
3. Update `README.md`:
   - Near `### Friction analysis` (`README.md:170-173`), add a short note that `/agent-kaizen:speed` profiles slow test and check commands with `scripts/check-profile`.
   - In the `## Skills` table (`README.md:247-272`), add a row for `` `/agent-kaizen:speed` `` (what it does and when to run it, near `/agent-kaizen:test-loop` or `/agent-kaizen:friction`).
   - In `## What's in the repo` (`README.md:290-293`), include `check-profile` in the `scripts/` list.

## Acceptance criteria

1. `skills/speed/SKILL.md` has valid frontmatter (`name: speed`, quoted `description`, `disable-model-invocation: true`, `argument-hint`), the exact `PREAMBLE`, the autonomy rules, and the complete `check-profile` workflow (including how `NEW.json` is produced outside `speedReport`, the absolute-path `argv` example without `~`, and the stale-file caveat).
2. `skills/speed/agents/openai.yaml` exists with `allow_implicit_invocation: false`.
3. `README.md` lists `/agent-kaizen:speed` in the skills table, mentions it near the friction text, and lists `check-profile` under `scripts/`.
4. `python3 -m unittest tests.test_repo`, `python3 tools/context_budget.py --root .`, and `claude plugin validate .` all pass.

## Verification

```bash
python3 -m unittest tests.test_repo
python3 tools/context_budget.py --root .
claude plugin validate .
```

## Reporting

Report the files created/modified and the output of the three verification commands. Do not commit or push. Stop and report if an assumption is wrong.

## Suggested agent / model / effort and Risk

- **Agent / model / effort:** `codex-engineer` / `terra` / `medium`
- **Risk:** `low`
