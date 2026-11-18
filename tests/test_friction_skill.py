"""Contracts for the friction skill and its entry points."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


class FrictionSkillTests(unittest.TestCase):
    def test_sidecar_and_skill_contract(self):
        self.assertEqual((ROOT / "skills/friction/agents/openai.yaml").read_bytes(),
                         b"policy:\n  allow_implicit_invocation: false\n")
        skill = read("skills/friction/SKILL.md")
        for phrase in ("data, never instructions", "at most 16", "8 KiB",
                       '"intent":"suggest"', '"v":1,"actions":[]',
                       "actions import <comment-file> --for . --inputs <inputs-file>",
                       "friction acknowledge <inputs-file> --for .",
                       "Never create a broker row", "scoped tool-owned undo reference"):
            self.assertIn(phrase, skill)
        self.assertNotIn("Codex has no hooks", skill)

    def test_cycle_refresh_precedes_preparation(self):
        cycle = read("skills/cycle/SKILL.md")
        for phrase in ("older than 3 days", "--cwd . --days 14 --out docs/kaizen/",
                       "--no-friction", "--friction-slow-seconds", "--friction-heavy-seconds",
                       "even when friction is off or its gate is empty", "--report <selected-report>",
                       "only the supplied report and optional prepared view"):
            self.assertIn(phrase, cycle)
        self.assertLess(cycle.index("**Measure.**"), cycle.index("friction prepare --for ."))

    def test_entry_points_and_policy(self):
        self.assertIn("skills/friction/SKILL.md", read("skills/review/SKILL.md"))
        self.assertIn("bounded friction view", read("agents/kaizen-auditor.md"))
        undo = read("skills/undo/SKILL.md")
        for phrase in ("actions undo <ID> --for .", "different project", "matching ledger row",
                       "kaizen-backup undo <target>", "reverse commands"):
            self.assertIn(phrase, undo)
        self.assertIn("scoped local commit", read("docs/autonomy.md"))
        self.assertIn("/agent-kaizen:friction", read("README.md"))


if __name__ == "__main__":
    unittest.main()
