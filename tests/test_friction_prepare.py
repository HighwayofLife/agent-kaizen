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
from concurrent.futures import ThreadPoolExecutor
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

    def test_duplicate_mixed_basis_flags(self):
        flags = [dict(self.flag, basis="measured"), dict(self.flag, basis="row_gap", value=8)]
        new, state = self.compare({}, flags=flags, basis="mixed")
        self.assertEqual(len(new), 2)
        self.assertFalse(self.compare(state, flags=flags, basis="mixed")[0])

    def test_estimated_acknowledgement_does_not_hide_measured(self):
        estimated = dict(self.flag, basis="estimated", value=16)
        measured = dict(self.flag, basis="measured", value=4)
        _, state = self.compare({}, flag=estimated, basis="mixed")
        self.assertEqual(self.compare(state, flag=measured, basis="mixed")[0], [measured])

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
        data = dict(v=1, report=self.report.name, scope=self.scope,
                    since=(self.current - timedelta(days=7)).isoformat())
        if self.block is not None:
            data["friction"] = self.block
        raw = json.dumps(data)
        binding = dict(size=len(raw.encode()), sha256=prepare.hashlib.sha256(raw.encode()).hexdigest())
        self.write(self.report, '# Token audit\nSince: ' + (self.current - timedelta(days=7)).isoformat()
                   + ' (UTC; disposable evidence).\n<!-- token-audit-scope ' + json.dumps(self.scope)
                   + ' -->\n<!-- token-audit-extract ' + json.dumps(dict(v=1, file=self.extract.name))
                   + ' -->\n<!-- token-audit-friction ' + json.dumps(binding)
                   + ' -->\n<!-- token-audit-complete -->\n')
        self.write(self.extract, raw)
        self.probe_path = self.write(self.obj.folder / "host-probe-disposable.json", json.dumps(self.probe))

    def run_prepare(self, report=None, interactive=True):
        return prepare.prepare(self.config / "audits", self.backups, self.obj, report,
                               self.runner["effective"](self.project), "propose-only", self.current + timedelta(seconds=2),
                               self.runner["action_project"], self.runner["key"], interactive=interactive)

    def reconcile(self, inputs, actions=None, current=None):
        return prepare.reconcile(self.config / "audits", self.backups, self.obj, inputs,
                                 self.runner["effective"](self.project), current or self.current + timedelta(seconds=3),
                                 self.runner["action_project"], self.runner["key"], actions)

    def actions(self, ids=(), intent="suggest"):
        return self.write(self.root / "actions.txt", '<!-- kaizen-host-actions ' + json.dumps(
            dict(v=1, actions=[dict(id=ident, intent=intent) for ident in ids])) + ' -->\n')

    def candidate(self):
        self.probe["findings"] = [dict(id="low-disk", catalog_id="low-disk", subject="project-volume",
                                       evidence=dict(free_disk_bytes=1))]
        self.write_evidence()
        inputs = self.run_prepare()
        return inputs, json.loads(inputs.read_text())["actions"][0]["id"]

    def test_automatic_selection_bounds_parses(self):
        for i in range(30):
            self.write(self.obj.folder / ("token-audit-%03d.md" % i), "bad")
        original = prepare._evidence
        with patch.object(prepare, "_evidence", side_effect=original) as read:
            try:
                self.run_prepare()
            except ValueError:
                pass
            self.assertLessEqual(read.call_count, 8)

    def test_directory_read_does_not_leak_descriptors(self):
        fd_dir = pathlib.Path("/dev/fd")
        if not fd_dir.exists():
            self.skipTest("descriptor directory unavailable")
        host = runpy.run_path(str(PATH.parent / "kaizen_friction_actions.py"))
        before = len(list(fd_dir.iterdir()))
        for _ in range(30):
            with self.assertRaises((OSError, ValueError)):
                prepare._read(self.project / "docs", host)
        self.assertEqual(len(list(fd_dir.iterdir())), before)

    def test_host_actions_off_needs_no_probe(self):
        self.write(self.project / "docs/kaizen/config.json", '{"hostActions":"off"}')
        self.probe_path.unlink()
        self.assertTrue(self.run_prepare())

    def test_probe_without_friction_block(self):
        self.candidate()
        self.block = None
        self.write_evidence()
        self.assertTrue(json.loads(self.run_prepare().read_text())["actions"])

    def test_linked_worktree_finding_uses_canonical_provenance(self):
        linked = str(self.root / "linked" / "build")
        canonical = self.project / "build"
        self.probe["findings"] = [dict(id="indexed-output", catalog_id="spotlight-output",
                                       subject=linked, evidence=dict(size_bytes=42))]
        self.probe["regenerable_dirs"] = [dict(path=str(canonical), size_bytes=42)]
        self.write_evidence()
        original = self.runner["action_project"]
        def canonicalize(project, *, selector=None):
            if selector in (linked, str(canonical)):
                return self.project, canonical
            return original(project, selector=selector)
        with patch.dict(self.runner, {"action_project": canonicalize}):
            self.assertEqual(len(json.loads(self.run_prepare().read_text())["actions"]), 1)
            self.probe["regenerable_dirs"] = []
            self.write_evidence()
            with self.assertWarns(UserWarning):
                self.assertEqual(json.loads(self.run_prepare().read_text())["actions"], [])

    def test_worktree_only_outputs_merge_and_keep_flags(self):
        linked1, linked2 = self.root / 'linked1', self.root / 'linked2'
        for linked in (linked1, linked2):
            (linked / 'build').mkdir(parents=True)
        self.obj.anchors.extend([linked1, linked2])
        self.probe['findings'] = [dict(id='indexed-output', catalog_id='spotlight-output',
                                       subject=str(linked / 'build'), evidence=dict(size_bytes=size))
                                  for linked, size in ((linked1, 42), (linked2, 84))]
        self.probe['regenerable_dirs'] = [dict(path=item['subject'], size_bytes=item['evidence']['size_bytes'])
                                          for item in self.probe['findings']]
        self.write_evidence()
        view = json.loads(self.run_prepare().read_text())
        self.assertEqual(len(view['actions']), 1)
        self.assertEqual(view['actions'][0]['evidence'], [84])
        self.assertTrue(view['flags'])
        receipt = json.loads(next((self.backups / 'friction').glob('receipt-*.json')).read_text())
        self.assertEqual(len(next(iter(receipt['allowed'].values()))['provenance']), 2)

    def test_acknowledged_worktree_finding_stays_closed(self):
        for i, size in enumerate((42, 84)):
            linked = self.root / f'linked{i}'
            build = linked / 'build'
            build.mkdir(parents=True)
            self.obj.anchors.append(linked)
            self.probe['findings'].append(dict(id='indexed-output', catalog_id='spotlight-output',
                                               subject=str(build), evidence=dict(size_bytes=size)))
            self.probe['regenerable_dirs'].append(dict(path=str(build), size_bytes=size))
        self.write_evidence()
        inputs = self.run_prepare()
        action, = json.loads(inputs.read_text())['actions']
        self.assertEqual(action['evidence'], [84])
        self.assertEqual(self.reconcile(inputs, self.actions([action['id']])), {action['id']: 'terminal'})
        self.reconcile(inputs)
        for attempt in range(2):
            with self.subTest(attempt=attempt):
                self.assertIsNone(self.run_prepare())

    def test_worktree_output_symlink_escape_is_rejected(self):
        linked, outside = self.root / 'linked', self.root / 'outside'
        linked.mkdir()
        outside.mkdir()
        (linked / 'build').symlink_to(outside, target_is_directory=True)
        self.obj.anchors.append(linked)
        path = str(linked / 'build')
        self.probe['findings'] = [dict(id='indexed-output', catalog_id='spotlight-output',
                                       subject=path, evidence=dict(size_bytes=42))]
        self.probe['regenerable_dirs'] = [dict(path=path, size_bytes=42)]
        self.write_evidence()
        with self.assertWarns(UserWarning):
            view = json.loads(self.run_prepare().read_text())
        self.assertFalse(view['actions'])
        self.assertTrue(view['flags'])

    def test_flapping_action_is_held(self):
        _, ident = self.candidate()
        host = runpy.run_path(str(PATH.parent / "kaizen_friction_actions.py"))
        store = host["HostActions"](self.config / "audits", self.backups, self.runner["action_project"], self.runner["key"])
        row = dict(id=ident, status="open", evidence="old", flaps=2)
        # Patch the class returned by the module loaded by prepare.
        original = prepare.runpy.run_path
        def load(path):
            module = original(path)
            module["HostActions"].scoped = lambda self, project: [row]
            return module
        self.block["flags"] = []
        self.write_evidence()
        with patch.object(prepare.runpy, "run_path", side_effect=load):
            self.assertIsNone(self.run_prepare())

    def test_reconciliation_rechecks_policy_after_lock(self):
        from contextlib import contextmanager
        inputs = self.run_prepare()
        original = prepare.runpy.run_path
        def load(path):
            module = original(path)
            if str(path).endswith('kaizen_friction_actions.py'):
                locked = module['_locked']
                @contextmanager
                def disable_while_waiting(directory, name):
                    with locked(directory, name):
                        self.write(self.project / 'docs/kaizen/config.json', '{"friction":"off"}')
                        yield
                module['_locked'] = disable_while_waiting
            return module
        with patch.object(prepare.runpy, 'run_path', side_effect=load):
            with self.assertRaises(ValueError):
                self.reconcile(inputs, self.actions())

    def test_interruption_empty_import_and_idempotent_ack(self):
        first = self.run_prepare()
        inputs = self.run_prepare()  # An interrupted preparation never advances acknowledgement.
        receipts = sorted((self.backups / "friction").glob("receipt-*.json"))
        self.assertEqual(*(json.loads(p.read_text())["comparison"] for p in receipts))
        with self.assertRaises(ValueError):
            self.reconcile(inputs)
        self.assertEqual(self.reconcile(inputs, self.actions()), {})
        with self.assertRaises(ValueError):
            self.reconcile(first)
        self.reconcile(inputs)  # A process can stop after import, then resume here.
        self.reconcile(inputs)
        self.assertEqual(self.reconcile(inputs, self.actions()), {})
        self.assertIsNone(self.run_prepare())

    def test_suggestion_retry_and_cross_project_id(self):
        inputs, ident = self.candidate()
        for intent in ("apply", "unexpected"):
            with self.assertRaises(ValueError):
                self.reconcile(inputs, self.actions([ident], intent))
        other = self.root / "other"
        (other / "docs/kaizen").mkdir(parents=True)
        host = runpy.run_path(str(PATH.parent / "kaizen_friction_actions.py"))
        store = host["HostActions"](self.config / "audits", self.backups, self.runner["action_project"], self.runner["key"])
        copied = store.action_id(other, "low-disk", "project-volume", allowed=("project-volume",))
        with self.assertRaises(ValueError):
            self.reconcile(inputs, self.actions([copied]))
        actions = self.actions([ident])
        self.assertEqual(self.reconcile(inputs, actions), {ident: "terminal"})
        self.assertEqual(self.reconcile(inputs, actions), {ident: "terminal"})
        with self.assertRaises(ValueError):
            self.reconcile(inputs, self.actions())  # A retry cannot change the selection.
        self.reconcile(inputs)
        self.assertEqual(store.scoped(self.project)[0]["status"], "open")
        self.assertNotIn("pending", store.scoped(self.project)[0])
        self.assertIsNone(self.run_prepare())

    def test_forged_views_receipts_and_live_changes(self):
        inputs, ident = self.candidate()
        actions = self.actions([ident])
        original = inputs.read_bytes()
        inputs.write_bytes(original.replace(b'"flags"', b'"forged"'))
        with self.assertRaises(ValueError):
            self.reconcile(inputs, actions)
        inputs.write_bytes(original)
        receipt = next((self.backups / "friction").glob("receipt-*.json"))
        frozen = receipt.read_bytes()
        receipt.write_bytes(frozen.replace(b'"suggest"', b'"apply"'))
        with self.assertRaises(ValueError):
            self.reconcile(inputs, actions)
        receipt.write_bytes(frozen)
        for path in (self.report, self.extract, self.probe_path):
            raw = path.read_bytes()
            path.write_bytes(raw + b"\n")
            with self.subTest(evidence=path.name), self.assertRaises(ValueError):
                self.reconcile(inputs, actions)
            path.write_bytes(raw)
        inputs = self.run_prepare()
        with self.assertRaises(ValueError):
            self.reconcile(inputs, actions, self.current + timedelta(seconds=prepare.PROBE_AGE + 3))
        self.write(self.project / "docs/kaizen/config.json", '{"hostActions":"off"}')
        with self.assertRaises(ValueError):
            self.reconcile(inputs, actions)

    def test_concurrent_generations_disabled_and_scheduled(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            inputs = list(pool.map(lambda _: self.run_prepare(), range(2)))
        older, latest = sorted(inputs)
        with self.assertRaises(ValueError):
            self.reconcile(older, self.actions())
        self.write(self.project / "docs/kaizen/config.json", '{"friction":"off"}')
        with self.assertRaises(ValueError):
            self.reconcile(latest, self.actions())
        self.write(self.project / "docs/kaizen/config.json", '{}')
        scheduled = self.run_prepare(interactive=False)
        with self.assertRaises(ValueError):
            self.reconcile(scheduled, self.actions())
        with self.assertRaises(ValueError):
            self.reconcile(scheduled)

    def test_import_uses_only_the_bounded_wire_block(self):
        inputs, ident = self.candidate()
        valid = self.actions([ident]).read_text().strip()
        for text in ("prose\n" + valid, valid + "\n" + valid, "x" * 8193,
                     valid.replace('"intent": "suggest"', '"intent": "suggest", "extra": 1'),
                     self.actions([ident, ident]).read_text()):
            with self.subTest(size=len(text)), self.assertRaises(ValueError):
                self.reconcile(inputs, self.write(self.root / "actions.txt", text))
        with self.assertRaises(ValueError):
            self.reconcile(inputs)

    def test_pending_scheduled_write_cannot_ack(self):
        inputs, ident = self.candidate()
        self.reconcile(inputs, self.actions([ident]))
        host = runpy.run_path(str(PATH.parent / "kaizen_friction_actions.py"))
        store = host["HostActions"](self.config / "audits", self.backups, self.runner["action_project"], self.runner["key"])
        receipt = json.loads(next((self.backups / "friction").glob("receipt-*.json")).read_text())
        pending = dict(receipt["allowed"][ident], intents=["apply"])
        block = self.actions([ident], "apply").read_text().strip()
        store.import_actions(block, {ident: pending}, self.project, "scheduled-write")
        before = next((self.backups / "friction").glob("prepare-*.json")).read_bytes()
        with self.assertRaises(ValueError):
            self.reconcile(inputs)
        self.assertEqual(next((self.backups / "friction").glob("prepare-*.json")).read_bytes(), before)

    def test_new_generation_invalidates_successful_older_import(self):
        older = self.run_prepare()
        self.reconcile(older, self.actions())
        latest = self.run_prepare()
        with self.assertRaises(ValueError):
            self.reconcile(older)
        self.block["flags"] = []
        self.write_evidence()
        with self.assertRaises(ValueError):
            self.reconcile(latest, self.actions())
        with self.assertRaises(ValueError):
            self.reconcile(latest)

    def test_evidence_changed_during_rederivation_is_refused(self):
        inputs = self.run_prepare()
        original = prepare._read

        def changing_read(path, *args, **kwargs):
            result = original(path, *args, **kwargs)
            if path == self.probe_path:
                self.report.write_bytes(self.report.read_bytes() + b"\n")
            return result

        with patch.object(prepare, "_read", side_effect=changing_read), self.assertRaises(ValueError):
            self.reconcile(inputs, self.actions())

    def test_swapped_extract_after_receipt_is_refused(self):
        inputs = self.run_prepare()
        info = self.extract.stat()
        raw = self.extract.read_bytes()
        self.extract.write_bytes(raw.replace(b'private subject', b'forged  subject'))
        os.utime(self.extract, ns=(info.st_atime_ns, info.st_mtime_ns))
        self.assertEqual(self.extract.stat().st_size, info.st_size)
        with self.assertRaises(ValueError):
            self.reconcile(inputs, self.actions())

    def test_swapped_extract_before_first_preparation_is_refused(self):
        raw = self.extract.read_bytes()
        self.extract.write_bytes(raw.replace(b'private subject', b'forged  subject'))
        with self.assertRaisesRegex(ValueError, "extract digest or size"):
            self.run_prepare(self.report)
        self.assertFalse(self.backups.exists())

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
        self.block = None
        self.write_evidence()
        self.assertIsNone(self.run_prepare())

    def test_installed_runner_prepares_real_disposable_evidence(self):
        self.candidate()
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
        inputs = pathlib.Path(result.stdout.strip())
        ident = json.loads(inputs.read_text())["actions"][0]["id"]
        for arguments in (("actions", "import", str(self.actions([ident])), "--inputs", str(inputs)),
                          ("friction", "acknowledge", str(inputs))):
            result = subprocess.run([sys.executable, str(runner), *arguments, "--for", str(self.project)],
                                    env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        stored = json.loads((self.config / "audits/host-actions.json").read_text())
        self.assertEqual(stored["actions"][ident]["status"], "open")
        state = json.loads(next((self.backups / "friction").glob("prepare-*.json")).read_text())
        self.assertEqual(state["acknowledged_generation"], json.loads(inputs.read_text())["generation"])
        self.assertTrue(state["acknowledged"]["cohorts"])


if __name__ == "__main__":
    unittest.main()
