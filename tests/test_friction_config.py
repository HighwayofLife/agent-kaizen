"""Typed friction configuration and scope contracts."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/kaizen-scheduled"


class FrictionConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "project with spaces"
        (self.project / "docs/kaizen").mkdir(parents=True)
        self.project_config = self.project / "docs/kaizen/config.json"
        self.global_config = self.root / "config/agent-kaizen.json"
        self.env = dict(os.environ, CLAUDE_CONFIG_DIR=str(self.global_config.parent))

    def config(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), "config", *map(str, args)],
                              env=self.env, text=True, capture_output=True)

    def test_values_precedence_and_scope(self):
        result = self.config("set", "friction=off", "frictionSlowCallSeconds=10",
                             "frictionHeavySeconds=5", "frictionSampler=off", "hostActions=suggest")
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.config("set", "--for", self.project, "friction=on", "hostActions=off",
                             'frictionOutputDirs=["build output/cache", "out"]')
        self.assertEqual(result.returncode, 0, result.stderr)
        shown = json.loads(result.stdout)
        for name, value, source in (("friction", "on", "project"), ("hostActions", "off", "project"),
                                    ("frictionSampler", "off", "global"),
                                    ("frictionSlowCallSeconds", 10, "global"),
                                    ("frictionHeavySeconds", 5, "global"),
                                    ("frictionOutputDirs", ["build output/cache", "out"], "project")):
            self.assertEqual(shown[name], {"value": value, "source": source})
        self.global_config.write_text(json.dumps({"frictionOutputDirs": ["out"], "frictionHeavySeconds": 20}))
        self.project_config.write_text(json.dumps({"frictionSampler": "off", "frictionHeavySeconds": 4}))
        result = self.config("show", "--for", self.project)
        self.assertIn("frictionOutputDirs is project-only, ignored", result.stderr)
        self.assertIn("frictionSampler is global-only, ignored", result.stderr)
        self.assertIn("frictionHeavySeconds=4 invalid, using 20", result.stderr)
        shown = json.loads(result.stdout)
        self.assertEqual(shown["frictionOutputDirs"], {"value": [], "source": "default"})
        self.assertEqual(shown["frictionHeavySeconds"], {"value": 20, "source": "global"})

    def test_invalid_values_never_write(self):
        self.global_config.parent.mkdir(parents=True)
        original = '{"schedule":"active"}\n'
        self.global_config.write_text(original)
        self.project_config.write_text(original)
        invalid = ("friction=maybe", "hostActions=true", "frictionSampler=true",
                   "frictionSlowCallSeconds=9", "frictionSlowCallSeconds=true",
                   "frictionHeavySeconds=4", "frictionHeavySeconds=5.0",
                   'frictionOutputDirs=["out"]')
        project_invalid = ('frictionOutputDirs=["../out"]', 'frictionOutputDirs=["a//b"]',
                           'frictionOutputDirs=["a/./b"]', 'frictionOutputDirs=[""]',
                           'frictionOutputDirs="out"', 'frictionOutputDirs=[1]',
                           'frictionOutputDirs=notjson', 'frictionOutputDirs=["/abs"]',
                           "frictionSampler=off")
        for args in [(item,) for item in invalid] + [("--for", self.project, item) for item in project_invalid]:
            with self.subTest(args=args):
                result = self.config("set", "schedule=off", *args)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(self.global_config.read_text(), original)
                self.assertEqual(self.project_config.read_text(), original)
        result = self.config("set", "--for", self.root / "missing", 'frictionOutputDirs=["out"]')
        self.assertEqual(result.returncode, 2)
        self.assertFalse((self.root / "missing").exists())

    def test_invalid_loaded_paths_and_types_warn(self):
        for value in (["a/../b"], ["a/"], [], "out", [False]):
            with self.subTest(value=value):
                self.project_config.write_text(json.dumps({"frictionOutputDirs": value}))
                result = self.config("show", "--for", self.project)
                self.assertEqual(result.returncode, 0)
                expected = {"value": value, "source": "project"} if value == [] else {"value": [], "source": "default"}
                self.assertEqual(json.loads(result.stdout)["frictionOutputDirs"], expected)
                if value != []:
                    self.assertIn("frictionOutputDirs=", result.stderr)
                    self.assertIn("invalid", result.stderr)


if __name__ == "__main__":
    unittest.main()
