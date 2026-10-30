# Planning role

- Start with `tools/codemap brief <your input file>`, then outline the few files that matter.
- Exploration budget: about 60 tool calls. After that, write the plan and list open items under **Research needed** instead of exploring further.
- Output: `docs/plans/<yyyy-mm-dd>-<slug>/plan.md` with a packet table (id | title | depends on | agent/model/effort | verify | status) and one standalone brief per packet in `briefs/`.
- Each brief: goal and why, files and functions, what's known, acceptance criteria, exact verify commands, scope limits, "don't commit".
