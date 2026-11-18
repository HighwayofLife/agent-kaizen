# Brief P02: Codex skill visibility (`agents/openai.yaml` x22) and the context budget

Suggested agent: Terra, low effort. Risk: low. Size: S. Group A (runs in parallel with P01, P03, P05, P06; you own `tests/test_repo.py`, `tools/context_budget.py` and `tests/test_context_budget.py` in this group).

## Goal and why

Agent Kaizen is a Claude Code plugin with 22 skills, each with `disable-model-invocation: true` so Claude lists none of them in its always-on context. Codex CLI ignores that flag: it lists every skill as `agent-kaizen:<name>` on every turn (3,810 bytes, against this repo's own 1,024-byte budget). Codex honours a per-skill sidecar file `skills/<name>/agents/openai.yaml` with `policy.allow_implicit_invocation: false`. Add that file to all 22 skills, and teach the repo test and the context-budget tool to check it.

## Context and facts you can rely on

- Measured 2026-11-17 with `codex-cli 0.167.0`: with the sidecar added to all 22 skills in a clean export, `codex debug prompt-input` listed 0 `agent-kaizen:` skills (before: 22), and `claude plugin validate .` still passed ("Validation passed with warnings"; the warnings exist on the unmodified tree too). Claude Code and Copilot ignore the file.
- Exact sidecar content (two lines, trailing newline):
  ```
  policy:
    allow_implicit_invocation: false
  ```
- `tests/test_repo.py:12` builds `SKILLS` from `skills/*/SKILL.md`; the existing skill frontmatter test is at `:44-50`. Add your new test next to it.
- `tools/context_budget.py:70-90` (function `check`, loop over `('agent', 'agents/*.md'), ('skill', 'skills/*/SKILL.md')`): a skill's description counts toward the budget only when `disable-model-invocation != 'true'` (`visible = kind == 'agent' or disabled != 'true'`). The loop also appends an error for any skill that lacks the flag (keep that). `tools/context-budget.json` holds `budget_bytes: 1024` and the hook entries; DO NOT edit it (P05 owns it).
- `tests/test_context_budget.py` builds a temp repo in `setUp` (`skills/a/SKILL.md` with the flag, no sidecar) and asserts `Total: 18 UTF-8 bytes`. Once Codex visibility counts, a skill without a sidecar adds its description bytes, so update `setUp` to write the sidecar for `skills/a` so existing assertions keep their meaning.

## Scope

Create: `skills/<name>/agents/openai.yaml` for all 22 skills (22 new files). Use this exact command, then check the count:
```
for d in skills/*/; do mkdir -p "$d/agents"; printf 'policy:\n  allow_implicit_invocation: false\n' > "$d/agents/openai.yaml"; done
ls skills/*/agents/openai.yaml | wc -l      # 22
```
Edit: `tests/test_repo.py`, `tools/context_budget.py`, `tests/test_context_budget.py`.
Create: `docs/plans/2026-11-17-multi-host/changelog/P02.md` (`mkdir -p` the directory) containing exactly this one bullet:
`- Codex no longer lists every skill on every turn: each skill ships agents/openai.yaml with implicit invocation off.`

Do NOT touch: `.claude-plugin/plugin.json` (version), `CHANGELOG.md` (only P09 edits them; the changelog fragment is yours instead), `tools/context-budget.json`, any `SKILL.md`, hooks, scripts, README, other tests.

## Required changes

1. `tests/test_repo.py`: new test `test_skills_have_codex_visibility_sidecar` (loop over `SKILLS` with `subTest`): `skills/<name>/agents/openai.yaml` exists and its text equals exactly `policy:\n  allow_implicit_invocation: false\n`.
2. `tools/context_budget.py`: a skill counts as visible if Claude lists it (`disable-model-invocation != 'true'`) OR Codex lists it (no `agents/openai.yaml` next to the `SKILL.md`, or one that does not set `allow_implicit_invocation: false`). Parse the sidecar with a regex only (no YAML library), for example `re.search(r'(?m)^\s*allow_implicit_invocation:\s*false\s*$', text)`. Print ` (disabled)` after the byte count only when the skill is hidden on both hosts. Agents unchanged. Keep the existing error for a skill missing `disable-model-invocation: true`. Python 3.9, stdlib only.
3. `tests/test_context_budget.py`: update `setUp` as noted; add cases: (a) skill with the flag but no sidecar counts its description bytes and no `(disabled)` marker; (b) sidecar present with the false policy counts 0 and prints `(disabled)`; (c) sidecar present without the policy line counts bytes.

## Acceptance criteria

1. 22 sidecar files exist, each byte-identical to the content above (the new repo test passes; deleting one sidecar makes it fail: confirm once by hand, restore it).
2. `python3 tools/context_budget.py --root .` passes; the total stays 823 bytes (all 22 skills show `(disabled)`). `tools/context-budget.json` is not edited here (P05 changes only its three `sha256` values, preserving the literal text and byte counts).
3. `claude plugin validate .` passes (warnings as before).
4. `git status --short --untracked-files=all` shows exactly: 22 new sidecar files, the 3 edited files, and the new changelog fragment. No edit to `plugin.json`, `CHANGELOG.md` or `tools/context-budget.json`.

## Sandbox and environment (read before running any command)

- Writable temp dir: `mkdir -p out/tmp && export TMPDIR="$PWD/out/tmp"` (`out/` is git-ignored; keep the path short). If `out/` is not writable, use any writable directory outside the repo. Use it for every scratch file and temp directory you create.
- Record every command the environment blocks (read-only file system, no network, no sign-in, missing CLI) as `not run: <reason>`, separately from product failures (a failed assertion, or a non-zero exit from product code). Stop and report only for product failures. Never report a blocked run as a pass.
- Check changed files with `git status --short --untracked-files=all` together with `git diff --stat`: the diff alone omits new files.
- Run narrow unit tests as `PYTHONPATH=tests python3 -m unittest tests.test_x ...` (some test modules import their siblings as top-level modules and fail without it).

## Verification (narrowest first)

```
PYTHONPATH=tests python3 -m unittest tests.test_repo tests.test_context_budget
python3 tools/context_budget.py --root .
claude plugin validate .
python3 -m unittest discover -s tests
shellcheck -S warning hooks/*.sh
git status --short --untracked-files=all
git diff --stat
```
Optional, owner-side (needs `codex`, no sign-in): `tools/host-probe --host codex` once P01 has landed; it should then show 0 skills listed. Not required for this packet; if run and blocked by the environment, record `not run: <reason>`.

## Reporting

Report the verify output (trimmed), the file counts, and any deviation. Do not commit or push. If an assumption here is wrong (for example the budget total changes or Codex-visible skills are counted differently by an existing test), stop and report.
