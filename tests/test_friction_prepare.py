"""Tests for the scoped friction comparison gate."""
import importlib.util
import pathlib
import json
import os
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from test_schedule import CRONTAB

PATH = pathlib.Path(__file__).resolve().parents[1] / "scripts/kaizen_friction_prepare.py"
SPEC = importlib.util.spec_from_file_location("friction_prepare", PATH)
prepare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare)


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.scope = "/project"
        self.window = {"kind": "rolling", "seconds": 86400, "policy": "utc-now-floor-second"}
        self.thresholds = {"slow_call_seconds": 120, "heavy_seconds": 60}
        self.flag = {"id": "timeouts", "subject": "shell", "value": 4}

    def compare(self, state, flag=None, **changes):
        args = dict(project=self.scope, window=self.window, thresholds=self.thresholds,
                    basis="measured", flags=[flag or self.flag], acknowledged=state)
        args.update(changes)
        return prepare.compare_flags(**args)

    def test_buckets_and_legacy_state(self):
        new, state = self.compare({"flag_fingerprints": {"timeouts:shell": 100}})
        self.assertEqual(new, [self.flag])
        for value, expected in ((4, False), (3, False), (7, False), (8, True)):
            flag = dict(self.flag, value=value)
            self.assertEqual(bool(self.compare(state, flag)[0]), expected)
        self.assertEqual(state["cohorts"][next(iter(state["cohorts"]))].popitem()[1], 2)

    def test_policy_switches_and_switch_back(self):
        _, initial = self.compare({})
        for change in (dict(project="/other"), dict(basis="row_gap"),
                       dict(thresholds=dict(self.thresholds, heavy_seconds=61)),
                       dict(window=dict(self.window, seconds=172800)),
                       dict(window={"kind": "fixed", "cutoff": "2026-01-01T00:00:00Z"})):
            new, switched = self.compare(initial, **change)
            self.assertTrue(new)
            self.assertFalse(self.compare(switched)[0])
        _, fixed = self.compare(initial, window={"kind": "fixed", "cutoff": "2026-01-01T00:00:00Z"})
        self.assertTrue(self.compare(fixed, window={"kind": "fixed", "cutoff": "2026-01-02T00:00:00Z"})[0])

    def test_invalid_evidence_fails_closed(self):
        for value in (0, -1, float("nan"), float("inf"), True, "4"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.compare({}, dict(self.flag, value=value))
        for window in ({"kind": "rolling", "seconds": 86400, "policy": "unknown"},
                       {"kind": "fixed", "cutoff": "2026-01-01"}):
            with self.assertRaises(ValueError):
                self.compare({}, window=window)


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name).resolve()
        self.config, self.backups = self.root / "config", self.root / "backups"
        self.project = self.root / "project"
        (self.project / "docs/kaizen").mkdir(parents=True)
        self.environment = dict(os.environ, CLAUDE_CONFIG_DIR=str(self.config),
                                KAIZEN_BACKUP_DIR=str(self.backups), KAIZEN_HOST="claude",
                                CODEX_HOME=str(self.root / "codex"), COPILOT_HOME=str(self.root / "copilot"))
        environment = patch.dict(os.environ, self.environment, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        self.runner = runpy.run_path(str(PATH.parent / "kaizen-scheduled"))
        self.obj = self.runner["Project"](self.project, [self.project])
        self.current = datetime.now(timezone.utc).replace(microsecond=0)
        self.scope = dict(v=1, codex="none", cwd=[str(self.project)], project=None, project_dirs=[], window="7d")
        self.report = self.obj.folder / "token-audit-disposable.md"
        self.extract = self.config / "audits/extracts" / (self.report.stem + ".extract.json")
        self.block = dict(v=1, window=dict(kind="rolling", seconds=604800, policy="utc-now-floor-second"),
                          thresholds=dict(slow_call_seconds=120, heavy_seconds=60), basis="measured",
                          flags=[dict(id="timeouts", subject="private subject", value=4)],
                          permission_acceptance=[dict(literal="private permission")])
        self.probe = dict(v=1, project=str(self.project), generated_at=self.current.isoformat(), findings=[], regenerable_dirs=[])
        self.write_evidence()

    @staticmethod
    def write(path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def write_evidence(self):
        self.write(self.report, '# Token audit\nSince: ' + (self.current - timedelta(days=7)).isoformat()
                   + ' (UTC; disposable evidence).\n<!-- token-audit-scope ' + json.dumps(self.scope)
                   + ' -->\n<!-- token-audit-extract ' + json.dumps(dict(v=1, file=self.extract.name))
                   + ' -->\n<!-- token-audit-complete -->\n')
        self.write(self.extract, json.dumps(dict(v=1, report=self.report.name, scope=self.scope,
                   since=(self.current - timedelta(days=7)).isoformat(), friction=self.block)))
        self.probe_path = self.write(self.obj.folder / "host-probe-disposable.json", json.dumps(self.probe))

    def run_prepare(self, report=None):
        return prepare.prepare(self.config / "audits", self.backups, self.obj, report,
                               self.runner["effective"](self.project), "propose-only", self.current + timedelta(seconds=2),
                               self.runner["action_project"], self.runner["key"])

    def test_receipt_redaction_generation_and_read_only_ack(self):
        first = self.run_prepare(self.report)
        second = self.run_prepare()
        self.assertGreater(second.name, first.name)
        visible = second.read_text()
        self.assertNotIn(str(self.project), visible)
        self.assertNotIn("private", visible)
        receipt = json.loads(max((self.backups / "friction").glob("receipt-*.json")).read_text())
        self.assertEqual(receipt["identities"]["report"]["sha256"], prepare.hashlib.sha256(self.report.read_bytes()).hexdigest())
        self.assertEqual(receipt["permission_provenance"], self.block["permission_acceptance"])
        self.assertEqual(receipt["allowed"], {})
        state_path = next((self.backups / "friction").glob("prepare-*.json"))
        state = json.loads(state_path.read_text())
        self.assertEqual(state["acknowledged"], {})
        state["acknowledged"] = receipt["comparison"]
        state_path.write_text(json.dumps(state))
        before = state_path.read_bytes()
        self.assertIsNone(self.run_prepare())
        self.assertEqual(state_path.read_bytes(), before)
        self.assertFalse((self.config / "audits/host-actions.json").exists())

    def test_refuse_stale_forged_mismatched_and_unsupported_evidence(self):
        bad = [("report", "forged"), ("extract", "{"), ("extract", " " * (prepare.LIMIT + 1)),
               ("block", dict(v=2)), ("scope", dict(cwd=["/other"])),
               ("block", dict(thresholds={"slow_call_seconds": 121, "heavy_seconds": 60})),
               ("probe", dict(project="/other")), ("probe", dict(v=2)),
               ("probe", dict(generated_at=(self.current - timedelta(days=1)).isoformat()))]
        original_block, original_scope, original_probe = (json.dumps(v) for v in (self.block, self.scope, self.probe))
        for attribute, value in bad:
            self.block, self.scope, self.probe = map(json.loads, (original_block, original_scope, original_probe))
            if isinstance(value, dict):
                getattr(self, attribute).update(value)
            self.write_evidence()
            if isinstance(value, str):
                getattr(self, attribute).write_text(value)
            with self.subTest(attribute=attribute, value=str(value)[:40]), self.assertRaises((ValueError, OSError)):
                self.run_prepare(self.report)
        self.block, self.scope, self.probe = map(json.loads, (original_block, original_scope, original_probe))
        self.write_evidence()
        os.utime(self.report, (0, 0))
        with self.assertRaises(ValueError):
            self.run_prepare(self.report)
        self.write_evidence()
        self.extract.unlink()
        self.extract.symlink_to(self.report)
        with self.assertRaises(OSError):
            self.run_prepare(self.report)

    def test_candidate_ids_suppression_and_pending_imports(self):
        self.block["flags"] = []
        self.probe["findings"] = [dict(id="low-disk", catalog_id="low-disk", subject="project-volume", evidence=dict(free_disk_bytes=1))]
        self.write_evidence()
        path = self.run_prepare()
        receipt = json.loads(next((self.backups / "friction").glob("receipt-*.json")).read_text())
        ident, row = next(iter(receipt["allowed"].items()))
        host = runpy.run_path(str(PATH.parent / "kaizen_friction_actions.py"))
        store = host["HostActions"](self.config / "audits", self.backups, self.runner["action_project"], self.runner["key"])
        self.assertEqual(ident, store.action_id(self.project, "low-disk", "project-volume", allowed=("project-volume",)))
        self.assertEqual(json.loads(path.read_text())["actions"][0]["id"], ident)
        def import_intent(intent, generation):
            return store.import_actions('<!-- kaizen-host-actions ' + json.dumps(dict(v=1, actions=[dict(id=ident, intent=intent)])) + ' -->',
                                        {ident: dict(row, intents=[intent])}, self.project, generation)
        import_intent("suggest", "suggestion")
        before = store.path.read_bytes()
        self.assertIsNone(self.run_prepare())
        self.assertEqual(store.path.read_bytes(), before)
        store.mark(self.project, ident, "dismiss")
        self.assertIsNone(self.run_prepare())
        store.mark(self.project, ident, "reopen")
        store.mark(self.project, ident, "done")
        self.assertIsNone(self.run_prepare())
        self.probe["findings"][0]["evidence"]["free_disk_bytes"] = 2
        self.write_evidence()
        self.assertIsNotNone(self.run_prepare())
        store.mark(self.project, ident, "reopen")
        import_intent("apply", "unresolved")
        self.assertIsNotNone(self.run_prepare())
        self.assertEqual(store.scoped(self.project)[0]["status"], "open")

    def test_disabled_and_empty_cli_produce_no_path(self):
        config = self.project / "docs/kaizen/config.json"
        self.write(config, json.dumps(dict(friction="off")))
        self.report.unlink()
        self.assertIsNone(self.run_prepare())
        self.assertFalse(self.backups.exists())
        self.write(config, "{}")
        self.block["flags"] = []
        self.write_evidence()
        self.assertIsNone(self.run_prepare())
        result = subprocess.run([sys.executable, str(PATH.parent / "kaizen-scheduled"), "friction", "prepare", "--for", str(self.project)],
                                env=self.environment, capture_output=True, text=True)
        self.assertEqual((result.returncode, result.stdout), (0, ""), result.stderr)
        data = json.loads(self.extract.read_text())
        del data["friction"]
        self.extract.write_text(json.dumps(data))
        self.assertIsNone(self.run_prepare())

    def test_installed_runner_prepares_real_disposable_evidence(self):
        plugin = self.root / "plugins/cache/disposable/version"
        shutil.copytree(PATH.parent, plugin / "scripts")
        binary = self.root / "bin"
        cron = self.write(binary / "crontab", CRONTAB.replace("#!/usr/bin/env python3", "#!" + sys.executable))
        cron.chmod(0o755)
        env = dict(self.environment, HOME=str(self.root), CRON_FILE=str(self.root / "cron"),
                   PATH=str(binary) + os.pathsep + os.environ["PATH"])
        installed = subprocess.run([sys.executable, str(plugin / "scripts/install-schedule"), "--apply", "--scheduler", "cron"],
                                   env=env, capture_output=True, text=True)
        self.assertEqual(installed.returncode, 0, installed.stderr)
        shutil.rmtree(plugin)
        runner = self.config / "bin/kaizen-scheduled"
        result = subprocess.run([sys.executable, str(runner), "friction", "prepare", "--for", str(self.project)],
                                env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(pathlib.Path(result.stdout.strip()).read_text())["flags"][0]["value"], 4)


if __name__ == "__main__":
    unittest.main()
