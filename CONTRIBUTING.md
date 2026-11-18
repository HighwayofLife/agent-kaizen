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
tools/host-probe --host codex           # install check in an isolated home; prints SKIP when codex is missing
```
Bump `version` in `.claude-plugin/plugin.json` and add a CHANGELOG entry for any user-visible change, and for any change under `skills/` (including `skills/*/agents/openai.yaml`), `agents/`, `hooks/`, `scripts/`, `templates/` or `.claude-plugin/`, or to `docs/autonomy.md`, `docs/hosts.md` or `docs/outcome-log.md` (skills read them at runtime).


## Release

Bump `version` in `.claude-plugin/plugin.json` and add a matching CHANGELOG entry. Run `tools/ci-local --python 3.9`, then commit the changes and run:

```sh
git tag vX.Y.Z && git push origin main vX.Y.Z
```

CI tests the tag and publishes the release. CI runs on PRs to `main` and on `v*` tags; it does not run on pushes to main. To run it by hand, use `gh workflow run CI`.
