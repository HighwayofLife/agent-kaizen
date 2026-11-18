# Brief P04: plugin-root preamble in every skill, `codex-dispatch` note, repo tests

Suggested agent: Terra, low effort. Risk: normal. Size: M. Group B. Runs AFTER P02 and P03 have landed on your base: `skills/*/agents/openai.yaml` (22 files) and `docs/hosts.md` already exist. P08 runs in parallel but touches other files. If `docs/hosts.md` or the sidecars are missing, stop and report.

## Goal and why

Agent Kaizen skills refer to scripts as `${CLAUDE_PLUGIN_ROOT}/scripts/...`. Claude Code substitutes that placeholder in skill text. Codex and Copilot do not: the model gets the raw `SKILL.md` and its file path. A fixed two-line preamble under each skill's title tells a non-Claude model where the plugin root is, to substitute the resolved path wherever the skill uses `CLAUDE_PLUGIN_ROOT`, where to read the host map, to skip steps that only work in Claude Code, and to follow the propose-only rule for host configuration before acting. Claude Code behaviour must not change (the first line then reads as a plain path).

## Context and facts you can rely on

- 22 skills at `skills/*/SKILL.md`; each has frontmatter (`---` ... `---`), a blank line, then `# Title` at line 8 (verified by `awk`), then a blank line and body text.
- `agents/kaizen-auditor.md` has frontmatter and NO `# ` heading: the body starts after the closing `---` and a blank line with "You run the agent-kaizen cycle ...". Insert the agent's preamble right after that blank line (before "You run ...").
- `tests/test_repo.py:60-71` checks `\$\{CLAUDE_PLUGIN_ROOT\}/<path>` references exist; the preamble writes `${CLAUDE_PLUGIN_ROOT}` followed by a backtick, not a slash, so it is not matched. Frontmatter test at `:44-50`; README table test at `:73-77`.
- Other tests read skill text: `tests/test_flow_skill.py:11,18`, `tests/test_process_rules.py:11,19`, `tests/test_schedule_steps.py:784`, `tests/test_scan.py:66`. They must still pass.
- `tools/context_budget.py` counts only frontmatter descriptions, so the budget is unchanged.
- The Codex model sees the skill file path in its skill list (probed), so the plugin root must be resolvable from it: this file is `skills/<name>/SKILL.md`, and the plugin root is the folder that contains `skills/` (note: two levels up from the file is `skills/`, so the wording names the folder instead of counting levels). On Copilot whether the model is told the skill path is unverified (owner check O1), so the preamble also says what to do with the resolved path. The shell commands in skills use the form `${CLAUDE_PLUGIN_ROOT}/scripts/...`; a non-Claude host will not set that variable, hence the substitution instruction. Keep the wording below exactly (tests pin it).
- `docs/hosts.md` (P03) has the Plugin root paragraph and the `Safety rule` section that the second preamble line points to (covered files, Claude-only steps to skip).

## The exact preamble (skills)

Insert, after the first body line that starts with `# ` (outside frontmatter) and its following blank line, these two lines followed by one blank line:

```
**Plugin root:** `${CLAUDE_PLUGIN_ROOT}`. If that is still a `${...}` placeholder, use the folder that contains `skills/` (this file is `skills/<name>/SKILL.md`), and substitute that path, in quotes, wherever this skill uses `CLAUDE_PLUGIN_ROOT`.
**Not in Claude Code?** Read `docs/hosts.md` in the plugin root first. Skip steps that only work in Claude Code, and follow its propose-only rule before changing any host configuration.
```

Result: `# Title`, blank, the 2 lines, blank, original body. That is 3 added lines per skill and 0 deleted. (The text writes `CLAUDE_PLUGIN_ROOT` without `${` in the second use on purpose: Claude Code substitutes only the `${...}` form, and the line must still read sensibly there.)

## The agent preamble (`agents/kaizen-auditor.md`)

The same two lines with "the folder that contains `skills/` (this file is `skills/<name>/SKILL.md`)" replaced by "the folder that contains `agents/` (this file is `agents/kaizen-auditor.md`)", inserted after the frontmatter's closing `---` and its blank line, followed by one blank line.

## `codex-dispatch`

In `skills/codex-dispatch/SKILL.md` add one more line directly after the preamble, as its own line before the blank line:
`Inside Codex, this skill does not apply: do the work in the current session.`
(so that skill gains 4 lines, all others 3).

## Scope

