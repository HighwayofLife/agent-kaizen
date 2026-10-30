# Coding role

- Tests first (red), implement (green). Never weaken a test to pass it.
- Run the exact verify commands from the brief; paste only the pass/fail lines and the first failure.
- Bulk or mechanical edits: `ast-grep -r` / `sed` / a formatter, then review `git diff`.
- Long logs go to a file; read them with `rg` / `tail`, never whole.
- Never add a dependency yourself: stop and report.
