# fx2: batch-2 review fixes (multi-host)

Risk: normal. Model: Terra medium. Do not commit or push.

Batch-2 review (P04, P05, P08, plus a Sol review through c8c34a4) passed with these leftovers. Fix them in one packet.

## 1. host-probe: a failed Codex `hooks/list` exchange must not count as success

`tools/host-probe`, the `except (...) as exc:` branch after the `hooks/list` request (~line 133), records `SKIP` when the JSON-RPC exchange errors or times out. `tools/ci-local` runs the probe and treats a zero exit as a pass, so a broken exchange passes CI silently.

Change it so that, once the Codex CLI was found and the plugin add succeeded, an RPC error, a malformed reply or a timeout records `FAIL` (detail keeps the current text). `hooks/list` needs no sign-in, so there is no sign-in SKIP case here. Keep the other SKIPs as they are (CLI not on PATH, plugin add failed, prompt output has no skills section, Copilot sign-in).

Add a test in `tests/test_host_probe.py` following its existing fake-codex pattern: a fake app-server that returns a JSON-RPC error for `hooks/list` gives a `FAIL` row and a non-zero exit.

## 2. host-probe `--worktree` copy and symlinked directories (verify first)

Sol flagged `tools/host-probe` ~line 69: the `--worktree` copy checks `src.is_symlink()` only on the file itself. Check whether `git ls-files --cached --others --exclude-standard` can ever list a path whose parent directory is a symlink (it should not: git records a symlinked directory as one symlink entry). If it cannot, make no change and say so in your report with the evidence (a quick experiment in a temp repo). If it can, skip such paths and add a test.

## 3. kaizen-doctor: Codex version check wording

`scripts/kaizen-doctor` ~line 70: `if version in versions:` emits `PASS 'Codex: plugin installed (version X)'`. The Codex plugin cache can hold several versions, and being cached does not prove that version is the active one. Find out whether Codex 0.167.0 records the active plugin version anywhere under `CODEX_HOME` (for example `config.toml`, or a file in `plugins/`; use `codex --help`, `codex plugin --help` and a probe install into a temp `CODEX_HOME` like `tools/host-probe` does). Then:
- If there is a reliable active-version record, check that instead (PASS when it matches the plugin root, WARN with the existing `codex plugin add` fix otherwise).
- If there is not, keep the logic but make the message honest: `Codex: plugin version X is in the cache` and, when other versions are also cached, add `(also cached: ...)`.
Update `tests/test_doctor.py` to match.

## 4. Agent preamble wording

`agents/kaizen-auditor.md` line 10 says "wherever this skill uses `CLAUDE_PLUGIN_ROOT`". It is an agent: change "this skill" to "this agent" there, and the same words in `AGENT_PREAMBLE` in `tests/test_repo.py`. Do not touch any SKILL.md.

## Scope

Only these files: `tools/host-probe`, `tests/test_host_probe.py`, `scripts/kaizen-doctor`, `tests/test_doctor.py`, `agents/kaizen-auditor.md`, `tests/test_repo.py`, and one line added to `docs/plans/2026-11-17-multi-host/changelog/P06.md` if the doctor message changes (under its existing heading). No version bump (P09 does it). Python 3.9, stdlib only.

## Verify

```
PYTHONPATH=tests python3 -m unittest tests.test_host_probe tests.test_doctor tests.test_repo
python3 tools/host-probe --help
```
Sandbox note: process and temp-dir tests may fail inside your sandbox; the dispatcher's checks run outside it and are the authority.
