# FX2: token-audit usage accounting and extract writing

Risk: high. Model: sol / high.
Sol reason: subtle parsing correctness — friction validation currently changes Claude usage counts versus 518da76.

## Items
1. `scripts/token-audit:462` — friction timestamp validation still gates Claude usage accounting: a valid `.1234Z` timestamp on Python 3.9, or a JSON-escaped fractional digit on 3.9 and 3.13, drops the reported call count from 1 to 0. Usage accounting must never depend on friction validation; counts must equal `518da76` for every input.
2. `scripts/token-audit:176` — the envelope scanner drops valid long timestamps that extend beyond its 100-byte field slice: a reordered 45-character timestamp with legal JSON whitespace drops the call count from 1 to 0.
3. `scripts/token-audit:480` — valid pre-window timestamps longer than 40 characters enter replay reconciliation as malformed: an older replay removes an in-window timing sample and turns its accepted permission into ambiguous evidence, while `518da76` preserves both.
4. `scripts/token-audit:311` — the oversized Codex check accepts balanced delimiters as valid JSON: a 4 MB output with a mismatched payload closer counts as format coverage, whereas `518da76` rejected it.
5. Extract refused under a symlinked path (P28 gate): any symlink component in `--extract-out` or the default `<config>/audits/extracts` makes it print `extract not written ([Errno 20] ...)`, exit 0 and write no extract. On macOS `$TMPDIR` is under `/var` (a symlink to `/private/var`) and many users keep their config dir as a dotfiles symlink; `v0.12.0` wrote the extract. Fix: resolve the configured root once (realpath, must be a directory the current user owns) and apply the no-follow protections only below that resolved root.
6. Exit status after a failed extract write: `token-audit` returns 0. Return a documented non-zero code when the extract was requested or defaulted and could not be written, and update every in-repo caller (`rg -n token-audit scripts hooks skills tools`) so it handles that code sensibly (report the warning; a scheduled run must not abort on it).

## Checks
python3 -m unittest discover -s tests -p 'test_friction_codex.py'; test_friction_signals.py; test_friction_timeline.py; test_token_audit_fixes.py; test_friction_claude.py; python3 tests/bench_token_audit.py --baseline d8a4cb7 --max-ratio 1.10. Run the parser tests under Python 3.9 too if `uv run --python 3.9` is available.

## Rules
- Base: branch `release-0.13` (candidate 0.13.0). `518da76` is the 0.12-era base the friction work started from; `v0.12.0` is the last release. Background for each item: `docs/plans/2026-11-17-friction-port/plan.md` section "0.14 known issues" and `gate-results.md`.
- This is the **fix round for the release**: fix every item properly. Do not defer, do not revert a feature away, and do not report an item as accepted. If a race cannot be closed completely with portable Python on macOS and Linux, close it as far as the platform allows AND make the operation detect the conflict afterwards and keep the user's data (keep the displaced content as a recoverable copy, report it, exit non-zero). Losing user data silently is never acceptable.
- For each item: first a test that fails now (red), then the fix (green). Never weaken, skip or delete an existing test. If an existing test pins the unsafe behaviour, change it to pin the safe behaviour and say why in the report.
- Old/new compatibility matters: state written by `v0.12.0` and by `518da76` must still load, recover and undo after upgrading.
- Stay in the files named here plus their tests. Under ~400 changed lines if you can; say so if you must exceed it. Keep `python3 tools/context_budget.py` passing (the budget is nearly full: do not grow hook or skill context text).
- Python 3.9 compatible. Do not commit or push. Do not touch `.claude-plugin/plugin.json`, `CHANGELOG.md` or the version.
- Report: per item FIXED (test name) or PARTIAL (what remains and how it is detected and recovered), files changed, checks run with results.
