"""Offline contracts for the unregistered Bash timing sampler."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import errno
import fcntl
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import kaizen_friction_sample as sampler


class SamplerTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.config = self.root / "agent-kaizen.json"
        self.samples = self.root / "audits" / "samples"
        self.env = {"HOME": str(self.root), "CLAUDE_CONFIG_DIR": str(self.root)}
        self.command = [sys.executable, str(SCRIPTS / "kaizen_friction_sample.py")]
        self.payload = dict(hook_event_name="PostToolUse", tool_name="Bash",
                            session_id="session; bad", tool_use_id="tool\tbad", duration_ms=1234.9,
                            tool_input={"command": "omit this"}, tool_response="omit output")

    def run_hook(self, payload=None, **env):
        payload = self.payload if payload is None else payload
        result = subprocess.run(self.command, input=payload if isinstance(payload, bytes)
                                else json.dumps(payload).encode(), capture_output=True,
                                env={**self.env, **env}, timeout=3)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b"", b""))

    def log(self):
        (path,) = self.samples.glob("*.tsv")
        return path

    def test_layout_privacy_and_optional_values(self):
        start = time.time_ns() // 1_000_000
        self.run_hook({**self.payload, "tool_response": "omit output" * 85000})
        path = self.log()
        row = path.read_bytes()
        ms, session, tool, duration, load, cores = row.decode().rstrip("\n").split("\t")
        self.assertGreaterEqual(int(ms), start)
        self.assertEqual(path.stem, datetime.fromtimestamp(int(ms) // 1000, timezone.utc).date().isoformat())
        self.assertEqual((session, tool, duration), ("sessionbad", "toolbad", "1234"))
        self.assertGreaterEqual(float(load), 0)
        self.assertGreater(int(cores), 0)
        self.assertLess(len(row), 4096)
        self.assertNotIn(b"omit", row)
        for optional in ({}, {"duration_ms": True}, {"duration_ms": -1},
                         {"duration_ms": float("inf")}, {"duration_ms": float("nan")},
                         {"session_id": "a" * 1024, "tool_use_id": 42}):
            self.run_hook({"hook_event_name": "PostToolUse", "tool_name": "Bash", **optional})
        rows = [line.split("\t") for line in path.read_text().splitlines()[1:]]
        self.assertEqual([row[1:4] for row in rows], [["", "", ""]] * 5 + [["a" * 512, "", ""]])

    def test_global_switches_and_host_precedence(self):
        for settings in ({"enabled": False, "frictionSampler": "on"}, {"frictionSampler": "off"}):
            self.config.write_text(json.dumps(settings))
            self.run_hook()
        self.config.write_text('{"enabled": true, "frictionSampler": "on"}')
        for env in (dict(KAIZEN_HOST="codex"), dict(KAIZEN_HOST="copilot"),
                    dict(KAIZEN_HOST="unknown", PLUGIN_ROOT="root"), dict(COPILOT_PLUGIN_ROOT="root")):
            self.run_hook(**env)
        self.assertFalse(self.samples.exists())
        with patch.dict(os.environ, {"COPILOT_PLUGIN_ROOT": "root", "PLUGIN_ROOT": "root"}, clear=True):
            self.assertEqual(sampler.host(), "copilot")
        override = self.root / "override"
        self.run_hook(KAIZEN_HOST="claude", COPILOT_PLUGIN_ROOT="root", PLUGIN_ROOT="root",
                      AUDIT_DIR=str(override))
        self.assertEqual(len(list((override / "samples").glob("*.tsv"))), 1)
        self.assertFalse(self.samples.exists())

    def test_invalid_and_oversized_input(self):
        for invalid in (b"{", [], {}, {**self.payload, "tool_name": "Read"},
                        {**self.payload, "hook_event_name": "PostToolUseFailure"},
                        {**self.payload, "is_interrupt": True},
                        {**self.payload, "tool_response": "x" * sampler.INPUT_LIMIT}):
            self.run_hook(invalid)
        self.assertFalse(self.samples.exists())

    def test_bounded_decimal_conversion(self):
        digits = b"1" + b"0" * 500000
        self.config.write_bytes(b'{"ignored":' + digits + b'}')
        self.run_hook(b'{"hook_event_name":"PostToolUse","tool_name":"Bash","duration_ms":' + digits + b'}')
        self.assertEqual(self.log().read_bytes().split(b"\t")[3], b"")

    def test_stalled_input_exits_silently(self):
        with subprocess.Popen(self.command, env=self.env, stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
            try:
                self.assertEqual(process.wait(timeout=2), 0)
                self.assertEqual((process.stdout.read(), process.stderr.read()), (b"", b""))
            finally:
                if process.poll() is None:
                    process.kill()
        self.assertFalse(self.samples.exists())

    def test_private_files_and_busy_lock(self):
        self.run_hook()
        path = self.log()
        lock = self.samples / sampler.LOCK_NAME
        for entry, mode in ((self.samples, 0o700), (lock, 0o600), (path, 0o600)):
            self.assertEqual(stat.S_IMODE(entry.stat().st_mode), mode)
        original = path.read_bytes()
        with lock.open("r+b") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            self.run_hook()
        self.assertEqual(path.read_bytes(), original)

    def test_competing_writers_respect_exact_cap(self):
        self.run_hook()
        path = self.log()
        row = path.read_bytes()
        with path.open("r+b") as stream:
            stream.truncate(sampler.DAY_LIMIT - len(row))

        def attempt(_):
            try:
                sampler.append(self.samples, path.stem, row, time.monotonic() + 2)
            except OSError as error:
                self.assertIn(error.errno, (errno.EAGAIN, errno.EACCES))

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(attempt, range(16)))
        self.assertEqual(path.stat().st_size, sampler.DAY_LIMIT)
        with path.open("rb") as stream:
            stream.seek(-len(row), os.SEEK_END)
            self.assertEqual(stream.read(), row)

    def test_replaced_lock_cannot_authorize_a_competing_append(self):
        self.run_hook()
        path = self.log()
        row = path.read_bytes()
        lock = self.samples / sampler.LOCK_NAME

        def replace_lock():
            lock.unlink()
            lock.touch(mode=0o600)

        open_fd, write = os.open, os.write

        def replace_on_open(name, *args, **kwargs):
            if name == path.name:
                replace_lock()
            return open_fd(name, *args, **kwargs)

        with patch.object(os, "open", side_effect=replace_on_open), self.assertRaises(PermissionError):
            sampler.append(self.samples, path.stem, row, time.monotonic() + 2)
        self.assertEqual(path.read_bytes(), row)

        def replace_on_write(fd, data):
            replace_lock()
            with self.assertRaises(BlockingIOError):
                sampler.append(self.samples, path.stem, row, time.monotonic() + 2)
            return write(fd, data)

        with patch.object(os, "write", side_effect=replace_on_write):
            sampler.append(self.samples, path.stem, row, time.monotonic() + 2)
        self.assertEqual(path.read_bytes(), row * 2)

    def test_partial_write_rolls_back_without_retry(self):
        self.run_hook()
        path = self.log()
        row = path.read_bytes()
        write = os.write
        with patch.object(os, "write", side_effect=lambda fd, data: write(fd, data[:5])) as short:
            sampler.append(self.samples, path.stem, row, time.monotonic() + 2)
        short.assert_called_once()
        self.assertEqual(path.read_bytes(), row)

    def test_refuses_symlinked_ancestors_lock_and_log(self):
        self.run_hook()
        log = self.log()
        original = log.read_bytes()
        for entry in (self.samples.parent, self.samples, self.samples / sampler.LOCK_NAME, log):
            with self.subTest(entry=entry.name):
                target = entry.with_name(entry.name + ".target")
                entry.rename(target)
                entry.symlink_to(target, target_is_directory=target.is_dir())
                self.run_hook()
                self.assertTrue(entry.is_symlink())
                self.assertEqual(log.read_bytes(), original)
                entry.unlink()
                target.rename(entry)

    def test_refuses_public_and_hardlinked_storage(self):
        self.run_hook()
        path = self.log()
        original = path.read_bytes()
        path.chmod(0o644)
        self.run_hook()
        self.assertEqual(path.read_bytes(), original)
        path.chmod(0o600)
        alias = path.with_suffix(".target")
        os.link(path, alias)
        self.run_hook()
        self.assertEqual(alias.read_bytes(), original)
