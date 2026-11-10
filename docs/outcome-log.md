# Outcome log

Projects append packet outcomes to `out/packets.jsonl` for the audit and calibration report. Each line is one JSON object. The report requires the first four keys; other keys are optional.

A packet is one brief in a plan (see `/agent-kaizen:planning`). Your own landing script or agent writes these rows; the plugin ships no writer.

| Key | Required | Type and default |
| --- | --- | --- |
| ts | yes | ISO UTC timestamp string |
| id | yes | packet ID string |
| model | yes | string |
| effort | yes | string |
| plan | no | string |
| merge_sha | no | string |
| risk | no | string: low, normal, high, or untagged; default untagged |
| fix_origin | no | string or null; default null |
| fixes | no | list of packet ID strings; default [] |
| dispatches | no | number; default 1 |
| dispatch_models | no | list in dispatch order of objects with model and effort strings and rounds integer, one per dispatch |
| rounds | no | number; default 0 |
| status | no | string: DONE, CHECKS FAILING, CODEX FAILED, ENV NOT READY, or none; default unknown |
| slot_wait_s | no | number or null; project-specific timing fields; `packet-report` ignores them |
| playmode_s | no | number or null; project-specific timing fields; `packet-report` ignores them |
| editmode_s | no | number or null; project-specific timing fields; `packet-report` ignores them |
| dotnet_s | no | number or null; project-specific timing fields; `packet-report` ignores them |
| wall_s | no | number or null; default null |
| lines | no | number; default 0 |
| files | no | number |
| area | no | string; default mixed |
| tokens_in | no | number or null |
| tokens_out | no | number or null |
| note | no | string |

The writer reads `Risk:`, `Fix-Origin:`, and `Fixes:` trailers on the merge commit. Risk uses the values above. Fix-Origin may be `batch-review` or `final-audit`, or another project-defined origin. Fixes lists the packet IDs fixed by this landing. A self-reference does not count as a fix.

Write one atomic append per landing. For example, with a prepared `row` dictionary and existing `out` directory:

```python
import json, os; fd = os.open('out/packets.jsonl', os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644); os.write(fd, (json.dumps(row) + '\n').encode()); os.close(fd)
```

A project is enrolled when it has `docs/kaizen/`. The owner may name optional commands in global config under `projectCommands`: `shadowStatus`, `slowTests`, and `speedReport`. Each is an argv list run with the project root as its working directory and prints Markdown or plain lines. Shadow status may write state in the project, such as a STOP flag.

First-pass is the share of rows without a fix origin whose status is DONE, dispatches is 1, and rounds is 0. Fix rate is the share of rows whose ID appears in another row's fixes. Fixes from the whole log count even when dates filter samples. For groups of at least eight, propose UP if first-pass is below 70% or fix rate exceeds 30%. Propose DOWN if first-pass is at least 95% and no row was fixed by a batch-review or final-audit fix. Smaller groups have too few samples. Proposals are never applied automatically.
