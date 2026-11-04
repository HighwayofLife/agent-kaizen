# fix-b: group B batch-review fixes (risk normal, Terra medium)

Repo: agent-kaizen. Reviewed range: 94e65f4..898aa06 (kz-05a, 05b, 06, 07a, fix-a). Main now also holds kz-07b (notes-ledger `due`) and kz-08. Read briefs 07a-notes-ledger-add-set.md and 05a-token-audit-codex-kinds.md for the contracts. Keep code generic. Do not bump versions. Do not commit.

## notes-ledger (`scripts/notes-ledger`)
1. **Line ~89, `csv_exists`.** The duplicate check only accepts `change.startswith(cell)`. After `set --effect` lengthens the cell, a retried identical `add` appends a duplicate. Also accept `cell.startswith(change)`. Test: an `add`, then `set --effect`, then a retried `add` leaves one row.
2. **Lines ~98 and ~119.** Timeline cells flatten newlines and escape `|`, but dedupe and `set` compare against the raw text. Put the normalisation in one function and apply it to both sides. Test: a multiline `--change` containing `|`; a retried `add` leaves one timeline row, and `set` finds it.
3. **Line ~196.** `set --effect` must be idempotent. If the cell already ends with ` Result: <text>`, do not append it again. Test: a retry after a simulated failure between the CSV and timeline writes.
4. **Line ~213.** `--dry-run` must write nothing, including `<csv>.lock`; skip the lock in dry-run. A JSON config that is not a dict must exit 3 with a message, not a traceback.
5. **Missing tests:**
   - `set` keeps every other CSV byte identical.
   - `set` with several matches exits non-zero and reports the ambiguity.
   - No torn lines: every line ends with a newline and has the full column count after concurrent adds.

## kaizen-link (`scripts/kaizen-link` ~l.96)
6. Skip the "no sources under plugin root" check when `--unlink` is set. Stale managed symlinks must still be removable after the plugin is gone. Test: remove every source, then `--unlink` removes the links and leaves regular files alone.

## token-audit (`scripts/token-audit`, 05a)
7. `scan_codex` replaced `rows()` with an inline `session_rows()`. It duplicates the gating logic and runs `TIMESTAMP.search` and `date_time` on every line with no `MARKERS` prefilter. Reuse `rows()` (or factor out the shared gate) so the prefilter applies again, and keep the single pass. Keep 05a's outputs identical: there must be no diff in section 7 or 7b on the test fixtures.
8. Write `tests/bench_token_audit.py`, or a `--bench` helper in tests, that times collection over a synthetic fixture of about 2000 Codex session lines, taking the median of 5 runs, old gate vs new. Report the ratio. Acceptance: within 10% of the pre-05a path; paste the numbers into your report. Do not use real user data.

## kaizen-project-report / config (LOW)
9. `--out` final file mode is 0644 (respect umask), not the 0600 inherited from the temp file. A `projectCommands` value that is not a dict exits 2 with a message, not a traceback. Test both.

## Verify
`python3 -m unittest discover -s tests`, `git diff --check`, `./scripts/rules-lint --repo .`
