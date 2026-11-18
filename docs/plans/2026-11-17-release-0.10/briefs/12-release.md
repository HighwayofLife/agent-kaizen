# 12: Release 0.10.0 and the end-to-end gate

## Goal and why

Ship the eleven feature packets as one release: one version bump, one changelog entry, the README lines, and a real end-to-end run of the new tools before anything is tagged. The plan is not done until this run is clean.

## Context

- agent-kaizen is a Claude Code plugin. `AGENTS.md` (Rules): any change under `skills/`, `agents/`, `hooks/`, `scripts/`, `templates/` or `.claude-plugin/`, or to `docs/autonomy.md` or `docs/outcome-log.md`, needs a version bump and a changelog entry; `tests/test_repo.py:35` requires `## <plugin version>` in CHANGELOG.md.
- Work happens on the unpublished integration branch `release-0.10`, which holds packets 01 to 11 and was created from `main` after a separate CI change landed (that change adds `tools/ci-local` and a `## Unreleased` heading in CHANGELOG.md with a usage-db fix line). Do not create or edit `tools/ci-local`, `.github/workflows/ci.yml`, `scripts/usage-db` or `docs/examples/` (external).
- Changelog style: see `CHANGELOG.md:5-30` (the 0.9.1 entry): heading `## 0.9.1 (2026-11-10)`, one intro sentence, bullets grouped under backticked script names. The new heading is exactly `## 0.10.0 (2026-11-17)`.
- Changelog bullets proposed by packets 01 to 11 are in `docs/plans/2026-11-17-release-0.10/changelog-bullets.md` (written by the orchestrator). Packets 01 to 11 did not edit CHANGELOG.md.
- Version: `.claude-plugin/plugin.json` has `"version": "0.9.1"`; `.claude-plugin/marketplace.json` has no version field (confirm with `rg -n version .claude-plugin/marketplace.json`).
- README: the `flow` skill row was added by packet 10. Lines this packet edits (README.md, verify line numbers first): the ledger paragraph at :57 (mention the optional `metric command` and `review date` columns); the scripts list in the repo tree at :235-237 (add `packet-event`, `flow-report`, `experiment-check`, `brief-lint`); the docs list in the same tree (add `flow.md`); the environment table at :156-181 (add `KAIZEN_NOTICE_TIMEOUT`: used by the audit notice hook, seconds allowed for the experiment check, default 10; plus `pendingDays` is a config key and belongs in `docs/scheduling.md`, already done by packet 06).
- Test conventions: `python3 -m unittest discover -s tests -p 'test_X.py' -v` for one module; `python3 -m unittest discover -s tests` for all.
- Decisions already made (orchestrator): no commit, tag or push (the orchestrator merges and tags); a failing gate that points at a packet's code is reported, not patched here.

## Scope / do not touch

Creates: nothing tracked. The smoke script and logs go under the git-ignored `out` folder at the repo root.
Edit only: `.claude-plugin/plugin.json`, `CHANGELOG.md`, `README.md` (the lines above), and the `### Results` section of `docs/plans/2026-11-17-release-0.10/plan.md`.
Do not touch anything else.

## Preconditions (check first; stop and report BLOCKED if any fails)

1. `git branch --show-current` is `release-0.10` and `git log --oneline main..HEAD` shows the work of packets 01 to 11.
2. `tools/ci-local` exists and is executable.
3. `docs/plans/2026-11-17-release-0.10/changelog-bullets.md` exists.

## Steps

