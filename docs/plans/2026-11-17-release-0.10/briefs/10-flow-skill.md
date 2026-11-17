# 10: The `/agent-kaizen:flow` skill and its README row

## Goal and why

The event helper (`packet-event`) and the report (`flow-report`) only help if an orchestrator calls the helper at each state change. Add a skill that teaches the owner how to wire it into their own dispatch, check, review and landing scripts, and how to read the report. The skill must not edit the owner's scripts by itself.

## Context

- agent-kaizen is a Claude Code plugin: skills are Markdown in `skills/<name>/SKILL.md`. Read `AGENTS.md` (Rules): frontmatter `name` equals the folder name, `description` is quoted, `disable-model-invocation: true`, and every skill has a row in the README skills table (`tests/test_repo.py:35-74` check all of that, and that every `${CLAUDE_PLUGIN_ROOT}/...` path in a text file exists).
- Copy the frontmatter and layout (title, one-paragraph purpose, `**Changes:**`, `**Autonomy:**`, `## Task`, `## Done when`) from `skills/planning/SKILL.md:1-20`. Use `${CLAUDE_PLUGIN_ROOT}/docs/autonomy.md` for the Autonomy line wording used by the other skills.
- Already merged: `scripts/packet-event` (packet 01: `packet-event ID STATE [--file PATH] [--ts ISO] [--detail TEXT]`; exit 0 written, 1 write failed, 2 invalid input; states `queued`, `dispatched`, `round-N`, `checks`, `slot-wait`, `review`, `ready`, `landed`, `failed`; default file `out/packet-events.jsonl` (external)), `scripts/flow-report` (packet 05: `flow-report [--events PATH] [--json]`), and `docs/flow.md` (schema, limits, report conventions: wait = `queued` + `slot-wait`, everything else non-terminal is touch). Read `docs/flow.md` before writing; the skill cites it instead of repeating it.
- README skills table: `README.md:195-213` (rows look like ``| `/agent-kaizen:planning` | Plan dirs, standalone briefs, right-sized planners, exploration budget | Multi-step features |``). Add exactly one row for `flow`, after the `planning` row. Other README lines belong to packet 12.
- Test style for a text-contract test: `tests/test_process_rules.py` (reads files, asserts phrases).
- Decisions already made (orchestrator): the skill never edits user scripts without the owner's approval (follow `docs/autonomy.md`); no automatic installation. This packet does not edit CHANGELOG.md.

## Scope / do not touch

Creates: `skills/flow/SKILL.md`, `tests/test_flow_skill.py`.
Edit only: `README.md` (one skills-table row).
Do not touch `scripts/`, `docs/flow.md`, `CHANGELOG.md`, other skills, any other README line.

## Steps

1. Write `skills/flow/SKILL.md`. Task content: where to call `${CLAUDE_PLUGIN_ROOT}/scripts/packet-event` from the owner's scripts, one line each with a shell example: `queued` before the packet waits for a slot, `slot-wait` while waiting for an engine or test slot, `dispatched` at dispatch start, `round-N` per attempt, `checks` when checks run, `review` when review starts, `ready` when approved to land, `landed` or `failed` when finished, always the same unique packet ID, `|| true` so a failed write never breaks the work, and only record states the script actually observed. Explain partial histories (reported as incomplete, never guessed), the local-append limits and line cap (cite `docs/flow.md`), privacy (the log holds IDs and states, no brief text), how to run `flow-report` and read lead time, time per state, queue versus touch, WIP and top waits, and rollback (remove the calls; keep or delete the log). Offer to show the owner a diff of the proposed script edits and wait for approval.
2. Add the README row.
3. Write `tests/test_flow_skill.py`.

## Acceptance criteria

1. Frontmatter is correct (`name: flow`, quoted description, `disable-model-invocation: true`); `tests/test_repo.py` passes, including the README skill-list test and the plugin-root reference test.
2. The skill names every state, `packet-event`, `flow-report`, `docs/flow.md` and `|| true`, tells the reader not to log states that were not observed, covers partial histories, privacy and rollback, and says it does not edit the owner's scripts without approval.
3. `tests/test_flow_skill.py` asserts the frontmatter fields, every state name, the three tool/doc references, the `|| true` guidance, the approval wording and that the README contains `/agent-kaizen:flow`.
4. `scripts/packet-event --help` and `scripts/flow-report --help` still exit 0 (nothing in `scripts/` changed).

## Verification

```sh
python3 -m unittest discover -s tests -p 'test_flow_skill.py' -v
python3 -m unittest discover -s tests -p 'test_repo.py' -v
scripts/packet-event --help
scripts/flow-report --help
```

## Reporting

At most 20 lines: files changed, test results, one proposed CHANGELOG bullet (do not edit CHANGELOG.md). Do not commit or push. Stop and report if `docs/flow.md` or either script is missing.

## Suggested agent / model / effort and risk

`codex-engineer` / Terra medium. Risk: **low** (Markdown skill, one README row, a text test). Estimated size: 120 lines. Batch reviewer regression modules: `test_repo`, `test_flow_skill`.
