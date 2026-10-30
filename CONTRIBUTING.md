# Contributing

Thanks for helping. The most useful contributions:
- **Ledger results:** "skill X / change Y saved Z% of W in a setup like ours (stack, agents, vendors)". Open an issue with your before/after audit headlines. Never paste raw transcripts or audit files: they contain paths and prompt fragments.
- **Skills:** new steps for the loop. Keep the pattern:
  - measure first;
  - propose before changing anything;
  - back up config;
  - log every change in the ledger;
  - verify setting names against the current docs;
  - `disable-model-invocation: true`.
- **Ports:** dispatch and review scripts for other agent CLIs, following `scripts/codex-dispatch`.
- **Parser fixes** for token-audit when Claude Code or Codex transcript formats change.

Before a PR:
```
python3 -m unittest discover -s tests
shellcheck -S warning hooks/*.sh
claude plugin validate .
```
Bump `version` in `.claude-plugin/plugin.json` and add a CHANGELOG entry for any user-visible change.
