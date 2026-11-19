# FX5: worktree facts, prune launcher, allow-rule recovery, dispatch-status privacy

Risk: high. Model: sol / high.
Sol reason: security-sensitive Git invocation (clean-filter execution), interpreter trust, and recovery ownership.

## Items
1. `scripts/kaizen_worktree_facts.py:217` — the full staged-index scan exceeds the 1 MiB output cap at about 18,000 short paths; those repositories lose clean/dirty results that `518da76` reported. Stream or early-exit (clean/dirty needs only the first difference).
2. `scripts/kaizen_worktree_facts.py:293` — the identity guard requires a resolvable `HEAD`; newly initialised repositories report `clean=unknown` even when they contain untracked files. Handle the unborn-branch case.
3. `scripts/kaizen_worktree_facts.py:290` (clean-filter race) — Git reloads configuration and the index after the safety check, so a concurrent update can make advisory status execute a clean filter. Run status with filters disabled by construction (for example `-c filter.<name>.clean=`/`process=` overrides for every configured filter driver, `core.fsmonitor=false`, a scrubbed environment and `GIT_CONFIG_NOSYSTEM`, or plumbing that never runs filters) instead of a check-then-run.
4. `scripts/worktree-prune:1` — PATH-interpreter item: the shebang is `#!/usr/bin/env -S python3 -I` so a PATH-resolved python runs it. Keep that shebang (pinning `/usr/bin/python3` broke supported setups) but make the trust check in-script: refuse to perform any removal unless the running interpreter's real path is owned by root or the current user and not group/world-writable, and the script's own file likewise.
5. `scripts/allow-rule:747` (FA5 item 4, interrupted-add ownership) — recovery adopts an editor-added grant without proof of publication when the staged file is missing, so a later undo can revoke the editor's grant. Record publication proof (a journal entry written before publishing, matched by content hash) so recovery adopts only grants it published; a missing staged file with no proof is left alone and reported. The existing recovery test that requires adopting that case must be changed to the safe behaviour; explain in the report.
6. `scripts/dispatch-status` (P28 gate) — it prints every running dispatch command line on the machine, including other projects' paths. Show only dispatches for the current repository (and its worktrees) by default, redact others to a count, and keep an explicit `--all` flag.

## Checks
python3 -m unittest discover -s tests -p 'test_worktree_prune.py'; test_allow_rule.py; test_dispatch_status.py; test_scripts.py.

## Rules
- Base: branch `release-0.13` (candidate 0.13.0). `518da76` is the 0.12-era base the friction work started from; `v0.12.0` is the last release. Background for each item: `docs/plans/2026-11-17-friction-port/plan.md` section "0.14 known issues" and `gate-results.md`.
- This is the **fix round for the release**: fix every item properly. Do not defer, do not revert a feature away, and do not report an item as accepted. If a race cannot be closed completely with portable Python on macOS and Linux, close it as far as the platform allows AND make the operation detect the conflict afterwards and keep the user's data (keep the displaced content as a recoverable copy, report it, exit non-zero). Losing user data silently is never acceptable.
- For each item: first a test that fails now (red), then the fix (green). Never weaken, skip or delete an existing test. If an existing test pins the unsafe behaviour, change it to pin the safe behaviour and say why in the report.
- Old/new compatibility matters: state written by `v0.12.0` and by `518da76` must still load, recover and undo after upgrading.
- Stay in the files named here plus their tests. Under ~400 changed lines if you can; say so if you must exceed it. Keep `python3 tools/context_budget.py` passing (the budget is nearly full: do not grow hook or skill context text).
- Python 3.9 compatible. Do not commit or push. Do not touch `.claude-plugin/plugin.json`, `CHANGELOG.md` or the version.
- Report: per item FIXED (test name) or PARTIAL (what remains and how it is detected and recovered), files changed, checks run with results.
