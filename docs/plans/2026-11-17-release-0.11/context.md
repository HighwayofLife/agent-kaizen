# Context map (verified at 28b89c6)

## Rules and verification
- `AGENTS.md:8` names the suite, shellcheck and plugin validation; Rules require Python 3.9 stdlib, skill frontmatter and README row, privacy, version/changelog, and scan timing. `.github/workflows/ci.yml:46` checks script `--help`; no CI edits.
- `tools/ci-local:14-22` accepts `--python`, `--skip-tests`, `--version-only`; :48-62 uses `uv` for a named Python. Baselines were not run: planning brief prohibits builds/tests and network. No `tools/codemap` exists. Locate with `rg -n` and `sed`.
- Narrow tests: `python3 -m unittest discover -s tests -p 'test_NAME.py' -v`; shellcheck `shellcheck -S warning hooks/*.sh`; `claude plugin validate .`. Scan performance: `python3 tests/bench_token_audit.py --baseline 28b89c6` (synthetic fixture).

## Code and patterns
- `scripts/token-audit:71` filters records before decoding; :445 scans Claude; :721 collects; :786 headline JSON; :1049 report sections; :1176 report; :1336 CLI. At :1404-1410 it always writes report and extract even with `--json`. `--project-dir`, `--days` and `CLAUDE_CONFIG_DIR` select fixtures; Codex discovery is separate.
- `scripts/usage-db:34-45` stores source, call ID, time, session, agent and token columns; no spawn ID. :146-175 finds transcripts and agent labels; :177 parses calls; :281 ingests all changed files; :477 reports; :573-615 defines CLI. No session-specific ingest exists. Gaps for subagent types are ambiguous when spawns overlap.
- `tests/test_usage.py:17-65` and `tests/test_usage_db.py:43` use temporary fixtures; `tests/bench_token_audit.py:56-89` compares synthetic collect times. `tests/test_hooks.py:43` runs shell hooks; :421 tests timeout/atomic notice.
- `scripts/kaizen-scheduled:308` run lock; :1489 checks; :1532 audit steps; :1548 existing DB ingest; :1570 `_run_audit`; :1576 `_run_token_audit`; :2227 lock dispatch. Reuse existing lock and subprocess timeouts; do not acquire the same lock twice.
- `hooks/hooks.json:3` registers startup notice; `hooks/audit-notice.sh:1-40,93-97,134` gates notices, bounds checker and emits JSON. `hooks/limit-big-read.sh:27` emits exit-0 PreToolUse deny. `skills/guardrails/SKILL.md:12,44-50` installs guards only with approval and copies bundled hooks.
- `scripts/install-schedule:50-56` `MANAGED_NAMES`; `scripts/kaizen-link:28-39` `SCRIPTS`; installed helpers must be registered in both. `README.md:196` correctly says disabled skill descriptions do not cost per-turn context (tested on Claude Code 2.1.327); the agent description remains visible. `scripts/pricing.json:2-5` contains source check date. `.claude-plugin/plugin.json:3` is 0.10.0.

## Discrepancies and contracts
- The proposed scan cannot just call current `--json`: it writes files. Packet 04a adds `--no-write` and verifies no writes including extracts. Demo generator lives under scripts so installed copies can use it; tests invoke the same generator.
- No DB call row tracks a spawn identity; main-session gap metrics are reliable, subagent interleaving is labelled approximate and never treated as per-spawn truth. Full rewrite is an explicit heuristic, not a known cache event.
- Unknown records may be discarded by fast byte gates. Canary must inspect all eligible records without losing speed or count known metadata as drift; missing CLI versions use `unknown`.
- This is an unpublished integration branch: feature packets propose changelog bullets; the integrator bumps version and adds an entry at each sequential landing to satisfy AGENTS.md, then packet 10 sets the release version. Every skill packet adds its README table row immediately. Research fixture contains sanitized synthetic input, never a captured transcript.

- Revision: `tests/test_kaizen_link.py:121` requires each new script in `SCRIPTS`; each script packet also updates `MANAGED_NAMES`. `tests/test_hooks.py:163,175` checks hook command names and template paths/timeouts. `.github/workflows/ci.yml:54` runs the budget stage with `--skip-tests`. Global auto-audit state belongs at `<audits>/auto-audit-state.json`; per-project `state.json` at `scripts/kaizen-scheduled:700` is not global.
- Guardrails discrepancy: repository guard hooks use environment settings and the guardrails skill; no `guardrails` section currently exists in the global config. Packet 05 defines the section there instead of assuming it exists.
