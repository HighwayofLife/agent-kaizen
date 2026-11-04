"""Contract tests for global scheduled configuration keys."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/kaizen-scheduled"
DEFAULTS = {
    "projectCommands": {},
    "notesLedger": {},
    "calibrationLadder": ["haiku", "sonnet medium", "sonnet high", "opus high"],
    "rulesLintFiles": [],
    "localScripts": [],
}


class ConfigKeysTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = dict(os.environ, CLAUDE_CONFIG_DIR=str(self.root / "config"))
        self.config = self.root / "config/agent-kaizen.json"
        self.project = self.root / "project"
        (self.project / "docs/kaizen").mkdir(parents=True)

    def run_config(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), "config", *args],
                              env=self.env, text=True, capture_output=True)

    def test_defaults_and_round_trip(self):
        shown = json.loads(self.run_config("show").stdout)
        for name, value in DEFAULTS.items():
            self.assertEqual(shown[name], {"value": value, "source": "default"})
        commands = {"/work/proj": {"shadowStatus": ["python3", "tools/x.py", "--shadow-status"],
                                   "outcomeLog": "out/packets.jsonl"}}
        result = self.run_config("set", "projectCommands=" + json.dumps(commands))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.config.read_text())["projectCommands"], commands)
        self.assertEqual(json.loads(self.run_config("show").stdout)["projectCommands"],
                         {"value": commands, "source": "global"})

    def test_invalid_values_rejected_and_ignored(self):
        invalid = {
            "projectCommands": [{"/work/proj": {"shadowStatus": "python3"}},
                                {"/work/proj": {"outcomeLog": "out/../x"}},
                                {"relative": {}}, {"~user/project": {}}, {"/work/proj": {"unknown": []}}],
            "notesLedger": [{"csv": "~/notes.csv", "measureAfterDays": 0}, {"timeline": "x"}, {"csv": ""}],
            "calibrationLadder": [["model effort extra"], [""]],
            "rulesLintFiles": [[1], [""]],
            "localScripts": [["tools/check"], [""]],
        }
        self.config.parent.mkdir(parents=True)
        for name, values in invalid.items():
            for value in values:
                with self.subTest(name=name, value=value):
                    result = self.run_config("set", name + "=" + json.dumps(value))
                    self.assertNotEqual(result.returncode, 0)
                    self.config.write_text(json.dumps({name: value}))
                    result = self.run_config("show")
                    self.assertIn(name + "=", result.stderr)
                    self.assertIn("invalid", result.stderr)
                    self.assertEqual(json.loads(result.stdout)[name],
                                     {"value": DEFAULTS[name], "source": "default"})

    def test_global_only(self):
        project_config = self.project / "docs/kaizen/config.json"
        project_config.write_text(json.dumps(DEFAULTS))
        shown = self.run_config("show", "--for", str(self.project))
        for name, value in DEFAULTS.items():
            with self.subTest(name=name):
                result = self.run_config("set", "--for", str(self.project), name + "=" + json.dumps(value))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(name + " is global-only", result.stderr)
                self.assertIn(name + " is global-only, ignored", shown.stderr)
                self.assertEqual(json.loads(shown.stdout)[name], {"value": value, "source": "default"})

    def test_valid_values(self):
        values = {"projectCommands": {"~/proj": {"slowTests": ["test"], "speedReport": ["report"]}},
                  "notesLedger": {"csv": "~/notes.csv", "timeline": "~/timeline", "measureAfterDays": 1},
                  "calibrationLadder": ["model", "model effort"],
                  "rulesLintFiles": ["docs/*.md"], "localScripts": ["check"]}
        result = self.run_config("set", *(name + "=" + json.dumps(value) for name, value in values.items()))
        self.assertEqual(result.returncode, 0, result.stderr)
        for name, value in values.items():
            self.assertEqual(json.loads(result.stdout)[name], {"value": value, "source": "global"})
