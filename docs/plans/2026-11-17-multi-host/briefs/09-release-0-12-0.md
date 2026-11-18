# Brief P09: release 0.12.0 and end-to-end gate

Agent: Terra, effort medium. Risk: low. Size: S. Runs last, after P01 to P08 (and C1 if it was needed) have landed on the branch.
Do not commit or push.

## Goal and why

Agent Kaizen (a Claude Code plugin, now 0.11.0) has been made to install on Codex CLI and the GitHub Copilot runtime. Earlier packets changed code, docs and tests but deliberately did not touch the version or CHANGELOG.md (parallel worktrees would conflict). This packet does the release bookkeeping once, then runs the new tooling end to end on the real final tree and records the output. The plan is not done until that run is clean.

## Context

- The version rule (AGENTS.md): any change under `skills/`, `agents/`, `hooks/`, `scripts/`, `templates/` or `.claude-plugin/`, or to `docs/autonomy.md` or `docs/outcome-log.md`, bumps `version` in `.claude-plugin/plugin.json` and adds a `## x.y.z (date)` entry to CHANGELOG.md. This release also changes `docs/hosts.md` and every skill.
- `CHANGELOG.md` format (see the `## 0.11.0 (2026-11-17)` entry): a title line, a short summary sentence, then groups. A group is a line of backticked file or feature names ending with a colon, a blank line, and bullets. The GitHub release job extracts the entry with the regex `^## <version>(?: |$)[^\n]*\n(.*?)(?=^## |\Z)`, so the heading must be exactly `## 0.12.0 (YYYY-MM-DD)`.
- `tools/ci-local` checks that the current version has a `## <version>` heading in CHANGELOG.md. `tests/test_repo.py` checks the same (`test_manifest_names_match`).
- Each earlier packet that changed shipped behaviour left a changelog fragment in `docs/plans/2026-11-17-multi-host/changelog/`: `P02.md`, `P03.md`, `P04.md`, `P05.md`, `P06.md`, `P07.md`, and `C1.md` only if contingent packet C1 landed. (P01 and P08 have none: `tools/` and CI are not shipped.) A fragment is bullets, sometimes with a heading line. Keep each bullet's wording; you may fix typos and reorder. Group headings are FIXED (use exactly these, a line of backticked names ending with a colon, then a blank line, then the bullets): P02 `` `skills/*/agents/openai.yaml`: ``; P03 `` `docs/hosts.md`, `docs/autonomy.md`: ``; P04 `` `skills`: ``; P05 `` `hooks`: ``; P06 `` `kaizen-doctor`, `kaizen-scan`, `token-audit`: ``; P07 as written in its fragment (`` `README`, `plugin.json`: ``); C1 (when present) `` `.github/plugin/plugin.json`, `hosts/copilot/hooks.json`: ``. Keep any fragment's own heading line only if it equals the fixed one.
- `tools/host-probe` (P01) installs the plugin into isolated temp homes with the `codex` and `copilot` CLIs and checks it. `--worktree` probes the working tree's tracked files instead of `HEAD`, so uncommitted edits count. It needs no sign-in for Codex; Copilot lines print `SKIP` when `copilot` is missing or needs sign-in.
- The hook config `hooks/hooks.json` must be byte-identical to commit `d1accc4` (release 0.11.0). Claude Code behaviour is unchanged by design.
- Contingent packet C1 (a Copilot-only manifest `.github/plugin/plugin.json` plus `hosts/copilot/hooks.json`) exists only if the owner's live Copilot check failed on hooks. Detect it with `ls .github/plugin/plugin.json hosts/copilot/hooks.json changelog/C1.md`. When it landed, its manifest carries a `version` that `tests/test_repo.py` requires to equal `.claude-plugin/plugin.json`'s, so you bump both in the same step and include its fragment; if you bump only one, that test fails.
- Codex asks users to trust plugin hooks in `/hooks` once, and again after an update that changes a hook script. P05 changed three hook scripts, so Codex users must re-trust after updating. The changelog must say this.
- D2 (Copilot labelled experimental) is decided: yes. README says Copilot is experimental, and so does the changelog. The lines tagged **[D2]** below are used as written.

## Files you may change

- `.claude-plugin/plugin.json`: the `version` field only, from `0.11.0` to `0.12.0`.
- `.github/plugin/plugin.json` (only if C1 landed): the `version` field only, from `0.11.0` to `0.12.0`.
- `CHANGELOG.md`: add the new entry directly above `## 0.11.0 (2026-11-17)`.
- `docs/plans/2026-11-17-multi-host/plan.md`: add the end-to-end result (see Step 3).

## Do not touch

