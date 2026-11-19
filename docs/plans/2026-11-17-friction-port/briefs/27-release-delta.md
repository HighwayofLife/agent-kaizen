# P27 delta (2026-11-18): read with briefs/27-release.md

Do `briefs/27-release.md` in full. Facts settled since it was written:

- 0.12.0 is released and merged (`.claude-plugin/plugin.json` still says 0.12.0). Bump it to 0.13.0, together with every other version field that `tools/ci-local --version-only` checks.
- O1 and O2 are settled; see the plan's "Decisions needed". Document only what the code ships: the narrow allow-rule vocabulary, and the manual Time Machine catalogue action on macOS unless the code proves otherwise.
- Changelog: write `## 0.13.0 (2026-11-18)`. Build it only from the fragments in `docs/plans/2026-11-17-friction-port/changelog/*.md`: merge duplicates and group them as Added / Changed / Fixed, using user-facing wording. Leave out internal test and tooling fragments. End the section with a short "Known issues" line that points to the 0.14 follow-up, without listing file paths.
- Keep public-repo privacy: no absolute home paths, no user names, no private project names.
- P28 (real-input gate) runs after this packet, so do not claim any capability that P28 must still prove. Mark such capabilities as pending verification, or leave them out.
- Do not commit or push.
