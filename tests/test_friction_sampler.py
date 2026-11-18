"""Offline contracts for the unregistered Bash timing sampler."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import errno
import fcntl
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
from threading import Barrier, Event, local
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
        worker = self.root / "kaizen_friction_sample.py"
        shutil.copyfile(SCRIPTS / worker.name, worker)
        self.command = [sys.executable, str(worker)]
        self.payload = dict(hook_event_name="PostToolUse", tool_name="Bash",
                            session_id="session-1", tool_use_id="tool_1", duration_ms=1234.9,
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

    def sample_event(self, deadline=None):
        with tempfile.TemporaryFile() as stream:
            stream.write(json.dumps(self.payload).encode())
            stream.seek(0)
            sampler.sample(stream.fileno(), deadline)

    def process_rows(self):
        return [line for path in sorted(self.samples.glob("*.tsv"))
                for line in path.read_bytes().splitlines() if line.startswith(b"P\t")]

    def test_process_claim_releases_lock_and_survives_utc_rollover(self):
        ms = 1735775999999
        elapsed = sampler.PROCESS_INTERVAL_NS
        started, release = Event(), Event()

        def query(_deadline):
            started.set()
            self.assertTrue(release.wait(2))
            return b"1 mds\n"

        with patch.dict(os.environ, self.env, clear=True), \
                patch.object(sampler, "metrics", return_value=("4", "4")), \
                patch.object(time, "time_ns", side_effect=lambda: ms * 1_000_000), \
                patch.object(time, "clock_gettime_ns", side_effect=lambda _: elapsed), \
                patch.object(sampler, "boot_identity", return_value=b"a" * 16), \
                patch.object(sampler, "query_processes", side_effect=query) as poll:
            with ThreadPoolExecutor(max_workers=2) as pool:
                future = pool.submit(self.sample_event, time.monotonic() + 2)
                try:
                    self.assertTrue(started.wait(1))
                    ms += 1  # A competing claim crosses midnight while the winner polls.
                    pool.submit(self.sample_event).result(timeout=1)
                    self.assertEqual(len((self.samples / "2025-01-02.tsv").read_bytes().splitlines()), 1)
                    poll.assert_called_once()
                finally:
                    release.set()
                future.result()
            ms += 600_000  # A forward wall-clock adjustment cannot renew the claim.
            elapsed += sampler.PROCESS_INTERVAL_NS - 1
            self.sample_event()
            poll.assert_called_once()
            ms -= 300_001
            elapsed += 1
            self.sample_event()
            self.assertEqual(poll.call_count, 2)
            with patch.object(sampler, "metrics", return_value=("3.99", "4")):
                elapsed += sampler.PROCESS_INTERVAL_NS
                self.sample_event()
                self.assertEqual(poll.call_count, 2)
        self.assertEqual(self.process_rows(), [b"P\t1735775999999\t4\t4\tmds",
                                               b"P\t1735776299999\t4\t4\tmds"])

    def test_unknown_boot_identity_still_rate_limits(self):
        self.samples.mkdir(parents=True)
        lock = os.open(self.samples / sampler.LOCK_NAME, os.O_CREAT | os.O_RDWR, 0o600)
        self.addCleanup(os.close, lock)
        with patch.object(time, "clock_gettime_ns", return_value=123), \
                patch.object(sampler, "boot_identity", return_value=None):
            self.assertTrue(sampler.claim_process(lock))
            self.assertFalse(sampler.claim_process(lock))

    def test_claim_changes_with_boot_identity(self):
        self.samples.mkdir(parents=True)
        lock = os.open(self.samples / sampler.LOCK_NAME, os.O_CREAT | os.O_RDWR, 0o600)
        self.addCleanup(os.close, lock)
        with patch.object(time, "clock_gettime_ns", return_value=123), \
                patch.object(sampler, "boot_identity", side_effect=[b"a" * 16, b"a" * 16, b"b" * 16]):
            self.assertTrue(sampler.claim_process(lock))
            self.assertFalse(sampler.claim_process(lock))
            self.assertTrue(sampler.claim_process(lock))

    def test_no_claim_when_file_full_or_query_budget_short(self):
        for remaining, budget in ((2, 1), (100, 0.001)):
            with self.subTest(remaining=remaining, budget=budget):
                with patch.object(sampler, "DAY_LIMIT", 128), \
                        patch.object(sampler, "boot_identity", return_value=b"a" * 16):
                    day = "2025-01-01"
                    initial = b"x" * (127 - remaining) + b"\n"
                    sampler.append(self.samples, day, initial, time.monotonic() + 1)
                    self.assertFalse(sampler.append(self.samples, day, b"x\n", time.monotonic() + budget, True))
                    lock = self.samples / sampler.LOCK_NAME
                    self.assertEqual(lock.read_bytes(), b"")
                    (self.samples / (day + ".tsv")).unlink()

    def test_process_append_rechecks_cap_after_query(self):
        def query(_deadline):
            # Simulate a timing writer consuming the capacity while the lock is released.
            path = self.log()
            remaining = sampler.DAY_LIMIT - path.stat().st_size
            sampler.append(self.samples, path.stem, b"x" * (remaining - 1) + b"\n", time.monotonic() + 1)
            return b"1 mds\n"

        with patch.dict(os.environ, self.env, clear=True), \
                patch.object(sampler, "DAY_LIMIT", 128), \
                patch.object(sampler, "metrics", return_value=("4", "4")), \
                patch.object(sampler, "query_processes", side_effect=query) as poll:
            self.sample_event()
            self.assertEqual(self.log().stat().st_size, sampler.DAY_LIMIT)
            self.assertEqual(self.process_rows(), [])
            poll.assert_called_once()

    def test_copied_worker_resolves_catalogue_and_filters_process_names(self):
        self.command = [sys.executable, "-c",
                        "import sys; import kaizen_friction_sample as s; "
                        "s.metrics = lambda: ('4', '4'); "
                        "s.PROCESS_COMMAND = (sys.executable, '-c', sys.argv[1]); s.main()",
                        "print('99 private-name\\n98 mdworker_private\\n1 mds\\n2 /system bin/mdworker_shared')"]
        self.env["PYTHONPATH"] = str(self.root)
        self.run_hook()
        lock = self.samples / sampler.LOCK_NAME
        lock.write_bytes(b"")
        shutil.copyfile(SCRIPTS / "friction-catalog.json", self.root / "kaizen-friction-catalog.json")
        self.run_hook()
        rows = self.log().read_bytes().splitlines()
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[2].split(b"\t"),
                         [b"P", rows[1].split(b"\t")[0], b"4", b"4", b"mdworker_shared", b"mds"])

    def test_unusable_process_queries_keep_timing_rows(self):
        for code in ("print('1 mds'); raise SystemExit(1)", "print('1 mds\\nbad')",
                     "print('1 mds', end='')", "print('x' * 300000)",
                     "print('99 unknown\\n' * 10 + '1 mds')"):
            with self.subTest(code=code), patch.dict(os.environ, self.env, clear=True), \
                    patch.object(sampler, "PROCESS_COMMAND", (sys.executable, "-c", code)), \
                    patch.object(sampler, "metrics", return_value=("4", "4")):
                self.sample_event()
                self.assertEqual(self.process_rows(), [])
                (self.samples / sampler.LOCK_NAME).write_bytes(b"")
        self.assertEqual(len(self.log().read_bytes().splitlines()), 5)

    def test_timed_out_or_cancelled_query_is_killed_and_reaped(self):
        pid_file = self.root / "query-pid"
        for cancel in (False, True):
            with self.subTest(cancel=cancel):
                query = ("import signal, time; "
                         "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                         "time.sleep(3)")
                # The query can be killed before it publishes its own PID. Record
                # the spawn result in the parent, where cancellation only sets a flag.
                worker = """