Everything else. In particular not `hooks/`, `skills/`, `scripts/`, `tests/`, `tools/`, `README.md`, the fragments in `changelog/`, `.claude-plugin/marketplace.json`, or any other field of `plugin.json`. Delete nothing. If a gate command fails because of something in another file, stop and report; do not fix it here.

## Steps

### 1. Preconditions

```bash
ls docs/plans/2026-11-17-multi-host/changelog/
ls tools/host-probe docs/hosts.md
ls .github/plugin/plugin.json hosts/copilot/hooks.json 2>/dev/null   # present only if C1 landed
jq -r .version .claude-plugin/plugin.json          # expect 0.11.0
git status --short --untracked-files=all > "$TMPDIR/status-before.txt"   # baseline for the final file check
```

Fragments `P02.md` to `P07.md` must all exist (plus `C1.md` if `.github/plugin/plugin.json` exists). If one is missing, stop and report which. If `.claude-plugin/plugin.json` is already 0.12.0, stop and report.

### 2. Version and changelog

```bash
jq -r .version .claude-plugin/plugin.json
sed -i.bak 's/"version": "0.11.0"/"version": "0.12.0"/' .claude-plugin/plugin.json && rm .claude-plugin/plugin.json.bak
jq -r .version .claude-plugin/plugin.json          # expect 0.12.0
date +%F                                           # use this date in the heading
git diff --stat -- .claude-plugin/plugin.json      # expect 1 insertion, 1 deletion
```

If C1 landed, bump its manifest the same way and check parity:

```bash
sed -i.bak 's/"version": "0.11.0"/"version": "0.12.0"/' .github/plugin/plugin.json && rm .github/plugin/plugin.json.bak
jq -r .version .claude-plugin/plugin.json .github/plugin/plugin.json     # both 0.12.0
PYTHONPATH=tests python3 -m unittest tests.test_repo                       # includes the C1 parity test
```

Write the CHANGELOG entry above `## 0.11.0`:

```
## 0.12.0 (<date +%F output>)

Codex CLI and GitHub Copilot support: the same plugin installs on Codex CLI and the Copilot runtime. Claude Code behaviour is unchanged.

<groups built from the fragments>

Updating on Codex: run `/hooks` again and trust the changed hooks; hooks do nothing until you do.
```

Build the groups from `changelog/P02.md` to `P07.md` (and `C1.md` if present), with the fixed headings listed under Context. Add this sentence as the first bullet of the first group or as its own group `` `host support`: ``: "**[D2]** GitHub Copilot support is experimental and has not been checked in a live session; Copilot usage is not measured yet." Do not add claims that are not in a fragment or in the lines above. Plain, short sentences; no marketing words.

### 3. End-to-end gate (real input, once, on the final tree)

Run these in this order. Save trimmed output (first and last lines that show PASS/FAIL/SKIP and the exit code) as you go:

```bash
git diff --exit-code d1accc4 -- hooks/hooks.json; echo "hooks.json diff exit $?"     # expect 0
tools/host-probe --host all --worktree; echo "exit $?"
tools/ci-local; echo "exit $?"          # its host-probe stage also runs with --worktree, so it checks this same tree
UV_OFFLINE=1 tools/ci-local --python 3.9; echo "exit $?"
```

Expectations:
- `hooks/hooks.json` diff: no output, exit 0.
- `host-probe --worktree`: Codex lines all `PASS` (install, installed version equals 0.12.0, zero `agent-kaizen:` skills listed, hooks listed or a stated `SKIP`); Copilot lines `PASS` or `SKIP`; exit 0. A `FAIL` line means stop and report the line.
- `tools/ci-local`: every stage `PASS` or `SKIP`, ending with `PASS: version and changelog`, exit 0.
- `UV_OFFLINE=1 tools/ci-local --python 3.9` needs the `uv` tool and a Python 3.9 that is already provisioned (offline mode must not download one). If it cannot run in your sandbox, write `not run: <reason>` and list it under owner checklist item O5 in your report; do not claim it passed.

If `codex` is not installed in your sandbox, `tools/host-probe` prints SKIP lines: say so, and list the Codex check under `not run` for the owner (O5). If the probe or the `host probe` stage of `tools/ci-local` fails with an OS or network error (permission denied, read-only file system, DNS or connection error, sign-in, no writable temp dir), that is a blocked run, not a product failure: record `not run: <reason>`, list it under O5, and continue. A probe `FAIL` about the product (installed version is not 0.12.0, skills still listed, hooks missing) is a product failure: stop and report it. Owner checklist O5: run `tools/host-probe --host all --worktree` and `tools/ci-local --python 3.9` outside the sandbox before the release is tagged.

