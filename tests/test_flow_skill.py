"""Keep the flow skill's event and approval guidance in place."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class FlowSkillTest(unittest.TestCase):
    def test_frontmatter(self):
        text = (ROOT / "skills/flow/SKILL.md").read_text()
        frontmatter = text.split("---", 2)[1]
        self.assertIn("name: flow\n", frontmatter)
        self.assertRegex(frontmatter, r'(?m)^description: "[^"\n]+"$')
        self.assertIn("disable-model-invocation: true\n", frontmatter)

    def test_flow_guidance(self):
        text = (ROOT / "skills/flow/SKILL.md").read_text()
        for phrase in (
            "queued", "dispatched", "round-N", "checks", "slot-wait", "review",
            "ready", "landed", "failed", "${CLAUDE_PLUGIN_ROOT}/scripts/packet-event",
            "${CLAUDE_PLUGIN_ROOT}/scripts/flow-report", "${CLAUDE_PLUGIN_ROOT}/docs/flow.md",
            "|| true", "states that were not observed", "incomplete", "no brief text",
            "Do not edit the owner's scripts without approval", "wait for approval",
            "remove the calls", "keep or delete the log",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_readme_lists_skill(self):
        self.assertIn("/agent-kaizen:flow", (ROOT / "README.md").read_text())


if __name__ == "__main__":
    unittest.main()
