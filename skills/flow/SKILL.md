---
name: flow
description: "Wire packet flow events into an orchestrator and read the report."
disable-model-invocation: true
argument-hint: "[propose|safe|auto|yolo]"
---

# Packet flow instrumentation

**Plugin root:** `${CLAUDE_PLUGIN_ROOT}`. If that is still a `${...}` placeholder, use the folder that contains `skills/` (this file is `skills/<name>/SKILL.md`), and substitute that path, in quotes, wherever this skill uses `CLAUDE_PLUGIN_ROOT`.
**Not in Claude Code?** Read `docs/hosts.md` in the plugin root first. Skip steps that only work in Claude Code, and follow its propose-only rule before changing any host configuration.

Show the owner where to record packet state changes in their dispatch, check, review and landing scripts, and how to read the resulting flow report.

**Changes:** proposed calls in the owner's scripts, only after the owner approves.

**Autonomy:** follow `${CLAUDE_PLUGIN_ROOT}/docs/autonomy.md`. Do not edit the owner's scripts without approval, regardless of mode.

## Task

Read `${CLAUDE_PLUGIN_ROOT}/docs/flow.md` for the schema, local-append limits, 4096-byte line cap and report conventions. Use the same unique packet ID for every event for a packet. Record only states the script actually observed; do not log states that were not observed. Add `|| true` to every call so a failed write never breaks the work. For example, with `packet_id` set by the orchestrator:

- Before the packet waits for a slot: `"${CLAUDE_PLUGIN_ROOT}/scripts/packet-event" "$packet_id" queued || true`
- While waiting for an engine or test slot: `"${CLAUDE_PLUGIN_ROOT}/scripts/packet-event" "$packet_id" slot-wait || true`
- At dispatch start: `"${CLAUDE_PLUGIN_ROOT}/scripts/packet-event" "$packet_id" dispatched || true`
- For each attempt, using its positive attempt number: `"${CLAUDE_PLUGIN_ROOT}/scripts/packet-event" "$packet_id" "round-${round}" || true` (`round-N`)
- When checks run: `"${CLAUDE_PLUGIN_ROOT}/scripts/packet-event" "$packet_id" checks || true`
- When review starts: `"${CLAUDE_PLUGIN_ROOT}/scripts/packet-event" "$packet_id" review || true`
- When approved to land: `"${CLAUDE_PLUGIN_ROOT}/scripts/packet-event" "$packet_id" ready || true`
- When finished successfully: `"${CLAUDE_PLUGIN_ROOT}/scripts/packet-event" "$packet_id" landed || true`
- When finished unsuccessfully: `"${CLAUDE_PLUGIN_ROOT}/scripts/packet-event" "$packet_id" failed || true`

Keep the log private: record IDs and states, no brief text. Partial histories are reported as incomplete; missing events are never guessed. The default log is `out/packet-events.jsonl`. Local appends have filesystem limits and no network-filesystem locking promise; see the flow document before choosing a log location.

Run `"${CLAUDE_PLUGIN_ROOT}/scripts/flow-report"` for the default log, or add `--events PATH` for another log and `--json` for JSON. Read lead time from first event to terminal state, time per state, queue versus touch time, WIP and top waits using the definitions in the flow document. Incomplete packets have no lead time.

Offer to show the owner a diff of the proposed script edits and wait for approval before editing. Do not install anything automatically. To roll back, remove the calls and either keep or delete the log.

## Done when

The owner has a proposed diff and knows how to run and interpret the report, including its limits and rollback. Apply script edits only after the owner approves.
