# Brief P08: CI host-probe stage, Codex in CI, repo rule wording

Agent: Terra, effort medium. Risk: low. Size: S. Group B. Runs AFTER P01 and P02 have landed on your base: `tools/host-probe` exists and the 22 `skills/*/agents/openai.yaml` sidecars exist (without them the probe's "zero skills" check fails with "22 listed"). If either is missing, stop and report.
Do not commit or push.

## Goal and why

Agent Kaizen (a Claude Code plugin, version 0.11.0) is being made to install on Codex CLI and the GitHub Copilot runtime too. Earlier packets added `tools/host-probe` (P01) and hid the skills from Codex's always-on list (P02), so the probe passes on a good tree. The probe installs the plugin into isolated temp homes with each host's CLI and checks it. This packet wires that probe into the local and CI checks so a future change that breaks the Codex or Copilot install is caught, and it fixes repo rule text that is wrong or out of date (the rules claim CI enforces the version bump on PRs, but CI has no PR trigger).

## Context (verified facts)

- `.github/workflows/ci.yml` lines 3-6: `on:` has only `push: tags: ['v*']` and `workflow_dispatch:`. No `pull_request` trigger. Job `checks` (lines 44-59) sets up Node 22, runs `npm install -g @anthropic-ai/claude-code`, then `tools/ci-local --skip-tests`.
- `tools/ci-local` (Python, 90 lines) runs stages through `stage(name, fn)`. The `plugin validation` stage (lines 81-84) is the pattern to copy: run only when the CLI is on PATH, otherwise print `SKIP: ... (... not found)`. The `version and changelog` stage only checks that the current version has a `## x.y.z` heading in CHANGELOG.md; it does not compare with a base branch.
- `tools/host-probe` (from P01): `tools/host-probe --host codex|copilot|all [--source PATH] [--worktree] [--json]`. It exports the git HEAD tree (or, with `--worktree`, the tracked and untracked-but-not-ignored files on disk) into a fresh temp dir (honours `TMPDIR`), sets `HOME`, `CODEX_HOME`, `COPILOT_HOME` to temp subfolders, prints one `PASS|FAIL|SKIP <host> <check>: <detail>` line per check, exits 1 on any FAIL and 0 otherwise. A missing CLI gives a SKIP line and exit 0. It needs no sign-in for Codex (checked on codex-cli 0.167.0). Because it exports HEAD, uncommitted edits are not probed unless `--worktree` is used. So the `ci-local` stage passes `--worktree`: a local run then probes the tree being checked (otherwise it would test the old committed version while a direct probe tests the new one), and in CI (a clean checkout) the two are the same.
- `AGENTS.md:19` and `CONTRIBUTING.md:21` carry the version-bump rule with a list of runtime-read paths: `skills/`, `agents/`, `hooks/`, `scripts/`, `templates/`, `.claude-plugin/`, `docs/autonomy.md`, `docs/outcome-log.md`. `docs/hosts.md` (new in this release, read by skills at runtime) and the new `skills/*/agents/openai.yaml` files must be covered.
- `AGENTS.md:19` ends "CI enforces this on PRs." which is false today. `CONTRIBUTING.md:32` says "CI does not run on PRs or main pushes."
- Decision D3 is made: **yes**, add a `pull_request` trigger for `main`. Implement the "yes" text; the "no" alternatives below are kept only for the record and must not be used.

## Files you may change

- `tools/ci-local`
- `.github/workflows/ci.yml`
- `AGENTS.md`
- `CONTRIBUTING.md`

## Do not touch

`.claude-plugin/` (no version bump, no CHANGELOG: P09 does that; these four files are outside the version rule), `hooks/`, `scripts/`, `skills/`, `tests/`, `tools/host-probe`, `docs/`, `README.md`.

## Steps

### 1. `tools/ci-local`: add the `host probe` stage

Directly after the `plugin validation` if/else block (after the line `print('SKIP: plugin validation (claude not found)', flush=True)`), at the same indentation, add:

```python
        if shutil.which('codex') or shutil.which('copilot'):
            stage('host probe', lambda: run([sys.executable, 'tools/host-probe', '--host', 'all', '--worktree']))
        else:
            print('SKIP: host probe (neither codex nor copilot found)', flush=True)
```

Do not add the stage under `--version-only`: the existing `if not args.version_only:` block already covers that.

### 2. `.github/workflows/ci.yml`

- In the `checks` job, directly after the `Install Claude Code` step, add:

```yaml
      - name: Install Codex CLI
        run: npm install -g @openai/codex
```

  Pin no version. Do not add a sign-in or secret.
- **[D3 = yes]** Under `on:`, between `push:` (with its `tags` line) and `workflow_dispatch:`, add:

```yaml
  pull_request:
    branches: [main]
```

  **[D3 = no]** add nothing here.

### 3. `AGENTS.md`

- Line 19 (the **Version and changelog** rule): replace the path list and the last sentence. New text of the whole bullet:
  - **[D3 = yes]** `- **Version and changelog:** any change under \`skills/\` (including \`skills/*/agents/openai.yaml\`), \`agents/\`, \`hooks/\`, \`scripts/\`, \`templates/\` or \`.claude-plugin/\`, or to \`docs/autonomy.md\`, \`docs/hosts.md\` or \`docs/outcome-log.md\` (skills read them at runtime), bumps \`version\` in \`.claude-plugin/plugin.json\` and adds a \`## x.y.z (date)\` entry to CHANGELOG.md. CI runs on PRs to \`main\` and fails when the current version has no CHANGELOG entry; it does not check that the version was bumped, so do it.`
  - **[D3 = no]** same, but the last sentence is: `CI runs only on \`v*\` tags and by hand (\`gh workflow run CI\`); its tag check fails when the version has no CHANGELOG entry. It does not check the bump, so check it yourself before a PR.`
  (Write the backticks as plain backticks; the backslashes above only protect them in this brief.)
- In the Commands code block, after the line `claude plugin validate .`, add the line `tools/host-probe --host codex           # install check in an isolated home; prints SKIP when codex is missing`.
- The sentence under the block, `CI (.github/workflows/ci.yml) also checks that every JSON file parses and that each script answers \`--help\`.` gains at the end: ` It also runs \`tools/host-probe\` when the \`codex\` or \`copilot\` CLI is installed.`

### 4. `CONTRIBUTING.md`

- Line 21 (the version-bump sentence after "Before a PR:" block): use the same path list as AGENTS.md: `skills/` (including `skills/*/agents/openai.yaml`), `agents/`, `hooks/`, `scripts/`, `templates/`, `.claude-plugin/`, and `docs/autonomy.md`, `docs/hosts.md`, `docs/outcome-log.md`.
- In the "Before a PR:" code block, after `claude plugin validate .`, add the same `tools/host-probe --host codex` line as in AGENTS.md.
- Line 32 (Release section): `CI does not run on PRs or main pushes.`
  - **[D3 = yes]** becomes `CI runs on PRs to \`main\` and on \`v*\` tags; it does not run on pushes to main.`
  - **[D3 = no]** stays unchanged.

## Acceptance criteria

1. `tools/ci-local --skip-tests` passes. With `codex` on PATH it prints `PASS: host probe` (the stage runs the probe with `--worktree`); without `codex` and `copilot` on PATH it prints `SKIP: host probe (neither codex nor copilot found)` and still exits 0.
2. `.github/workflows/ci.yml` parses as YAML, contains the `Install Codex CLI` step in the `checks` job, and (D3 = yes) a `pull_request` trigger limited to `main`. The `release` job condition is untouched.
3. The path list in `AGENTS.md` and `CONTRIBUTING.md` is the same set of nine runtime paths (`skills/` + the openai.yaml note, `agents/`, `hooks/`, `scripts/`, `templates/`, `.claude-plugin/`, `docs/autonomy.md`, `docs/hosts.md`, `docs/outcome-log.md`).
4. Neither file still says "CI enforces this on PRs", and the CONTRIBUTING Release sentence matches the workflow's real triggers.
5. `git diff --stat` and `git status --short --untracked-files=all` show only the four listed files.

## Sandbox and environment (read before running any command)

- Writable temp dir: `mkdir -p out/tmp && export TMPDIR="$PWD/out/tmp"` (`out/` is git-ignored; keep the path short). If `out/` is not writable, use any writable directory outside the repo. Use it for every scratch file and temp directory you create.
- `tools/host-probe` honours `TMPDIR` but always exports the plugin with `git archive` (or the `--worktree` file list) into a fresh directory under it and runs the host CLI from that export, never from the checkout. Do not install a host CLI from the checkout or put a host home under `out/` inside the tree: Codex fails with "File name too long" when it copies a tree that contains `out/`.
- Record every command the environment blocks (read-only file system, no network, no sign-in, missing CLI) as `not run: <reason>`, separately from product failures (a failed assertion, or a non-zero exit from product code). Stop and report only for product failures. Never report a blocked run as a pass. A probe `FAIL` whose detail is an OS or network error (permission denied, read-only file system, DNS or connection error, sign-in) counts as blocked; a `FAIL` about the product (version mismatch, skills still listed, hooks missing) is a product failure.
- Check changed files with `git status --short --untracked-files=all` together with `git diff --stat`: the diff alone omits new files.
- Run narrow unit tests as `PYTHONPATH=tests python3 -m unittest tests.test_x ...` (some test modules import their siblings as top-level modules and fail without it).

## Verification

Narrowest first.

```bash
python3 -m py_compile tools/ci-local
yq e . .github/workflows/ci.yml >/dev/null    # or: ruby -ryaml -e 'YAML.load_file(".github/workflows/ci.yml")'
rg -n 'pull_request|Install Codex CLI' .github/workflows/ci.yml
rg -n 'docs/hosts.md' AGENTS.md CONTRIBUTING.md
rg -n 'CI enforces this on PRs' AGENTS.md CONTRIBUTING.md   # expect no output
tools/ci-local --skip-tests
```

SKIP path (builds a PATH with only the tools the stages need, and no codex):

```bash
d=$(mktemp -d); for t in python3 git jq shellcheck; do ln -s "$(command -v $t)" "$d/$t"; done   # $TMPDIR must be writable (see Sandbox)
env PATH="$d:/usr/bin:/bin" sh -c '! command -v codex && ! command -v copilot'
env PATH="$d:/usr/bin:/bin" tools/ci-local --skip-tests; echo "exit $?"
rm -rf "$d"
```

Expect `SKIP: host probe (neither codex nor copilot found)` and `exit 0`. The first command guards the test: if it fails, a real `codex` or `copilot` is in `/usr/bin` or `/bin`; record `not run: codex or copilot in a system directory` for the SKIP-path run and report the normal run only. If `git` is a shim that breaks when symlinked, use a wrapper script (`#!/bin/sh`, `exec <absolute path> "$@"`) instead. If a tool the stages need (`shellcheck`, `jq`) is not installed, record `not run: <tool> missing`.

Full gate:

```bash
python3 -m unittest discover -s tests
shellcheck -S warning hooks/*.sh
claude plugin validate .
```

If `claude` is not installed in your sandbox, say so and skip only that command (the CI stage already skips it). If the `host probe` stage fails because the environment blocks it (the probe cannot write its temp home, no network, `codex` cannot run), that is not a product failure: report the exact `FAIL`/error line as `not run: <reason>`, add it to the owner's run list (checklist item O5: run `tools/host-probe --host all --worktree` outside the sandbox before release), give the SKIP-path result, and do not edit `tools/host-probe`. A probe FAIL about the product (version mismatch, skills still listed, hooks missing) is a product failure: stop and report it. Nothing here needs a sign-in. The workflow itself cannot be run here; checking its syntax is enough.

## Reporting

Report that you implemented D3 = yes, the output of `tools/ci-local --skip-tests` (both PATH variants, or `not run: <reason>`), each verify command pass/fail (or `not run: <reason>`), `git diff --stat` and `git status --short --untracked-files=all`. Do not commit or push. If an anchor line in this brief does not match the file (line numbers may have moved; match on text), say so and stop if the meaning is unclear.

## Suggested agent

Terra, effort medium. Risk low.
