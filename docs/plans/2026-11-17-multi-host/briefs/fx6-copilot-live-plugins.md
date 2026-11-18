# FX6: detect Copilot "live" plugins loaded from a local marketplace directory

Agent: Terra, effort medium. Risk: normal. Do not commit or push.

## What we found

GitHub Copilot CLI 1.0.114 does not copy a plugin from a local directory marketplace into `~/.copilot/installed-plugins/`. It lists it as a "Live Plugin (loaded from a local marketplace directory, never copied)". The only on-disk record is `$COPILOT_HOME/settings.json` (default `~/.copilot/settings.json`):

```json
{
  "enabledPlugins": {"agent-kaizen@agent-kaizen-tools": true},
  "extraKnownMarketplaces": {
    "agent-kaizen-tools": {"source": {"source": "directory", "path": "/abs/path/to/marketplace"}}
  }
}
```

The plugin root is the marketplace dir joined with the plugin entry's `source` in that dir's `.claude-plugin/marketplace.json` (`plugins[]` entry whose `name` is `agent-kaizen`; for this repo `"./"`, so the root is the marketplace dir itself). The root holds `.claude-plugin/plugin.json` with `"name": "agent-kaizen"`.

A live session confirmed hooks fire from that root (`COPILOT_PLUGIN_ROOT` set, copilot sessionStart/userPromptSubmit trace lines). But two tools only look in `installed-plugins/`:

- `tools/host-acceptance` (around line 167, the `base = ...` for copilot/vscode): `check` fails `installed`, `files`, `scripts`, `hooks-offline`.
- `scripts/kaizen-doctor` (around lines 64-90): prints no Copilot line at all.

## Changes

1. One small resolver in each file (they are separate programs; keep them standalone, stdlib only): given the Copilot home, return the plugin root or None.
   - First `installed-plugins/agent-kaizen-tools/agent-kaizen` if it is a dir (unchanged behaviour wins).
   - Else read `settings.json` (missing or bad JSON means None, never a crash). Require `enabledPlugins["agent-kaizen@agent-kaizen-tools"]` to be true and `extraKnownMarketplaces["agent-kaizen-tools"].source.source == "directory"`. Take `source.path` (expand `~`), read its `.claude-plugin/marketplace.json`, find the `agent-kaizen` entry, join its `source` (string; default `./`), and accept the result only if `.claude-plugin/plugin.json` there has `"name": "agent-kaizen"`.
   - Return also a kind (`installed` or `live`) so output can say which.
2. `tools/host-acceptance check --host copilot-cli|vscode`: use the resolver for the Copilot location. The `installed` detail says `live plugin from <redacted path>` for the live kind. Keep FX5's VS Code agentPlugins fallback and its precedence rule (a `~/.copilot` install, installed or live, wins over agentPlugins). `files`/`scripts`/`hooks-offline` must pass for a live root, which is a whole repo export (extra dirs like `tests/`, `tools/` are fine).
   - Version check: compare the live root's `plugin.json` version with the repo's, as for installed copies.
3. `scripts/kaizen-doctor`: use the resolver; for a live plugin emit the same PASS/WARN rows as for an installed one, with the detail noting it is live (e.g. `Copilot: plugin installed (live from local marketplace)`). Disabled in `enabledPlugins` means not installed.
4. Tests:
   - `tests/test_host_acceptance.py`: a temp COPILOT_HOME with only `settings.json` pointing at a temp marketplace dir is found by `check`; disabled plugin is not found; `installed-plugins` wins over live.
   - The kaizen-doctor tests (find them with `rg -l kaizen-doctor tests`): the live case gives the PASS Copilot row; bad JSON in settings.json gives no crash and no Copilot PASS.
   - Tests use temp dirs and env (`COPILOT_HOME`, `HOME`) only; never read or write the real `~/.copilot`.
5. CHANGELOG: `scripts/kaizen-doctor` changes, so add one bullet to the existing unreleased `## 0.12.0` entry (no version bump). Add one short line to `docs/hosts.md` in the Copilot section saying a local-directory install is "live" (loaded in place, not copied), and the matching note in `docs/testing/host-acceptance.md` troubleshooting if there is a natural place.

## Scope

Allowed files: `tools/host-acceptance`, `scripts/kaizen-doctor`, `tests/test_host_acceptance.py`, the kaizen-doctor test file, `CHANGELOG.md`, `docs/hosts.md`, `docs/testing/host-acceptance.md`. Do not touch hooks, skills, manifests. No home-directory paths in tracked files.

## Verify

```
PYTHONPATH=tests python3 -m unittest tests.test_host_acceptance tests.test_repo tests.test_host_probe
python3 -m unittest discover -s tests -p 'test_*doctor*'
python3 tools/host-acceptance --help && python3 scripts/kaizen-doctor --help
```