Edit: `skills/*/SKILL.md` (22 files), `agents/kaizen-auditor.md`, `tests/test_repo.py`.
Create: `docs/plans/2026-11-17-multi-host/changelog/P04.md` (`mkdir -p`) containing exactly:
`- Every skill starts with a two-line plugin-root note and a pointer to docs/hosts.md, so Codex and Copilot find the bundled scripts; Claude Code reads the same text as a plain path.`

Do NOT touch: `.claude-plugin/plugin.json` (version), `CHANGELOG.md` (only P09 edits them), skill frontmatter or descriptions, any other skill text, `docs/hosts.md`, `docs/autonomy.md`, the sidecars, README, hooks, scripts, `tools/`.

## Steps

1. Do NOT edit by hand. Write a short throwaway Python script (put it in `out/`, which is git-ignored, not in the repo tree) that, for each `skills/*/SKILL.md` and the agent file, inserts the preamble idempotently: skip a file that already contains the line starting `**Plugin root:**`; find the first line starting with `# ` after the closing frontmatter `---` (skills) or the first line after the frontmatter plus blank (agent). Preserve every other byte (read and write with `newline=''` or binary; keep the trailing newline).
2. Run it. Run it a second time and confirm `git diff --numstat` does not change (idempotent).
3. Add `codex-dispatch`'s extra line.
4. Add tests to `tests/test_repo.py` (inside `RepoTests`): (a) `test_skill_preamble`: for each skill, the exact two-line preamble text above (pinned as a constant `PREAMBLE`) occurs exactly once (`text.count(PREAMBLE) == 1`), and it appears directly after the first `# ` heading and its blank line; (b) the agent file contains its own exact variant once (constant `AGENT_PREAMBLE`, with the `agents/` wording); (c) `docs/hosts.md` exists and contains the headings `Claude Code`, `Codex CLI` and `Copilot`; (d) `skills/codex-dispatch/SKILL.md` contains the Inside-Codex line.

## Acceptance criteria

1. `git diff --numstat -- skills/*/SKILL.md` shows 0 deleted lines for every file and 3 added lines for 21 skills and 4 for `codex-dispatch`; `git diff --numstat -- agents/kaizen-auditor.md` shows 3 added, 0 deleted.
2. `git diff -- skills agents` outside the inserted lines is empty (no other text changed; check with `git diff --stat` and `git diff -U0 | rg '^[-+]' | rg -v '^(\+\+\+|---)'` shows only the preamble lines).
3. New tests pass; the script is idempotent. No skill or agent text says "two levels above".
4. `python3 tools/context_budget.py --root .` total unchanged (823 bytes).
5. No file under `skills/` or `agents/` other than those listed is modified; the sidecars are untouched.
6. Owner checks O1 and O2 (see `probe-results.md`, created by P01) invoke a skill from an unrelated project after this packet lands; nothing to do here beyond keeping the wording exact.

## Sandbox and environment (read before running any command)

- Writable temp dir: `mkdir -p out/tmp && export TMPDIR="$PWD/out/tmp"` (`out/` is git-ignored; keep the path short). If `out/` is not writable, use any writable directory outside the repo. Use it for every scratch file and temp directory you create.
- Record every command the environment blocks (read-only file system, no network, no sign-in, missing CLI) as `not run: <reason>`, separately from product failures (a failed assertion, or a non-zero exit from product code). Stop and report only for product failures. Never report a blocked run as a pass.
- Check changed files with `git status --short --untracked-files=all` together with `git diff --stat`: the diff alone omits new files.
- Run narrow unit tests as `PYTHONPATH=tests python3 -m unittest tests.test_x ...` (some test modules import their siblings as top-level modules and fail without it).

## Verification (narrowest first)

```
PYTHONPATH=tests python3 -m unittest tests.test_repo tests.test_flow_skill tests.test_process_rules tests.test_schedule_steps tests.test_scan
git diff --numstat -- skills/*/SKILL.md agents/kaizen-auditor.md
git status --short --untracked-files=all
rg -c 'two levels above' skills agents      # no output
python3 tools/context_budget.py --root .
claude plugin validate .
python3 -m unittest discover -s tests
shellcheck -S warning hooks/*.sh
```

## Reporting

Report the numstat output, `git status --short --untracked-files=all`, the verify results (trimmed) and any skill whose structure did not fit (for example a skill with no `# ` heading). Do not commit or push. If an assumption here is wrong, stop and report instead of improvising.
