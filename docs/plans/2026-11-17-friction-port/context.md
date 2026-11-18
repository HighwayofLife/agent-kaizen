# Friction port code map

Line numbers below are from 0.11.0 main `d8a4cb7`. The 0.12.0 integration branch is local `multi-host` at `18ababd`, separate from main. Only its landed P01/P02/P03/P06 contracts are executable at that tip; read the branch plan for pending P04/P05/P07/P08/P09 and verify against the merged base. Re-anchor with `rg -n` after merging 0.12.0; no `tools/codemap` exists on the planning base. Read narrow ranges. The archived source branches are read-only reference material.

| Entry point | Current source range and pattern |
|---|---|
| Claude row admit/canary | `scripts/token-audit:83–245`, bounded timestamp and type filters, version counters before decode |
| Claude tools/scrubbing | `scripts/token-audit:422–493,564–736`, error redaction, duplicate and tool-pair IDs |
| Codex single pass | `scripts/token-audit:748–859`, raw cwd matching, bounded first row, usage deltas |
| Audit output | `scripts/token-audit:860–963,1279–1313,1327–1493,1501–1586`, source aggregation, previous-scope selection, atomic extract v1, default paths |
| Runner settings | `scripts/kaizen-scheduled:62–149,170–299,2086–2171`, schema, strict reads, and config locks; paths helper at 46–60 must match peers |
| Runner project state | `scripts/kaizen-scheduled:573–746,2124–2136`, enrollment, canonical worktrees, index and atomic project state |
| Runner audit and gate | `scripts/kaizen-scheduled:803–914,923–962,1419–1469,1585–1649`, activity gating, scoped audit argv, project report and usage DB chain |
| Runner permission boundary | `scripts/kaizen-scheduled:139–156,965–1057,1187–1220`, empty general Bash allows, absolute path hints, deny lists, approved backup/ledger verbs |
| Runner retention | `scripts/kaizen-scheduled:1231–1412`, existing `host-probe-*.json` and `friction-inputs-*.json` patterns, age/cap and file identity. No sample kind yet |
| Runner timeout and recovery | `scripts/kaizen-scheduled:312–508,1650–1876,1877–2085`, lock, process groups, active run, ledger guard, rollback and successful proposal |
| Git facts | `scripts/dispatch-status:11–58,60–102`, NUL worktrees with fallback and dirty dispatch reporting excluding `out` |
| Backups | `scripts/kaizen-backup:49–84,110–210,217–247,289–390`, manifest validation, hash preflight, credential guards, backup actions and dispatch |
| Installer | `scripts/install-schedule:50–57,419–441` uses MANAGED_NAMES and source aliases. `scripts/kaizen-link:26–51,183–213` skips unshipped sources; `tests/test_kaizen_link.py:138–142` requires all existing scripts. Runner sibling resolver `scripts/kaizen-scheduled:921–951`. |
| Hook wiring | `hooks/hooks.json:3–50`, startup, prompt and Bash completion/failure; `hooks/bash-burst.sh:8–45`, synchronous nudge and per-turn state |
| Session notice and budget | `hooks/audit-notice.sh:8–45,128–176`, project and atomic notice markers; `tools/context_budget.py:70–111`, hashes and reviewed literal inventory from `tools/context-budget.json` |
| Current security and instructions | `docs/autonomy.md:40–100`, `skills/cycle/SKILL.md:10–42`, `skills/review/SKILL.md:15–52`, `skills/undo/SKILL.md:14–25`, `agents/kaizen-auditor.md` |
| Repo and config pins | `tests/test_repo.py:29–80`; `tests/test_runner.py:46–105,195–233,319–390,1093–1245`; `tests/test_config_keys.py` for subset checks |
| CI and release | `tools/ci-local:15–86`, `.github/workflows/ci.yml:43–63`, `.claude-plugin/plugin.json:3`, `CHANGELOG.md:5`; skill list `README.md:200–232` |
| Existing scan bench | `tests/bench_token_audit.py:55–95`, imports a baseline using `git show` and pins legacy summaries |

