"""Offline host-action store and CLI checks using disposable projects."""
from concurrent.futures import ThreadPoolExecutor
import hmac
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
from threading import Barrier
import unittest
from unittest.mock import patch

from scripts import kaizen_friction_actions as actions

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/kaizen-scheduled"
RUNNER = runpy.run_path(str(SCRIPT))
LITERALS = ("ls", "ls -a")


@unittest.skipIf(actions.fcntl is None, "requires flock")
class HostActionsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        self.project, self.other = root / "projäct", root / "other"
        self.project.mkdir()
        self.other.mkdir()
        self.env = dict(os.environ, CLAUDE_CONFIG_DIR=str(root / "claude"), KAIZEN_BACKUP_DIR=str(root / "backup"))
        self.store = actions.HostActions(root / "claude/audits", root / "backup", RUNNER["action_project"], RUNNER["key"])
        self.secret = self.store.friction / "machine.key"

    def cli(self, *args, project=None, code=0):
        result = subprocess.run([sys.executable, str(SCRIPT), "actions", *args, "--for",
                                 str(project or self.project)], capture_output=True, text=True, env=self.env)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result.stdout

    def record(self, project=None, literal="ls"):
        return self.store.record(project or self.project, "low-disk", literal, "e" * 600, allowed=LITERALS)

    def test_missing_store_and_concurrent_ids(self):
        self.assertEqual(json.loads(self.cli("list", "--json")), [])
        self.assertFalse(self.store.path.parent.exists())
        barrier = Barrier(4)

        def record(scope, literal):
            barrier.wait(timeout=10)
            return self.record(scope, literal)

        with ThreadPoolExecutor(4) as pool:
            ids = list(pool.map(record, [self.project] * 3 + [self.other], ("ls", "ls", "ls -a", "ls")))
        payload = f'[1,{json.dumps(str(self.project))},"low-disk","ls"]'.encode("ascii")
        self.assertEqual(ids[:2], ["fa1_" + hmac.new(self.secret.read_bytes(), payload, "sha256").hexdigest()] * 2)
        scoped = json.loads(self.cli("list", "--json"))
        self.assertEqual({row["id"] for row in scoped}, {ids[0], ids[2]})
        self.assertEqual(len(set(ids)), 3)
        self.assertTrue(all(row["projects"] == [RUNNER["key"](self.project)] and not row["eligible"]
                            and len(row["evidence"]) == 500 for row in scoped))
        self.assertEqual(self.secret.stat().st_mode & 0o777, 0o600)
        self.assertEqual([row["id"] for row in self.store.scoped(self.other)], [ids[3]])

    def test_cli_marks_unknown_and_disabled(self):
        (self.project / "docs/kaizen").mkdir(parents=True)
        ident = self.record(self.project / "docs")
        with patch.object(actions, "_id", return_value=ident), self.assertRaisesRegex(ValueError, "collision"):
            self.record(literal="ls -a")
        (self.store.path.parent.parent / "agent-kaizen.json").write_text('{"enabled":false}')
        self.cli("done", ident, project=self.other, code=2)
        for command, status in actions.STATES.items():
            self.cli(command, ident)
            row, = self.store.scoped(self.project)
            self.assertEqual((row["status"], row["eligible"]), (status, False))
            self.assertEqual(row["done_by"], "user" if command == "done" else None)
            before = self.store.path.read_bytes()
            self.cli(command, ident)
            self.assertEqual(self.store.path.read_bytes(), before)

    def test_invalid_store_and_key_preserve_bytes(self):
        ident = self.record()
        path = self.store.path
        before = path.read_bytes()
        for raw in (b"{", b'{"v":2,"actions":{}}', b" " * (actions.STORE_LIMIT + 1)):
            path.write_bytes(raw)
            self.cli("done", ident, code=2)
            self.assertEqual(path.read_bytes(), raw)
        path.write_bytes(before)
        self.secret.unlink()
        self.cli("done", ident, code=2)
        self.assertFalse(self.secret.exists())
        self.assertEqual(path.read_bytes(), before)

    def test_atomic_replace_and_unsafe_files(self):
        ident = self.record()
        path = self.store.path
        before = path.read_bytes()
        with patch.object(actions, "fcntl", None), self.assertRaises(ValueError):
            self.store.mark(self.project, ident, "done")
        with patch.object(os, "replace", side_effect=OSError), self.assertRaises(OSError):
            self.store.mark(self.project, ident, "done")
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(set(path.parent.iterdir()), {path, path.with_suffix(".json.lock")})
        path.unlink()
        path.symlink_to(self.secret)
        self.cli("done", ident, code=2)
