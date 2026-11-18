# Example: a measured case study

`early-findings-white-paper.pdf` (source: `early-findings-white-paper.md`, charts in `charts/`) is the white paper "Making Multi-Agent AI Coding Cheaper and Faster: early findings", version 0.4, dated 2026-11-17. It is a case study of one developer's setup: Claude Code orchestrating Claude, Codex, Grok and Gemini agents on one game project, audited and changed with the tools in this plugin.

It shows what the loop measured and changed:

- the first clean before/after split (orchestrator context per call 479k to 164k, wake-up context 521k to 170k, wrapper-agent spawns down 86%, main-session images about 28 a day to 0);
- weeks three and four: routing and risk-tagged batch verification (verifier spawns per merge 1.37 to 0.40), orchestrator turns per merge about 40 to about 26, slot waits, cost by agent, the eight ledger rows measured on 2026-11-17, and the plugin releases to 0.11.0, with the lesson from real-input gates and a full local CI;
- what did not work or got worse: an unused rule, a swarm lead that became a new cost, drift back to the most expensive engineer, an unproven batch-review catch rate, and measurement traps.

Read it as a method and a set of leads, not a benchmark. The numbers come from one setup over short, unequal windows, several changes landed together, and dollar figures are API list prices used as a weighting, not bills. Proposals in the paper are recorded as proposals, not results.

The charts are the light versions of the paper's 31 figures, one PNG each.