## Invariants to copy

- Follow the existing private scoped project storage and versioned output conventions. Reject bad and outdated records, de-duplicate on stable identity and bound all transcript/probe parsing. Prefer one pass and deterministic read before the model gets any friction input.
- Keep legacy review deny lists, backup/ledger lifecycles, pre-existing hooks and host adapters. Preserve skill preambles, Codex implicit-invocation sidecars, README registration, same-scope comparisons, and installation through managed names and overrides.
- Sample appends and action store writes need cross-process synchronization. A path extracted from a state file is data. Re-derive project, action type and targets at use. Ordinary Git status and recorded file/ref identity do not authorize hidden-data removal.
- The archived p13 prefix grant and p08b grants are deliberately replaced. The older Markdown-home autonomy decision is narrower under newer config hard stops. Keep the newer guards.

## Check commands and status

- Each implementation brief lists its file-specific unittest discovery and validators. Full per-packet check is `tools/ci-local --python 3.9`.
- Hooks run `shellcheck -S warning hooks/*.sh` and `python3 tools/context_budget.py --root .`; plugin changes run `claude plugin validate .`.
- For scan packets save `FRICTION_BASE=$(git rev-parse HEAD)` before edits and run `python3 tests/bench_token_audit.py --baseline "$FRICTION_BASE" --max-ratio 1.10`. Recheck against the post-0.12.0 integration baseline in P28.
- Planning checked local paths, source ranges, revision names and packet consistency. Builds, validators, benchmarks, host clients and tests were left to implementation and release, per the offline planning brief. No measured baseline is asserted here.

## Discrepancies and references

- Read `git show multi-host:docs/plans/2026-11-17-multi-host/plan.md` at 76, 105, 110, 122, 166 and 170 for the unchanged 0.12.0 manifest, four baseline Codex registrations and 823/1024 context bytes. `git show multi-host:hooks/hooks.json` has the existing PostToolUse/Failure Bash registrations. `git show multi-host:tools/host-probe` at 17–19,121–131 and `git show multi-host:tests/test_host_probe.py` at 41–42,133–136 are the executable discovery contract. P14c owns both probe paths and their verification. P06/P10 use the separate runtime probe suite.
- `git show multi-host:docs/plans/2026-11-17-multi-host/briefs/04-skill-preamble.md` at 19–31,51–54 pins P04 text and placement pending integration. `git show multi-host:tests/test_repo.py` at 52–58 and `git show multi-host:skills/audit/agents/openai.yaml` pin the exact P02 bytes already landed. P26 uses both contracts.
- `scripts/kaizen-backup:157–201` ordinary begin and finish already record run/session, created time and after hashes, but no Git stamp. `scripts/kaizen-scheduled:1930–2008` generates IDs, grants scoped editing independently of backups, and has guard/rollback before the success branch. P08/P16/P25 bind the helper to the runner snapshot. P24a cannot infer a zero write count from an empty manifest list.
- `docs/autonomy.md:23–27,67–81` supplies the default shared change count and ledger obligation. `skills/start/SKILL.md:25–28` fixes the Markdown row schema. `skills/undo/SKILL.md:16–26` dispatches existing backup undo, and P24b/P26 add the explicit action-ID route. `skills/cycle/SKILL.md:21–23` refreshes normal interactive reports independently of friction.
- p06's store lives in `wt/p06:scripts/kaizen-scheduled`, not in an archived standalone executable. p08b's installer predates `kaizen-link`. p10's tip omits p04/p07 and includes only partial final skill text. Use feature tips and review fixes rather than the stacked p10 branch as a base.
- Archives inspected using `git diff 599810c wt/<branch> --stat` and selective `git show wt/<branch>:<path>`. The source plan's retained owner decisions and review fixes are in `out/plans/2026-10-30-friction-audit/`. They inform the new briefs without being required reading for implementers.
