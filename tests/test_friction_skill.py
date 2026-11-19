"""Contracts for the friction skill and its entry points."""
import json
import subprocess
import sys
import tempfile
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

    def test_cycle_looks_up_canonical_audits_before_refresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            main = Path(tmp).resolve() / "main"
            main.mkdir()
            linked = main.with_name("linked")

            def git(*args):
                subprocess.run(["git", "-C", str(main), *args], check=True, capture_output=True)

            git("init", "-q")
            audits = main / "docs/kaizen"
            audits.mkdir(parents=True)
            (audits / "LEDGER.md").touch()
            git("add", ".")
            git("-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                "-c", "commit.gpgsign=false", "commit", "-qm", "initial")
            git("worktree", "add", "-qb", "linked", str(linked))
            config = json.loads(subprocess.check_output([
                sys.executable, str(ROOT / "scripts/kaizen-scheduled"),
                "config", "show", "--for", str(linked),
            ]))
            self.assertEqual(Path(config["localAudits"]), audits)
        lookup = read("skills/cycle/SKILL.md").split("**Measure.**")[0]
        self.assertIn("newest `token-audit-*.md` across `docs/kaizen/` and `localAudits`", lookup)
        self.assertNotIn("review --dry-run", lookup)

    def test_entry_points_and_policy(self):
        self.assertIn("skills/friction/SKILL.md", read("skills/review/SKILL.md"))
        self.assertIn("bounded friction view", read("agents/kaizen-auditor.md"))
        undo = read("skills/undo/SKILL.md")
        for phrase in ("actions undo <ID> --for .", "different project", "matching ledger row",
                       "kaizen-backup undo <target>", "reverse commands"):
            self.assertIn(phrase, undo)
        self.assertIn("scoped local commit", read("docs/autonomy.md"))
        self.assertIn("/agent-kaizen:friction", read("README.md"))

    def test_friction_preparation_and_action_policy(self):
        friction = read("skills/friction/SKILL.md")
        for phrase in ("scripts/host-probe\" --project <canonical-project> --out <reports>",
                       "one hour", "view's `actions` (never `flags`)", "hostActions=apply",
                       "hostActions.value", "config show --for .", "otherwise use `suggest`",
                       "scripts/friction-catalog.json", "linux-localsearch"):
            self.assertIn(phrase, friction)
        self.assertLess(friction.index("scripts/host-probe"), friction.index("friction prepare --for ."))

    def test_scoped_refresh_backup_and_review(self):
        cycle = read("skills/cycle/SKILL.md")
        for phrase in ("review --dry-run --project-dir .", "paths:", "--cwd <path>"):
            self.assertIn(phrase, cycle)
        autonomy = read("docs/autonomy.md")
        self.assertIn('begin --skill <skill> --ledger "<ledger text>" --repo <project root>', autonomy)
        review = read("skills/review/SKILL.md")
        self.assertIn("supplied report", review)
        self.assertLess(review.index("supplied report"), review.index("newest usage audit"))


if __name__ == "__main__":
    unittest.main()
