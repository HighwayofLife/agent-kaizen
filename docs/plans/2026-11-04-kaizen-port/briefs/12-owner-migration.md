# 12: owner migration (`~/.claude`), plugin update, notes repo rows

## Goal and why
Make the owner's live setup use the plugin as the single source: `~/.claude/bin` and one hook link to the plugin, owner-specific values move into `~/.claude/agent-kaizen.json` and a user pattern file, the stale project registry is retired, the installed plugin is updated to 0.7.0, the old scheduled jobs are replaced (with the owner's OK), and the change is recorded in the notes repo. This packet edits files outside the repo, so it follows `~/.claude/CLAUDE.md`: every `~/.claude` edit takes a `kaizen-backup begin/finish`.

## Context
- Plugin repo: ~/github/highwayoflife/agent-kaizen with packets 01-11 merged into the checked-out branch. Run every plugin script from this path (`python3 ~/github/highwayoflife/agent-kaizen/scripts/NAME`), never from the plugin cache: the cache path changes per version, so `kaizen-link --mode auto` would copy instead of link. Notes repo: ~/github/highwayoflife/agent-field-notes (`data/changes.csv`, `findings/changes-timeline.md`). New World (~/github/highwayoflife/NewWorld) is another session's active repo: you only READ it. Never write into it (this includes `install-schedule --auto <project>` and `kaizen-scheduled config set --for <New World>`, which would create its `docs/kaizen/config.json`).
- The marketplace `agent-kaizen-tools` is a directory source pointing at the repo, but the INSTALLED plugin is a stale cache copy: `jq -r '.plugins["agent-kaizen@agent-kaizen-tools"][0] | .version, .installPath' ~/.claude/plugins/installed_plugins.json` shows 0.2.0 under `~/.claude/plugins/cache/...`. So `/agent-kaizen:cycle` runs the old skill until the plugin is updated.
- Live state (verified 2026-11-04): `~/.claude/bin/` has token-audit (old fork), kaizen-token-audit (old fork; run by launchd), kaizen-backup (identical to the plugin's), rules-lint (old, hardcoded patterns) + `bin/tests/test_rules_lint.py`, codex-review/codex-dispatch/codex-run/codex_common.py/dispatch-status (owner-only features, stay local), `preambles/` (extra `3d.md`, stays local), `prompts/` (identical). `~/.claude/hooks/` has after-compact.sh, block-image-read.sh, limit-big-read.sh, subagent-context.sh (owner-specific content, stay local) and session-notes.sh (replace by the plugin's generic hook). `~/.claude/agent-kaizen.json` = `{"autonomy":"auto","maxChangesPerRun":3,"allowInstalls":false}`. `~/.claude/audits/project-repos.txt` holds the New World path; the OLD `kaizen-token-audit` still reads it, so it must stay until the launchd step is done. LaunchAgents: `com.highwayoflife.token-audit` (runs `bin/token-audit --days 3 --codex`; harmless to link, the plugin script accepts the same flags and writes to `~/.claude/audits`), `com.agent-kaizen.audit` and `com.agent-kaizen.review` (run `bin/kaizen-token-audit`; review also runs `cd NewWorld && claude -p '/agent-kaizen:cycle auto' ...`).
- Owner's stale patterns to move out of the old rules-lint (read them from `PATTERNS` in `~/.claude/bin/rules-lint` before replacing it): `\b400k\b|\b250k\b`, `w/ Sol`, `Sol-tier`, `under ~50 lines`, `(per[- ]packet|every packet)[^|\n]{0,40}\bSol\b (review|diff)`, `(landing )?note (names|says) .fix-origin`, `use .--policy.`. Add one more: the superseded CLAUDE.md item 7 wording `bin/token-audit` runs every 3 days \(launchd\)` (regex: ``bin/token-audit` runs every 3 days``).
- Hard stops (the plugin's docs/autonomy.md): installing, changing or removing scheduled jobs (launchd) needs the owner's explicit OK; updating the installed plugin also asks the caller first. Ask your caller before step 6 (plugin update) and before Branch A. The two branches:
  - **Branch A (launchd approved):** steps 1-9 then 10-12.
  - **Branch B (deferred, no OK yet):** steps 1-9 only for the items marked "both", skip 10-11, keep `kaizen-token-audit` in `localScripts`, keep `project-repos.txt`, keep the old jobs untouched (they keep working on the old files), CLAUDE.md wording stays conditional (below), and still run step 12 (notes rows with status `planned` where the step is pending) and step 13 (`kaizen-backup finish`).

## Steps (order matters)
1. Baseline (both): `python3 ~/github/highwayoflife/agent-kaizen/scripts/kaizen-link --check --json > ~/github/highwayoflife/agent-kaizen/out/drift-before.json`; note the drift count (last line of the text form).
2. Backup (both): the list of files to back up comes from the dry-run plan: `python3 .../kaizen-link --json` (no `--apply`); take every target that exists as a REGULAR file and would be replaced, plus `~/.claude/agent-kaizen.json`, `~/.claude/CLAUDE.md`, `~/.claude/hooks/session-notes.sh`, `~/.claude/bin/tests/test_rules_lint.py`, `~/.claude/audits/project-repos.txt` (Branch A) and the three LaunchAgent plists (Branch A). Directories cannot be backed up (`kaizen-backup begin` rejects non-regular files): `prompts` is identical and `preambles` is LOCAL, so neither changes. Then `python3 .../kaizen-backup begin --skill port --ledger "Link ~/.claude/bin to the agent-kaizen plugin" FILE...`; keep the change dir.
3. Config via the plugin (both; no hand-editing JSON): `python3 .../kaizen-scheduled config set KEY=JSON` for `calibrationLadder='["haiku","terra low","terra medium","terra high","sol medium","sol high"]'`; `rulesLintFiles='["orchestrator/*.md","planning/*.md"]'`; `notesLedger` with csv `~/github/highwayoflife/agent-field-notes/data/changes.csv` and timeline `~/github/highwayoflife/agent-field-notes/findings/changes-timeline.md`; `localScripts` = codex-review, codex-dispatch, codex-run, codex_common.py, dispatch-status, preambles, after-compact.sh, block-image-read.sh, limit-big-read.sh, subagent-context.sh, **kaizen-token-audit** (removed again in step 10); `projectCommands` for the New World path: `outcomeLog` out/packets.jsonl; `speedReport` `["python3","-I","tools/speed_report.py","--markdown"]`; `shadowStatus` `["python3","-I","tools/review_batch.py","--shadow-status"]`; `slowTests`: run `python3 -I tools/test_timing_report.py --help` inside New World first and configure `--over` only if it runs without a report path, otherwise omit it and say so. Run each configured command once by hand (read-only; the shadow command writes `review/shadow.json` only when it prints STOP, which is expected).
4. Write `~/.claude/kaizen-rules-lint.txt` with the eight patterns above (one regex per line, a `# reason` comment above each) (both).
5. Move the superseded old rules-lint test (both): `mv ~/.claude/bin/tests/test_rules_lint.py ~/.claude/bin/tests/test_rules_lint.py.replaced-$(date +%Y%m%d)`.
6. Plugin update (both, after the caller's OK): use `claude plugin --help` to find the marketplace-update and plugin-update commands (the interactive forms are `/plugin marketplace update agent-kaizen-tools` and the plugin update); then verify `jq -r '.plugins["agent-kaizen@agent-kaizen-tools"][0].version' ~/.claude/plugins/installed_plugins.json` prints 0.7.0. If it cannot be done non-interactively, report the exact commands for the owner and continue.
7. Link (both): `python3 .../kaizen-link --apply --replace --mode auto` (LOCAL names are skipped by the tool). Then `kaizen-link --check` must exit 0 (LOCAL rows expected). Check the plugin repo is untouched: `git -C ~/github/highwayoflife/agent-kaizen status --porcelain` shows nothing except ignored `out/`. If a managed script fails `--help` through its link, `kaizen-link --unlink --restore-replaced` and report.
8. Enrolment check (both): `python3 .../kaizen-scheduled review --dry-run` lists the New World project. Do NOT retire the registry yet.
9. `~/.claude/CLAUDE.md` item 7 (both): Branch B wording: "Token audit. Audits run every 3 days (launchd) into `~/.claude/audits/`; the plugin's `kaizen-scheduled audit` also writes `checks-*.md` and per-project `project-report-*.md` once the schedule is moved (pending owner approval)." Branch A wording: "`kaizen-scheduled audit` (installed by `install-schedule`) runs every 3 days into `~/.claude/audits/` ..." Keep the review instruction; leave item 8. Then `python3 .../rules-lint --repo ~/github/highwayoflife/NewWorld`; fix hits in files you own, report others.
10. **Branch A only**: schedule. In the step 2 change, also record reverse actions: `python3 .../kaizen-backup action CHANGE_DIR --did "launchctl bootout ... <plist>" --undo "launchctl bootstrap gui/$(id -u) <plist>"` for each job. Then for each of the three jobs: `launchctl bootout gui/$(id -u) <plist>`, and move the retired plists out of `~/Library/LaunchAgents` into `~/.claude/audits/retired-launchagents/` (so they do not load at next login). Remove `kaizen-token-audit` from `localScripts` (`config set localScripts=[...]` without it) and re-run step 7. Run `python3 .../install-schedule --apply --review` with `--auto none` (propose). The old review job ran `cycle auto` in New World; keeping auto means either global `--auto all` (affects every project) or a `docs/kaizen/config.json` inside New World (outside this plan): do neither, report it as an owner decision. Confirm with `launchctl list | rg kaizen`.
11. **Branch A only**: retire the registry: `mv ~/.claude/audits/project-repos.txt ~/.claude/audits/project-repos.txt.replaced-$(date +%Y%m%d)` after `kaizen-scheduled review --dry-run` still lists New World.
12. Notes repo (both; do not commit): `python3 .../notes-ledger set --match "Port all self-improvement tooling" --status active`; then `notes-ledger add` rows (date 2026-11-04, category `tooling`) for: bin/hook links with drift check (measure: `kaizen-link --check` drift count from step 1 to 0); project report with calibration proposals (measure: first report written for New World, calibration rows present); rules-lint moved to the plugin with user patterns; session-notes hook from the plugin; launchd move (status `planned` in Branch B). Each `--why` and `--measure` is one sentence.
13. `python3 .../kaizen-backup finish CHANGE_DIR` (both, even when deferred).

## Rollback (document in your report; rehearse steps a-b without running undo)
a. `python3 .../kaizen-link --unlink --restore-replaced` FIRST. `kaizen-backup undo` copies with `shutil.copy2`, which follows symlinks and would overwrite plugin sources if a link were still in place.
b. Then `python3 .../kaizen-backup undo last`.
c. Then run the recorded reverse `launchctl bootstrap ...` commands by hand (undo prints them, it never runs them), move the plists back from `retired-launchagents/` first.
After a rehearsal-free check, confirm `git -C ~/github/highwayoflife/agent-kaizen status --porcelain` is empty.

## Scope / do not touch
Only the files named above and the notes repo's two data files. Do not edit New World or the plugin repo (except the `out/` scratch file). Do not delete anything: rename with `.replaced-<date>` or move to `retired-launchagents/`. Do not commit or push either repo.

## Acceptance criteria
1. `kaizen-link --check` exits 0 after step 7; before count and after count are in your report; plugin repo status is clean.
2. `~/.claude/bin/token-audit --help` and `~/.claude/bin/kaizen-scheduled config show` work through the links; `config show` lists the five keys with source `global`.
3. LOCAL files are byte-identical to before (sha256 of `codex-review`, `codex-dispatch`, `preambles/*` before and after).
4. `rules-lint --repo ~/github/highwayoflife/NewWorld` runs with the eight owner patterns (hits or 0, never "no patterns configured").
5. The installed plugin version is 0.7.0 (or the report says why not and gives the commands).
6. Notes CSV has the new rows with `measured=no` and the timeline matching rows; `git -C ~/github/highwayoflife/agent-field-notes diff --stat` shows only those two files.
7. Branch A: `launchctl list | rg kaizen` shows only the new jobs, retired plists are outside LaunchAgents, `project-repos.txt` is renamed and `review --dry-run` still lists New World. Branch B: the old jobs and the registry are untouched and the report says what is pending.
8. `kaizen-backup list` shows the change as finished in both branches.

## Verification
```
python3 ~/github/highwayoflife/agent-kaizen/scripts/kaizen-link --check | tail -3
~/.claude/bin/kaizen-scheduled config show | jq 'keys'
python3 ~/github/highwayoflife/agent-kaizen/scripts/kaizen-scheduled review --dry-run | head -20
git -C ~/github/highwayoflife/agent-kaizen status --porcelain
git -C ~/github/highwayoflife/agent-field-notes diff --stat
jq -r '.plugins["agent-kaizen@agent-kaizen-tools"][0].version' ~/.claude/plugins/installed_plugins.json
python3 ~/github/highwayoflife/agent-kaizen/scripts/kaizen-backup list | head -3
```

## Reporting
Per step: done/skipped; which branch; drift before/after; failures; owner decisions pending (launchd, auto mode for New World, plugin update). Do not commit or push. Stop and report if a link breaks a script or `--check` cannot reach 0 without changing a plugin script.

## Suggested agent / model / effort
sonnet-engineer, Sonnet, medium (Codex cannot write `~/.claude`). Risk: high (replaces live tooling and scheduled jobs; per-packet review).

## Owner decisions (2026-11-04), which settle this brief's open choices
- **Launchd: Branch A (switch now) is approved.**
  - Unload the old jobs and move their plists to `~/.claude/audits/retired-launchagents/`, recording the reverse `launchctl` commands via `kaizen-backup action`.
  - Install the plugin's scheduled jobs with `install-schedule`.
  - `kaizen-token-audit` leaves `localScripts` as part of Branch A.
  - The Branch B (deferred) wording is not used.
- **New World keeps `auto` mode.** The owner explicitly authorises this project-config write.
  - Before changing anything, add the New World project config file that holds the mode to this packet's `kaizen-backup begin` file list.
  - Set or keep `auto` through the plugin's supported command, not by hand-editing the file, and record it in the migration notes.
  - This relies on packet 09's ledger integrity guard (09-fix2), which must be merged first.
