# Hand-off prompts for the host acceptance test

Paste one of these into a new session of the host you want to test, with the agent-kaizen clone open as the working folder. Paste the same prompt again in the second session when the agent asks you to. Replace `<path>` with your clone's path. Until `multi-host` is merged, check out that branch first (`git -C <path> checkout multi-host`).

## Codex CLI

```text
Test the Agent Kaizen plugin on this host (Codex CLI). The repo is at <path>; work from its root.
Read docs/testing/host-acceptance.md and follow it exactly, with HOST=codex.
Start with: python3 tools/host-acceptance status --host codex
Don't edit, commit or push anything. When you are done, reply with the RESULT line and the full report.
```

## GitHub Copilot CLI

```text
Test the Agent Kaizen plugin on this host (GitHub Copilot CLI). The repo is at <path>; work from its root.
Read docs/testing/host-acceptance.md and follow it exactly, with HOST=copilot-cli.
Start with: python3 tools/host-acceptance status --host copilot-cli
Don't edit, commit or push anything. When you are done, reply with the RESULT line and the full report.
```

## VS Code with GitHub Copilot (agent mode)

```text
Test the Agent Kaizen plugin on this host (VS Code with GitHub Copilot). The repo is at <path>; work from its root.
Read docs/testing/host-acceptance.md and follow it exactly, with HOST=vscode.
Start with: python3 tools/host-acceptance status --host vscode
Don't edit, commit or push anything. When you are done, reply with the RESULT line and the full report.
```
