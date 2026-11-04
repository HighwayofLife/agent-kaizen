# 13: end-to-end gate (run the scheduled cycle once for real)

## Goal and why
Rule (2026-11-04): a plan that adds or changes tooling ends with a packet that runs the new tools end to end on real input and pastes the trimmed output into the plan. This packet only runs and reports; it changes no code or config.

## Context
- Preconditions (check first, stop and report if one fails): packets 01-12 done; `~/.claude/bin` links to the plugin at ~/github/highwayoflife/agent-kaizen (`python3 ~/.claude/bin/kaizen-link --check | tail -1` says 0 drift, 0 broken); the installed plugin is 0.7.0 (`jq -r '.plugins["agent-kaizen@agent-kaizen-tools"][0].version' ~/.claude/plugins/installed_plugins.json`; it was a stale 0.2.0 cache copy before packet 12, which makes `/agent-kaizen:cycle` run the old skill); the owner's global config has `projectCommands`, `notesLedger`, `calibrationLadder`, `rulesLintFiles`, `localScripts`. New World (~/github/highwayoflife/NewWorld) is read-only for you.
- `~/.claude/audits/projects/index.json` may not exist on this machine; packet 09's `audit` must create it. That is part of what you verify.
- The real run spends one headless Sonnet run in PROPOSE-ONLY mode (at most 40 turns). Use the runner's own flags so the restrictions of `review_command` apply: `--project-dir` limits the review to New World, `--propose-only` forces propose mode even if a setting says auto, `--force` skips the activity gate. Never run `claude -p` by hand for this.
- "Clean" means: every command exits as described, every expected file exists and is non-empty, no line for this run containing `failed` in `~/.claude/audits/run.log`, and the drift line says 0 drift, 0 broken.
- Privacy: this repo's tests reject home-directory paths in any file under the repo, including `docs/plans/`. Replace the home directory prefix with `~` in everything you paste (`sed "s#$HOME#~#g"`), and re-run the repository tests afterwards.

## Steps
1. `python3 ~/.claude/bin/kaizen-link --check | tail -4`.
2. `~/.claude/bin/rules-lint --repo ~/github/highwayoflife/NewWorld | tail -3`.
3. Audit cost, before/after (rule: a cost claim needs a measurement): `( time KAIZEN_SKIP_CHECKS=1 python3 ~/.claude/bin/kaizen-scheduled audit --audits ~/github/highwayoflife/agent-kaizen/out/aud-a ) 2>&1 | tail -4` then the same without `KAIZEN_SKIP_CHECKS` and `--audits .../out/aud-b`. Report the difference (flag if more than 10 s). Do not use this for the real files below.
4. The real audit: `python3 ~/.claude/bin/kaizen-scheduled audit 2>&1 | tail -5`; list `ls -lt ~/.claude/audits/checks-*.md | head -1`, `ls -lt ~/.claude/audits/projects/*/project-report-*.md | head -3`, and `ls -l ~/.claude/audits/projects/index.json`; show section headings plus 2-3 lines each of the newest checks file and New World's project report.
5. Permission rehearsal (no tokens): with a short inline Python script, load the installed runner via `runpy.run_path` (path `~/.claude/bin/kaizen-scheduled`, expanded) and build the auto-mode `review_command` for New World; print only (home prefix redacted to `~`): whether the allowed list contains `notes-ledger add` and does not contain `notes-ledger set`, and the `Edit(` and `Write(` deny entries for the configured ledger files. Then run `python3 ~/.claude/bin/notes-ledger add --dry-run --date 2026-11-04 --category tooling --change "gate rehearsal" --why x --measure y --source gate` (must print what it would write and change nothing; `git -C ~/github/highwayoflife/agent-field-notes status --porcelain` is unchanged).
6. The real review: `python3 ~/.claude/bin/kaizen-scheduled review --project-dir ~/github/highwayoflife/NewWorld --propose-only --force 2>&1 | tail -8`. The produced artifact is the file `cycle-<date>.md` in the project's report folder (`~/.claude/audits/projects/<key>/`, key from `kaizen-scheduled config show --for ~/github/highwayoflife/NewWorld`'s `reports`). Show its first 25 lines; check it mentions calibration (or "none"), drift, stale rules and ledger measurement proposals.
7. `python3 ~/.claude/bin/notes-ledger due --project ~/github/highwayoflife/NewWorld | head -20` (rows too new say so).
8. In `~/github/highwayoflife/agent-kaizen/docs/plans/2026-11-04-kaizen-port/plan.md` replace the line `Result: (to be filled by packet 13)` with the redacted, trimmed outputs (at most 60 lines in a fenced block) and one line `Verdict: clean` or `Verdict: not clean (<reasons>)`. This is the only file you edit. Then `cd ~/github/highwayoflife/agent-kaizen && python3 -m unittest discover -s tests` must pass (privacy test).

## Scope / do not touch
No code, config or `~/.claude` edits except the files the tools themselves write under `~/.claude/audits/`; no commits. Do not set `schedule=always` or change any setting. If something fails, do not fix it: report the exact command and trimmed output so the orchestrator can send a fix packet.

## Acceptance criteria
1. Steps 1-7 ran and their redacted outputs are in plan.md (including the `index.json` creation and the with/without timing).
2. The review ran with `--propose-only --force` and the `cycle-<date>.md` artifact exists and is non-empty.
3. The verdict line is present and matches the evidence.
4. The full repository suite passes after the paste.

## Verification
```
rg -n "^Verdict:" ~/github/highwayoflife/agent-kaizen/docs/plans/2026-11-04-kaizen-port/plan.md
rg -n "/Users/" ~/github/highwayoflife/agent-kaizen/docs/plans/2026-11-04-kaizen-port/ || echo "no home paths"
cd ~/github/highwayoflife/agent-kaizen && python3 -m unittest discover -s tests
tail -5 ~/.claude/audits/run.log
```

## Reporting
The verdict, the list of produced files with sizes, any failed step with trimmed output. Do not commit or push.

## Suggested agent / model / effort
sonnet-engineer, Sonnet, medium. Risk: normal.
