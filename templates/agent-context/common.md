# <Project>: context for every agent

<!-- Injected by hooks/subagent-context.sh into custom agents that skip CLAUDE.md. Keep it
to the ~10 rules every agent needs; roles add their own file. -->

- <One-line purpose, and where the design doc is.>
- <The 2–4 architecture red lines an agent must never cross.>
- Code map first: if you were given a brief or plan file, start with `tools/codemap brief <that file>`, then `find|outline|refs`, and read only the line ranges it returns. Read a whole big file only when the task really needs it (the Read guard allows it with an explicit limit).
- Project rules: `CLAUDE.md`. Topic docs: `docs/agents/*.md`; read one only when your task needs it.
- Your brief sets the scope; don't widen it. Agents don't commit, push or open PRs.
- Evidence (screenshots, logs) goes under `out/` (git-ignored).
- Report: files changed, checks run with results, evidence paths, anything unsure.