1. Write the changelog entry: group the proposed bullets by script or feature; fold the `## Unreleased` section into the right group and delete that heading; add plain sentences saying: the due-check nag appears in every enrolled project until its first recorded completion (nothing is recorded today); the ledger gains optional `metric command` and `review date` columns and old ledgers keep working (rows dated before 2026-11-17 are never reported as missing them); machines with a linked bin see `kaizen-link --check` drift for the new scripts until `kaizen-link --apply` is re-run; `pendingDays` (default 10) and `KAIZEN_NOTICE_TIMEOUT` (default 10); completion dates live in `<audits>/projects/<key>/checks.json` per machine. Use only facts from the bullets and the code; no invented numbers.
2. Set `"version": "0.10.0"` in `.claude-plugin/plugin.json`.
3. Edit the README lines named above.
4. Save the smoke script below as `out/release-smoke.sh` (new) and run `bash out/release-smoke.sh 2>&1 | tee out/release-smoke.log`. Every expected status is fixed (checks that pipe into `grep` or `python3` assert on the pipe's last command, so they expect 0); if one differs, do not change the expectation: stop and report which packet's behaviour differs.
5. Run the gates and record each exit status: `tools/ci-local --python 3.9`; `python3 -m unittest discover -s tests`; `shellcheck -S warning hooks/*.sh`; `claude plugin validate .` (if `claude` is not installed, say so).
6. Paste trimmed output (about 40 lines of the smoke log, the last 5 lines of each gate) and every exit status into the `### Results` section of `docs/plans/2026-11-17-release-0.10/plan.md`. Replace temporary absolute paths with `$TMP` and include no private content.

## Smoke script

```sh
set -u
repo=$PWD
tmp=$(mktemp -d)
fail=0
export CLAUDE_CONFIG_DIR="$tmp/cfg"; mkdir -p "$CLAUDE_CONFIG_DIR"
check() {
  name=$1; want=$2; shift 2
  "$@" > "$tmp/out.txt" 2>&1; got=$?
  if [ "$got" -eq "$want" ]; then echo "PASS $name (exit $got)"; else echo "FAIL $name (exit $got, want $want)"; fail=1; fi
  head -15 "$tmp/out.txt"
}

# 1. flow: events to report (p1 finishes, p2 is still open)
ev="$tmp/events.jsonl"
for row in "p1 queued 00:00:00" "p1 slot-wait 01:00:00" "p1 dispatched 02:00:00" "p1 round-1 02:01:00" "p1 checks 03:00:00" "p1 landed 04:00:00" "p2 queued 00:30:00" "p2 dispatched 01:30:00"; do
  set -- $row
  check "packet-event $1 $2" 0 scripts/packet-event --file "$ev" --ts "2026-01-01T$3Z" "$1" "$2"
done
check "flow-report text" 0 scripts/flow-report --events "$ev"
check "flow-report json" 0 sh -c "scripts/flow-report --events '$ev' --json | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d[\"packets\"]==2 and d[\"open_final_states\"]==1 and d[\"max_wip\"]==2, d'"

# 2. experiments: legacy six-column ledger and current eight-column ledger (real header from skills/start)
h6='| date | change | why (which audit finding) | expected effect | measured effect | keep/revert |'
h8='| date | change | why (which audit finding) | expected effect | measured effect | keep/revert | metric command | review date |'
legacy="$tmp/legacy"; cur="$tmp/current"; mkdir -p "$legacy/docs/kaizen" "$cur/docs/kaizen"
printf '%s\n%s\n%s\n' "$h6" '| --- | --- | --- | --- | --- | --- |' '| 2026-10-01 | Old change | audit | less | pending | keep |' > "$legacy/docs/kaizen/LEDGER.md"
{
  printf '%s\n%s\n' "$h8" '| --- | --- | --- | --- | --- | --- | --- | --- |'
  printf '%s\n' '| 2026-10-20 | Overdue test | audit | less | pending | keep | `echo measure` | 2026-11-01 |'
  printf '%s\n' '| 2026-11-01 | Pending test | audit | less | pending | keep | `echo x \| wc -l` | 2026-12-01 |'
  printf '%s\n' '| 2026-10-05 | Measured | audit | less | -20% | keep | `echo m` | 2026-10-12 |'
  printf '%s\n' '| 2026-11-17 | New row no fields | audit | less | pending | keep | | |'
  printf '%s\n' '| 2026-11-16 | Fresh | audit | less | pending | keep | `echo f` | 2026-12-01 |'
} > "$cur/docs/kaizen/LEDGER.md"
check "experiment-check legacy" 1 scripts/experiment-check --project "$legacy" --today 2026-11-17
check "experiment-check legacy json" 0 sh -c "scripts/experiment-check --project '$legacy' --today 2026-11-17 --json | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d[\"legacy_table\"] and d[\"legacy_rows\"]==1 and d[\"counts\"].get(\"missing_metadata\",0)==0, d'"
check "experiment-check current" 1 scripts/experiment-check --project "$cur" --today 2026-11-17
check "experiment-check current json" 0 sh -c "scripts/experiment-check --project '$cur' --today 2026-11-17 --json | python3 -c 'import json,sys; d=json.load(sys.stdin); c=d[\"counts\"]; assert (c[\"past_review\"],c[\"pending_too_long\"],c[\"missing_metadata\"])==(1,2,1), d; assert any(f[\"metric_command\"]==\"echo x | wc -l\" for f in d[\"findings\"]), d'"
printf '{"pendingDays": 20}\n' > "$cur/docs/kaizen/config.json"
check "pendingDays from project config" 0 sh -c "scripts/experiment-check --project '$cur' --today 2026-11-17 --json | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d[\"pending_days\"]==20 and d[\"counts\"][\"pending_too_long\"]==1, d'"

# 3. never-run and recorded checks, recorded from a linked worktree
proj="$tmp/proj"; mkdir -p "$proj/docs/kaizen"; cp "$cur/docs/kaizen/LEDGER.md" "$proj/docs/kaizen/"
git -C "$proj" init -q; git -C "$proj" add -A
git -C "$proj" -c user.name=smoke -c user.email=smoke@example.invalid commit -qm init
git -C "$proj" worktree add -q "$tmp/wt"
state=$(python3 scripts/kaizen-scheduled checks path --for "$proj")
check "checks never run" 0 sh -c "scripts/experiment-check --project '$proj' --checks --state-file '$state' --today 2026-11-17 | grep -q 'never run'"
check "checks record from worktree" 0 python3 scripts/kaizen-scheduled checks record --for "$tmp/wt" models --date 2026-11-10
check "worktree and main share one state file" 0 test "$state" = "$(python3 scripts/kaizen-scheduled checks path --for "$tmp/wt")"
check "second record keeps a backup" 0 sh -c "python3 scripts/kaizen-scheduled checks record --for '$proj' roster --date 2026-11-12 && test -f '$state.bak' && python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert set(d)=={\"models\",\"roster\"}, d' '$state'"
check "models fresh, whats-new still never run" 0 sh -c "scripts/experiment-check --project '$proj' --checks --state-file '$state' --today 2026-11-17 | grep -q 'whats-new: never run'"
printf '{"cwd": "%s"}' "$proj" > "$tmp/hook.json"
check "session-start notice" 0 sh -c "CLAUDE_PLUGIN_ROOT='$repo' AUDIT_DIR='$CLAUDE_CONFIG_DIR/audits' bash hooks/audit-notice.sh < '$tmp/hook.json' | grep -q 'Experiments need attention'"

# 4. packet-report before and after on the fixture
git show "$(git merge-base HEAD main):scripts/packet-report" > "$tmp/packet-report-old"
python3 "$tmp/packet-report-old" --packets tests/fixtures/packets.jsonl --json > "$tmp/pr-old.json"
check "packet-report new" 0 sh -c "scripts/packet-report --packets tests/fixtures/packets.jsonl --json > '$tmp/pr-new.json'"
check "old keys, groups and proposals unchanged" 0 python3 -c "import json; o=json.load(open('$tmp/pr-old.json')); n=json.load(open('$tmp/pr-new.json')); assert set(o)<=set(n) and o['groups']==n['groups'] and o['proposals']==n['proposals']; print('added keys:', sorted(set(n)-set(o)))"

# 5. codex-dispatch --brief-lint with a stub runner (the stub is the test suite's fake Codex)
mkdir -p "$tmp/bin" "$tmp/drepo"
python3 - "$tmp/bin/codex" <<'PY'
import pathlib, sys
sys.path.insert(0, "tests")
import test_scripts
target = pathlib.Path(sys.argv[1]); target.write_text(test_scripts.FAKE_CODEX); target.chmod(0o755)
PY
python3 - "$tmp" <<'PY'
import pathlib, sys
tmp = pathlib.Path(sys.argv[1]); fence = chr(96) * 3
good = f"# 01: smoke\n\n## Goal and why\nSmoke test.\n\n## Scope\nEdit only `tracked`.\n\n## Acceptance criteria\n1. It runs.\n\n## Verify\n{fence}sh\ntest -f tracked\n{fence}\n"
(tmp / "good.md").write_text(good)
(tmp / "bad.md").write_text("# 02: bad\n\nNo sections here.\n")
PY
echo hi > "$tmp/drepo/tracked"; git -C "$tmp/drepo" init -q; git -C "$tmp/drepo" add -A
git -C "$tmp/drepo" -c user.name=smoke -c user.email=smoke@example.invalid commit -qm init
export RECORD="$tmp/calls.jsonl"; PATH="$tmp/bin:$PATH"
check "dispatch good brief" 0 scripts/codex-dispatch --brief-lint -C "$tmp/drepo" -r 0 --allow-no-change "$tmp/good.md"
calls=$(wc -l < "$RECORD")
check "dispatch bad brief refused" 2 scripts/codex-dispatch --brief-lint -C "$tmp/drepo" -r 0 --allow-no-change "$tmp/bad.md"
check "stub not called for the bad brief" 0 test "$calls" = "$(wc -l < "$RECORD")"

# 6. brief lint on the shipped template and a real plan brief
check "brief-lint template" 0 scripts/brief-lint --repo . templates/plan/briefs/01-example.md
check "brief-lint real brief" 0 scripts/brief-lint --repo . docs/plans/2026-11-17-release-0.10/briefs/10-flow-skill.md

# 7. copied install finds every new script and the scheduler finds its sibling
export CLAUDE_CONFIG_DIR="$tmp/cfg2"; mkdir -p "$CLAUDE_CONFIG_DIR"
check "kaizen-link copy apply" 0 python3 scripts/kaizen-link --plugin-root "$repo" --mode copy --apply
for s in packet-event flow-report experiment-check brief-lint; do
  check "installed $s --help" 0 "$CLAUDE_CONFIG_DIR/bin/$s" --help
done
check "installed scheduler finds experiment-check" 0 python3 -c "import runpy,sys; ns=runpy.run_path(sys.argv[1]); print(ns['sibling'](None,'experiment-check'))" "$CLAUDE_CONFIG_DIR/bin/kaizen-scheduled"

echo "smoke failures: $fail"; exit $fail
```

## Acceptance criteria

1. Preconditions pass, or the packet stops with BLOCKED and nothing is edited.
2. `CHANGELOG.md` has `## 0.10.0 (2026-11-17)` as the first entry, no `## Unreleased` heading remains, and every packet's bullet and every point in step 1 is present; `plugin.json` says 0.10.0; `rg -n "0\.9\.1" .claude-plugin` finds nothing.
3. README lines are edited as listed and `tests/test_repo.py` passes (README skill test, version and changelog test, privacy test).
4. The smoke script ends with `smoke failures: 0`; every `check` shows PASS.
5. `tools/ci-local --python 3.9`, `python3 -m unittest discover -s tests`, `shellcheck -S warning hooks/*.sh` and (when available) `claude plugin validate .` exit 0.
6. The Results section holds the trimmed smoke log and every gate's exit status, with no private paths.

## Verification

```sh
python3 -m unittest discover -s tests -p 'test_repo.py' -v
bash out/release-smoke.sh 2>&1 | tee out/release-smoke.log
tools/ci-local --python 3.9; echo "ci-local exit $?"
python3 -m unittest discover -s tests; echo "unittest exit $?"
shellcheck -S warning hooks/*.sh; echo "shellcheck exit $?"
claude plugin validate .; echo "validate exit $?"
```

## Reporting

At most 25 lines: every gate's exit status, the smoke result, files changed, anything that blocked or differed from the plan. Do not commit, tag or push.

## Suggested agent / model / effort and risk

`codex-engineer` / Terra medium. Risk: **normal**. Estimated size: 150 lines changed. The orchestrator merges the branch and tags after this packet and a final audit.