import os
from pathlib import Path
import signal
import sys
import time
import kaizen_friction_sample as s

s.metrics = lambda: ('4', '4')
s.PROCESS_COMMAND = (sys.executable, '-c', sys.argv[1])
spawn = os.posix_spawn
def record_spawn(*args, **kwargs):
    pid = spawn(*args, **kwargs)
    Path(sys.argv[2]).write_text(str(pid))
    if sys.argv[3] == 'True':
        os.kill(os.getpid(), signal.SIGTERM)
    return pid
s.os.posix_spawn = record_spawn
start = time.monotonic()
s.main()
assert time.monotonic() - start < s.BUDGET + 0.1
"""
                self.command = [sys.executable, "-c",
                                worker, query, str(pid_file), str(cancel)]
                self.run_hook(PYTHONPATH=str(SCRIPTS))
                with self.assertRaises(ProcessLookupError):
                    os.kill(int(pid_file.read_text()), 0)
                pid_file.unlink()
                self.assertEqual(self.process_rows(), [])
                (self.samples / sampler.LOCK_NAME).write_bytes(b"")

    def test_layout_privacy_and_optional_values(self):
        start = time.time_ns() // 1_000_000
        self.run_hook({**self.payload, "tool_response": "omit output" * 85000})
        path = self.log()
        row = path.read_bytes()
        ms, session, tool, duration, load, cores = row.decode().rstrip("\n").split("\t")
        self.assertGreaterEqual(int(ms), start)
        self.assertEqual(path.stem, datetime.fromtimestamp(int(ms) // 1000, timezone.utc).date().isoformat())
        self.assertEqual((session, tool, duration), ("session-1", "tool_1", "1234"))
        self.assertGreaterEqual(float(load), 0)
        self.assertGreater(int(cores), 0)
        self.assertLess(len(row), 4096)
        self.assertNotIn(b"omit", row)
        for optional in ({}, {"duration_ms": True}, {"duration_ms": -1},
                         {"duration_ms": float("inf")}, {"duration_ms": float("nan")},
                         {"session_id": "a" * 1024, "tool_use_id": 42}):
            self.run_hook({"hook_event_name": "PostToolUse", "tool_name": "Bash", **optional})
        rows = [line.split("\t") for line in path.read_text().splitlines()[1:]]
        self.assertEqual([row[1:4] for row in rows], [["", "", ""]] * 6)

    def test_malformed_ids_are_blank_without_rewriting(self):
        for value in ("/path/fragment", "command; argument", "tool\n", "ábc", "a" * 65):
            self.run_hook({**self.payload, "session_id": value, "tool_use_id": "a" * 64})
        rows = self.log().read_text().splitlines()
        self.assertEqual([row.split("\t")[1:3] for row in rows], [["", "a" * 64]] * 5)

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

    def test_slow_io_exits_silently_and_releases_locks(self):
        self.run_hook()
        path = self.log()
        code = r"""
