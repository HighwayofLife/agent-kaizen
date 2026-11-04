# Planning role

- Start with `tools/codemap brief <your input file>`, then outline the few files that matter.
- Exploration budget: about 60 tool calls. After that, write the plan and list open items under **Research needed** instead of exploring further.
- Output: `docs/plans/<yyyy-mm-dd>-<slug>/plan.md` with a packet table (id | title | depends on | agent/model/effort | verify | status) and one standalone brief per packet in `briefs/`.
- Each brief: goal and why, files and functions, what's known, acceptance criteria, exact verify commands, scope limits, "don't commit".

- A packet to speed development or cut tokens or cost names a before/after measurement command in its acceptance criteria (a report script, benchmark or `--explain`). Take the baseline before the change; unit tests alone do not show the saving.
- A plan that adds or changes tooling ends with an end-to-end packet that runs the new tools once on real input and pastes trimmed output into its plan row. The plan is not done until that run is clean.
- A packet that changes a contract (flag, trailer, file format or rule wording) adds the old wording to the `rules-lint` stale list and its test fixture in the same packet, and fixes every hit.
