import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LINT = ROOT / "scripts/rules-lint"
FIXTURES = ROOT / "tests/fixtures/rules_lint"


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class RulesLintTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.claude = self.root / "claude"
        self.repo = self.root / "repo"
        for path in (self.home, self.claude, self.repo):
            path.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def run_lint(self, *args, script=LINT, cwd=None):
        env = dict(os.environ, HOME=str(self.home), CLAUDE_CONFIG_DIR=str(self.claude))
        return subprocess.run([sys.executable, str(script), *map(str, args)],
                              capture_output=True, text=True, env=env, cwd=cwd or self.root)

    def test_clean(self):
        write(self.claude / "CLAUDE.md", "all good\n")
        result = self.run_lint("--repo", self.repo)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("0 stale-rule hit(s)", result.stdout)

    def test_sources_allow_and_dropped(self):
        shutil.copy(FIXTURES / "CLAUDE.md", self.repo / "CLAUDE.md")
        shutil.copy(FIXTURES / "rules-lint.txt", self.claude / "kaizen-rules-lint.txt")
        write(self.repo / "docs/kaizen/rules-lint.txt", "repo stale # comment\n")
        write(self.repo / "AGENTS.md", "obsolete instruction\nrepo stale\n"
              "obsolete instruction rules-lint: allow\n")
        write(self.repo / "docs/agents/DROPPED.md", "repo stale\n")
        result = self.run_lint("--repo", self.repo, "--json")
        self.assertEqual(result.returncode, 1, result.stderr)
        hits = json.loads(result.stdout)["hits"]
        self.assertEqual(len(hits), 4)
        self.assertEqual({(Path(h["path"]).name, h["line"]) for h in hits},
                         {("CLAUDE.md", 2), ("CLAUDE.md", 3), ("AGENTS.md", 1), ("AGENTS.md", 2)})
        self.assertIn(r"project-repos\.txt", {h["pattern"] for h in hits})
        self.assertIn("copies the runner, token-audit", {h["pattern"] for h in hits})

    def test_text_output_and_global_root(self):
        write(self.claude / "kaizen-rules-lint.txt", "old wording\n")
        write(self.claude / "agents/a.md", "x\nold wording\n")
        result = self.run_lint()
        self.assertEqual(result.returncode, 1)
        self.assertIn("a.md:2: old wording: old wording", result.stdout)
        self.assertIn("1 stale-rule hit(s)", result.stdout)

    def test_extra_globs_and_default_repo(self):
        write(self.claude / "agent-kaizen.json", json.dumps({"rulesLintFiles": ["extra/*.md"]}))
        write(self.claude / "extra/a.md", "old wording\n")
        write(self.claude / "kaizen-rules-lint.txt", "old wording\n")
        write(self.repo / "CLAUDE.md", "old wording\n")
        result = self.run_lint("--json", cwd=self.repo)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["count"], 2)

    def test_agents_only_repo_is_detected(self):
        write(self.claude / "kaizen-rules-lint.txt", "old wording\n")
        write(self.repo / "AGENTS.md", "old wording\n")
        result = self.run_lint("--json", cwd=self.repo)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["count"], 1)

    def test_bundled_patterns_name_no_project(self):
        text = (ROOT / "scripts/rules-lint.patterns").read_text(encoding="utf-8")
        for line in text.splitlines():
            self.assertNotIn("New World", line)
            self.assertNotIn("playtest", line)

    def test_no_patterns_and_bad_pattern(self):
        script = self.root / "rules-lint"
        shutil.copy(LINT, script)
        result = self.run_lint(script=script)
        self.assertEqual(result.returncode, 0)
        self.assertIn("no patterns configured", result.stdout)
        write(self.claude / "kaizen-rules-lint.txt", "[\n")
        result = self.run_lint(script=script)
        self.assertEqual(result.returncode, 2)
        self.assertIn("rules-lint: bad pattern", result.stderr)

    def test_settings_object_and_escaped_prefixes(self):
        write(self.claude / "agent-kaizen.json", "[1]")
        result = self.run_lint("--repo", self.repo)
        self.assertEqual(result.returncode, 2)
        self.assertIn("JSON object", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.claude = self.root / "claude[1]"
        self.repo = self.root / "repo[1]"
        write(self.claude / "agent-kaizen.json", json.dumps({"rulesLintFiles": ["extra/*.md"]}))
        write(self.claude / "extra/a.md", "old wording")
        write(self.claude / "CLAUDE.md", "old wording")
        write(self.claude / "kaizen-rules-lint.txt", "old wording")
        write(self.repo / "AGENTS.md", "old wording")
        result = self.run_lint("--repo", self.repo, "--json")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(json.loads(result.stdout)["count"], 3)

    def test_pattern_sources_excluded_even_when_explicitly_selected(self):
        repo_patterns = self.repo / "docs/kaizen/rules-lint.txt"
        script = self.root / "rules-lint"
        shutil.copy(LINT, script)
        builtin_patterns = script.with_name("rules-lint.patterns")
        write(builtin_patterns, "old wording\n")
        write(repo_patterns, "old wording\n")
        write(self.claude / "agent-kaizen.json", json.dumps({"rulesLintFiles": [str(repo_patterns), str(builtin_patterns)]}))
        result = self.run_lint("--repo", self.repo, "--json", script=script)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["hits"], [])

    def test_usage_and_help(self):
        self.assertEqual(self.run_lint("--bogus").returncode, 2)
        self.assertEqual(self.run_lint("--repo").returncode, 2)
        self.assertEqual(self.run_lint("--help").returncode, 0)


if __name__ == "__main__":
    unittest.main()