import fcntl
import os
from pathlib import Path
import sys
import time
import kaizen_friction_sample as sampler

path = Path(sys.argv[2])
stamp = int(path.read_bytes().split(b'\t', 1)[0]) * 1_000_000
time.time_ns = lambda: stamp
called = []

def slow_config(*args):
    called.append('config')
    time.sleep(1)
    return True

write = os.write
def slow_write(fd, row):
    called.append('write')
    count = write(fd, row[:5])
    time.sleep(1)
    return count

if sys.argv[1] == 'config':
    sampler.enabled = slow_config
else:
    sampler.os.write = slow_write
start = time.monotonic()
sampler.main()
elapsed = time.monotonic() - start
assert called == [sys.argv[1]], called
assert elapsed <= sampler.BUDGET + 0.100, elapsed
for entry in (path, path.with_name(sampler.LOCK_NAME)):
    with entry.open('rb') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
"""
        for phase in ("config", "write"):
            with self.subTest(phase=phase):
                result = subprocess.run([sys.executable, "-c", code, phase, str(path)],
                                        input=json.dumps(self.payload).encode(), capture_output=True,
                                        env={**self.env, "PYTHONPATH": str(SCRIPTS)}, timeout=3)
                self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b"", b""))

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

    def test_overlapping_writers_respect_exact_cap_across_utc_midnight(self):
        self.payload["session_id"] = "s" * 30

        def attempt(_=None):
            with tempfile.TemporaryFile() as stream:
                stream.write(json.dumps(self.payload).encode())
                stream.seek(0)
                try:
                    sampler.sample(stream.fileno())
                except BlockingIOError as error:
                    self.assertEqual(error.errno, errno.EAGAIN)

        expected = {}
        flock = fcntl.flock
        with patch.dict(os.environ, self.env, clear=True), \
                patch.object(sampler, "metrics", return_value=("1.25", "4")):
            for ms, day in ((1735775999999, "2025-01-01"), (1735776000000, "2025-01-02")):
                with patch.object(time, "time_ns", return_value=ms * 1_000_000):
                    attempt()
                    path = self.samples / (day + ".tsv")
                    row = path.read_bytes()
                    self.assertEqual(row.split(b"\t"), [str(ms).encode(), b"s" * 30, b"tool_1",
                                                        b"1234", b"1.25", b"4\n"])
                    rows_at_cap, leftover = divmod(sampler.DAY_LIMIT, len(row))
                    self.assertEqual(leftover, 0)
                    path.write_bytes(row * (rows_at_cap - 1))
                    with (self.samples / sampler.LOCK_NAME).open("r+b") as held:
                        flock(held, fcntl.LOCK_EX)
                        # Every writer must hit the held lock before any can retry.
                        overlap = Barrier(8, action=lambda: flock(held, fcntl.LOCK_UN), timeout=2)
                        contenders = local()

                        def synchronize_flock(fd, operation):
                            try:
                                return flock(fd, operation)
                            except BlockingIOError:
                                if not getattr(contenders, "waited", False):
                                    contenders.waited = True
                                    overlap.wait()
                                raise

                        with patch.object(fcntl, "flock", side_effect=synchronize_flock):
                            with ThreadPoolExecutor(max_workers=8) as pool:
                                list(pool.map(attempt, range(8)))
                    expected[path] = row * rows_at_cap
        self.assertEqual(set(self.samples.glob("*.tsv")), set(expected))
        for path, contents in expected.items():
            self.assertEqual(path.stat().st_size, sampler.DAY_LIMIT)
            self.assertTrue(path.read_bytes() == contents, path.name)

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

    def test_append_repairs_preexisting_torn_tail(self):
        self.run_hook()
        path = self.log()
        row = path.read_bytes()
        for prefix in (row, b""):
            with self.subTest(has_complete_row=bool(prefix)):
                path.write_bytes(prefix + row[:5])
                sampler.append(self.samples, path.stem, row, time.monotonic() + 2)
                self.assertEqual(path.read_bytes(), prefix + row)

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

    def test_darwin_refuses_extended_acls_on_store_and_day_file(self):
        self.run_hook()
        path = self.log()
        original = path.read_bytes()
        stamp = int(original.split(b"\t", 1)[0]) * 1_000_000
        for entry in (self.samples, path):
            with self.subTest(entry=entry.name), tempfile.TemporaryFile() as stream:
                identity = entry.stat()
                stream.write(json.dumps(self.payload).encode())
                stream.seek(0)
                with patch.dict(os.environ, self.env, clear=True), patch.object(sys, "stdin", stream), \
                        patch.object(sys, "platform", "darwin"), patch.object(time, "time_ns", return_value=stamp), \
                        patch.object(sampler, "has_extended_acl", create=True,
                                     side_effect=lambda fd: os.path.samestat(os.fstat(fd), identity)):
                    sampler.main()
                self.assertEqual(path.read_bytes(), original)
