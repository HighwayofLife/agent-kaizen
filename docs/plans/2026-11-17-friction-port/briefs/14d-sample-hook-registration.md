# P14d Register the bounded sampler hook (gated on S1 and S5)

## Goal

Finish P14c's registration half. P14c landed the sampler fixes and samples retention but left the sampler unregistered because the live S1/S5 checks had not run. This packet adds `hooks/friction-sample.sh`, the async registration in `hooks/hooks.json`, the `tools/context-budget.json` entry, the host-probe pin (four or five Codex events) and the opt-in on/off benchmark, only after S1 and S5 are answered in plan.md.

- **Agent / model / effort** — codex-dispatch, terra, high.
- **Risk** — normal.
- **Dependencies** — P14c landed; S1 answered; S5 answered (its Copilot part needs 0.12.0 O1, owner sign-in). Until then this packet does not start.
- Changelog: added: friction sampler hook runs silently after successful Bash calls.

Retention (P14c item 3) and the P14b review fixes are already landed; do not redo them. The section below is P14c's original acceptance text for reference.

## Implementation and acceptance

1. Add the silent async command under the existing Bash PostToolUse matcher after live S1/S5 verification on a disposable install. Existing sync nudges and event output remain intact. Scope sampling to successful PostToolUse only. Timeout/failure signals remain transcript-derived; keep PostToolUseFailure unchanged. Update only the new context-budget entry with zero literal bytes and `shasum -a 256 hooks/friction-sample.sh`.
2. By `git show multi-host:tools/host-probe` and `git show multi-host:tests/test_host_probe.py`, the four baseline Codex events are exact. Keep those required. Pin the extra sampler registration if observed (five total, two PostToolUse) or the verified omission (four total). Identify its command where exposed, reject unexpected extras/missing baseline, and test that Codex/Copilot execute no sampling. This change and its narrow host-probe test are required for the 0.12.0 `ci-local` host-probe stage. If the shared manifest breaks a supported host, keep the registration dark.
3. Add `samples` retention of 14 UTC days / 50 MiB through the existing retention planner. Protect the live UTC day and lock file, re-check identity and concurrent writers at apply. Check `retentionOverrides` via `tests/test_runner.py`. Run 50 warmed on/off measurements via the opt-in benchmark and report p50/p95 and installed Claude tool-return delta (<=10 ms added median). Compare to the same synchronous 0.12.0 nudge path. No synchronous process query.


## Verification

- `python3 -m unittest discover -s tests -p 'test_friction_sampler.py'`
- `python3 -m unittest discover -s tests -p 'test_housekeep.py'`
- `python3 -m unittest discover -s tests -p 'test_runner.py'`
- `python3 -m unittest discover -s tests -p 'test_host_probe.py'`
- `python3 -m unittest discover -s tests -p 'test_hooks.py'`
- `python3 -m unittest discover -s tests -p 'test_hook_schedule.py'`
- `python3 -m unittest discover -s tests -p 'test_doctor.py'`
- `shellcheck -S warning hooks/friction-sample.sh hooks/bash-burst.sh`
- `python3 -m json.tool hooks/hooks.json >/dev/null`
- `python3 tools/context_budget.py --root .`
- `python3 tests/test_friction_sampler.py --bench`
- `tools/host-probe --host codex --worktree`
- `tools/ci-local --python 3.9`


## Report

Report changed files and line counts, exact checks and outcomes, known uncertainty and any blocked verification. Label measurements with baseline/conditions. Redact paths and identifiers from shared output. Leave plugin version and release CHANGELOG to P27. Do not commit or push.

## Delta: P14b security review findings (2026-11-18), fix all three before registering the sampler

The sampler becomes live when this packet registers it, so fix these in `scripts/kaizen_friction_sample.py` first (red tests in `tests/test_friction_sampler.py`, do not delete or weaken existing tests):

1. Teardown (~line 321) ignores whether `waitpid` actually reaped the killed query. If the child has not exited by the deadline it is orphaned when the sampler exits. Fix: after SIGKILL, reap with a bounded wait inside the remaining budget; if still unreaped, make sure the child cannot outlive the sampler unobserved (for example its own process group killed as a group, or a detached reaper), and record the sample as unusable. Test: a child that ignores the first signal is still gone after the sampler returns.
2. The five-minute rate claim (~line 239) is taken even when the timing row fills the daily file or less than the required query budget remains, so later eligible hooks lose the slot without a sample. Fix: check the daily cap and remaining budget before claiming, or release/refund the claim when no process sample was taken. Test both cases.
3. The persisted monotonic timestamp (~line 207) has no boot identity, so after a reboot a claim can be rejected long after the interval elapsed. Fix: store a boot identity with the stamp (for example the boot time from `sysctl kern.boottime` on macOS / `/proc/sys/kernel/random/boot_id` on Linux, bounded and fail-open to "new boot") and treat a different boot as an elapsed interval. Test with an injected boot identity.
