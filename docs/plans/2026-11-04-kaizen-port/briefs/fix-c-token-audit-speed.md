# fix-c: restore token-audit collection speed (risk normal, Terra high)

Repo: agent-kaizen. Packet 05a (`scripts/token-audit`, `scan_codex`) added the Codex kind/duration table, and its collection is now **1.63× slower** than before 05a. Measured with `tests/bench_token_audit.py` (synthetic, median of 5): pre-05a 0.0216 s, now 0.0352 s. fix-b tried to restore the `MARKERS` prefilter and the shared `rows()` gate, but the ratio did not move. The acceptance bound from brief 05a is at most 1.10×.

Do:
1. Profile `scan_codex` against the bench fixture (`python3 -m cProfile -s cumtime`) and find what the 05a additions cost per line. Likely suspects:
   - `TIMESTAMP.search` and `date_time` running on lines the old path skipped;
   - per-line JSON parsing done twice;
   - building the duration and kind rows eagerly.
2. Fix it while keeping a single pass and identical outputs. Section 7 and 7b must have no diff on the test fixtures; the bench already compares collection results against HEAD.
   - Parse each line at most once.
   - Read timestamps only from the first and last relevant lines of a session, not every line, if that gives the same durations.
3. Add `--max-ratio R` to `tests/bench_token_audit.py`. It exits 1 when the current/pre-05a median ratio exceeds R.
4. Put the before and after numbers in your report.

Verify: `python3 tests/bench_token_audit.py --max-ratio 1.10`, `python3 -m unittest discover -s tests`, `git diff --check`. Do not commit. Do not bump versions.
