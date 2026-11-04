# fix-f round 4 (risk high, Sol high)

Read `fix-f-round3.md` first. The re-review of 62a60af returned a narrow REVISE. Round 3's symlink, directory and rg/git fixes are confirmed. Remaining:

1. **Drop `Bash(jq:*)` in both modes.** `jq -n env` and `$ENV.X` print the runner's environment, which bypasses the `env`/`printenv` hard stops. Nothing in the scheduled path needs jq. Update the pinned test (tests/test_schedule_steps.py around l.24) and docs/scheduling.md around l.139.
2. **Implicit file-command approval.** Around l.759, auto runs use `--permission-mode acceptEdits`, which auto-approves filesystem Bash commands (cp, touch, mkdir, sed, and others) inside working directories, including the add-dir'd config homes. Edit/Write deny rules may not cover them.
   - Stop using `acceptEdits` for scheduled runs. Use the default permission mode, where unapproved tools are denied in `-p` mode, and grant Edit and Write through explicit allow rules for the paths auto mode is meant to edit, keeping all existing deny rules.
   - As a second line of defence, add `Bash(cp:*)`, `Bash(touch:*)`, `Bash(mkdir:*)`, `Bash(sed:*)`, `Bash(dd:*)`, `Bash(install:*)`, `Bash(ln:*)`, `Bash(truncate:*)` and `Bash(perl:*)`, `Bash(python3 -c:*)`, `Bash(python:*)` to the auto-mode hard-stop denies. The `notes-ledger add` and `kaizen-backup` grants still need `python3 <path>`: keep those exact allow rules working, and add a test that they still match.
   - **Empirical probe, required.** In a temp HOME and project, run the real `claude -p --model haiku --max-turns 4` with the generated auto-mode flags. Prompt it to `cp` a file over a denied path and to Write a denied path. Assert that both are refused and the files are unchanged. Save the probe as a test skipped unless `KAIZEN_LIVE_PROBE=1`. Run it once with the variable set and report the result. If the probe shows the CLI behaves differently from these assumptions, adapt the design and say so.
3. **`.git` denies for config homes.** `GIT_DENY` (around l.122) is `**/.git/**`, relative to the project. Add resolved and unresolved `<home>/**/.git/**` Edit/Write denies for each add-dir'd config home, like the backup and ledger denies.
4. **Credential Read denies, orchestrator decision, folded in from a planned follow-up; the owner may revisit.** Scheduled runs (both modes) have Read and WebFetch, so a steered run could send a readable secret to a URL. Add Read (and Edit/Write) denies, in resolved and unresolved forms, for:
   - the config homes' credential files (`.credentials.json`, `auth.json`, any `*token*`/`*secret*` JSON at the top level of `~/.claude` and `~/.codex`);
   - `~/.ssh/**`, `~/.aws/**`, `~/.gnupg/**`, `~/.netrc`, `~/.config/gh/**`, `~/.docker/config.json`;
   - `**/.env` and `**/.env.*` in the project.
   Keep the list as one documented constant with a pinned test. Generic paths only, no owner names.

Do not commit, and do not bump versions. Verify: `python3 -m unittest discover -s tests`, `./scripts/rules-lint --repo .`, `git diff --check`, plus the live probe once.
