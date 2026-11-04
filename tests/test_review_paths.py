"""Offline checks for path-limited review prompts."""
from tests.test_scripts import StubCase


class ReviewPathsTests(StubCase):
    def setUp(self):
        super().setUp()
        self.env['FINAL'] = 'VERDICT: NO ISSUES'

    def test_default_prompt_is_unchanged(self):
        self.run_script('codex-review', 'diff', '--uncommitted')
        self.assertEqual(self.calls()[-1]['prompt'],
            "Review this repository's diff read-only. Do not edit files. Read AGENTS.md/CLAUDE.md. Hunt for actionable bugs.\n"
            "   - Model/effort/target.\n"
            "   - Findings, most severe first: `file:line — one-line defect — why it matters`. Drop pure style nitpicks.\n"
            "   - `VERDICT: NO ISSUES` | `VERDICT: ISSUES FOUND (n)` | `VERDICT: REVIEW FAILED` (with the error).\n"
            "\nTarget: --uncommitted (review staged, unstaged, and untracked changes)\nFocus: \n"
            "\nKeep the complete response under 22 lines, with the verdict/answer last.\n")

    def test_paths_are_quoted_in_command(self):
        self.run_script('codex-review', 'diff', '--uncommitted', '--paths', 'a', 'b c')
        prompt = self.calls()[-1]['prompt']
        self.assertIn("Paths: review only `git diff HEAD -- a 'b c'`; ignore changes outside these paths.\nPaths:\n- a\n- b c\n", prompt)
