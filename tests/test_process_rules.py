"""Keep the planning and self-improvement rules in their guidance."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class ProcessRulesTest(unittest.TestCase):
    def test_kaizen_rule(self):
        for name in ("skills/cycle/SKILL.md", "templates/global-CLAUDE.md"):
            with self.subTest(path=name):
                text = (ROOT / name).read_text()
                for phrase in ("every new self-improvement tool or process", "plugin schedule",
                               "notes ledger", "re-measure later"):
                    self.assertIn(phrase, text)

    def test_planning_rules(self):
        for name in ("skills/planning/SKILL.md", "templates/agents/planner.md",
                     "templates/agent-context/planning.md"):
            with self.subTest(path=name):
                text = (ROOT / name).read_text()
                for phrase in ("before/after measurement command", "baseline before the change",
                               "unit tests alone do not show the saving", "end-to-end packet",
                               "real input", "trimmed output", "until that run is clean",
                               "old wording", "`rules-lint` stale list", "test fixture",
                               "fixes every hit"):
                    self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
