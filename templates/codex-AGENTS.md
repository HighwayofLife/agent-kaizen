# Codex global rules

<!-- Template for ~/.codex/AGENTS.md. Codex also reads the repo's AGENTS.md (make it a
symlink to CLAUDE.md, or a one-line pointer), so keep this file to cross-project habits:
under ~20 lines. -->

- Read the repo's AGENTS.md (or CLAUDE.md) first, and the brief you were given. Stay inside the brief's scope.
- Find code with `tools/codemap` when the repo has it, otherwise `rg -n`, `fd` or `ast-grep`. Then read only the line ranges you need (`sed -n 'A,Bp'`). Don't print a whole source or data file over ~200 lines unless the task really needs all of it, and say why in your report.
- Parse JSON and YAML with `jq`/`yq`. Make bulk edits with `ast-grep`/`sed`, then review the diff. Write long output to a file and read it with `tail`/`rg`.
- Web calls (when allowed) send a normal browser User-Agent header.
- Never add a package or dependency yourself: stop and report.
- Don't commit or push unless the brief says so.
- End with a short report: files changed, checks run with their results, anything unsure.