Then add the result to `docs/plans/2026-11-17-multi-host/plan.md`: directly under the `## Packets` table (after the table, before "Parallel groups") add a heading line `### P09 end-to-end result (<date>)` and a fenced block with the trimmed output of the four commands above and `not run: <reason>` for any that could not run. (The table has no result column, so the block goes below it.)

### 4. README check

```bash
rg -n -i 'experimental' README.md
```

The Copilot rows and install blocks must be labelled experimental (open owner checks O1/O2 are not done). If README makes a Copilot claim without that label, stop and report; do not edit README.

## Acceptance criteria

1. `jq -r .version .claude-plugin/plugin.json` prints `0.12.0` and no other field of `plugin.json` changed (`git diff -- .claude-plugin/plugin.json` is one changed line).
2. `CHANGELOG.md` has exactly one `## 0.12.0 (YYYY-MM-DD)` heading directly above `## 0.11.0`, contains the Codex re-trust sentence, and every fragment `P02` to `P07` (and `C1` when present) is represented under its fixed heading.
3. `git diff --exit-code d1accc4 -- hooks/hooks.json` exits 0.
4. `tools/host-probe --host all --worktree` exits 0 with no `FAIL`; on Codex the installed version is 0.12.0 and zero `agent-kaizen:` skills are listed (or the result is recorded `not run: <reason>` / the line says SKIP with the reason).
5. `tools/ci-local` exits 0 (or its blocked probe stage is recorded `not run: <reason>`). `UV_OFFLINE=1 tools/ci-local --python 3.9` exits 0, or is reported `not run: <reason>`.
6. The plan's P09 result block exists and matches what you ran.
7. `git diff --stat` shows only `.claude-plugin/plugin.json`, `CHANGELOG.md`, `docs/plans/2026-11-17-multi-host/plan.md` (plus `.github/plugin/plugin.json` if C1 landed); `git status --short --untracked-files=all` compared with `$TMPDIR/status-before.txt` adds no other file. If C1 landed, `jq -r .version` of the two manifests is the same.

## Sandbox and environment (read before running any command)

- Writable temp dir: `mkdir -p out/tmp && export TMPDIR="$PWD/out/tmp"` (`out/` is git-ignored; keep the path short). If `out/` is not writable, use any writable directory outside the repo. Use it for every scratch file and temp directory you create.
- `tools/host-probe` honours `TMPDIR` but always exports the plugin with `git archive` (or the `--worktree` file list) into a fresh directory under it and runs the host CLI from that export, never from the checkout. Do not install a host CLI from the checkout or put a host home under `out/` inside the tree: Codex fails with "File name too long" when it copies a tree that contains `out/`.
- Python 3.9 check: `UV_OFFLINE=1 tools/ci-local --python 3.9`, only when Python 3.9 is already provisioned for `uv`. If `uv` would have to download it, do not run it.
- Record every command the environment blocks (read-only file system, no network, no sign-in, missing CLI, `uv` download) as `not run: <reason>`, separately from product failures (a failed assertion, or a non-zero exit from product code). Stop and report only for product failures. Never report a blocked run as a pass. A probe `FAIL` whose detail is an OS or network error (permission denied, read-only file system, DNS or connection error, sign-in) counts as blocked; a `FAIL` about the product (version mismatch, skills still listed, hooks missing) is a product failure.
- Check changed files with `git status --short --untracked-files=all` together with `git diff --stat`: the diff alone omits new files.
- Run narrow unit tests as `PYTHONPATH=tests python3 -m unittest tests.test_x ...` (some test modules import their siblings as top-level modules and fail without it).

## Verification

Narrowest first:

```bash
jq -r .version .claude-plugin/plugin.json
rg -n '^## 0\.12\.0 \(' CHANGELOG.md
PYTHONPATH=tests python3 -m unittest tests.test_repo
git diff --exit-code d1accc4 -- hooks/hooks.json
git status --short --untracked-files=all | diff - "$TMPDIR/status-before.txt"   # only the files named in acceptance criterion 7
```

Then the gate from Step 3, then the standard commands:

```bash
python3 -m unittest discover -s tests
shellcheck -S warning hooks/*.sh
claude plugin validate .
```

If `claude` is not installed in your sandbox, say so and skip only that command. Commands that need network or a sign-in (the `--python 3.9` run if it would have to download Python, anything with a signed-in Copilot) go to the owner checklist (O5) in your report as `not run: <reason>`.

## Reporting

Report: each gate command with exit code and its trimmed output, the CHANGELOG entry you wrote, anything marked `not run: <reason>` (kept separate from product failures), `git diff --stat` and `git status --short --untracked-files=all`. Do not commit or push. If a fragment is missing or contradicts the code, stop and report instead of improvising.

## Suggested agent

Terra, effort medium. Risk low.
