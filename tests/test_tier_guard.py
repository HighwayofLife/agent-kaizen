"""Exercise the opt-in Agent hook with real processes and private state."""
import copy
import hashlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/hooks/pretooluse_agent.json"
HOOK = ROOT / "hooks/tier-guard.sh"
RULE = {"pattern": "<agent *", "freeSpawns": 1, "reasonRegex": r"^Tier reason: audit\b"}


@unittest.skipUnless(shutil.which("jq"), "jq is required")
class TierGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Load the embedded Python for deterministic fault and race injection.
        embedded = HOOK.read_text().split("<<'PY'", 1)[1]
        source = embedded.split("\n", 1)[1].split("\nPY\n", 1)[0]
        cls.script = {"__name__": "tier_guard"}
        exec(compile(source, str(HOOK), "exec"), cls.script)

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.config = Path(tmp.name)
        self.state = self.config / "kaizen-tier-guard"
        self.event = json.loads(FIXTURE.read_text())
        self.key = hashlib.sha256(json.dumps([self.event["session_id"], RULE["pattern"]]).encode()).hexdigest()
        self.configure(RULE)

    def configure(self, *rules):
        (self.config / "agent-kaizen.json").write_text(json.dumps({"guardrails": {"agentTiers": rules}}))

    def lock(self):
        self.state.mkdir(mode=0o700)
        lock = self.state / (self.key + ".lock")
        lock.mkdir(mode=0o700)
        return lock

    def run_guard(self, output):
        previous_umask = os.umask(0o077)
        try:
            with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(self.config)}), redirect_stdout(output):
                self.script["guard"](self.event)
        finally:
            os.umask(previous_umask)

    def call(self, event=None, **env):
        data = self.event if event is None else event
        result = subprocess.run(["/bin/bash", str(HOOK)], text=True, capture_output=True, timeout=5,
                                input=data if isinstance(data, str) else json.dumps(data),
                                env={**os.environ, "CLAUDE_CONFIG_DIR": str(self.config), **env})
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        if result.stdout:
            output = json.loads(result.stdout)["hookSpecificOutput"]
            self.assertEqual((output["hookEventName"], output["permissionDecision"]), ("PreToolUse", "deny"))
            self.assertIn("Tier reason: <why>", output["permissionDecisionReason"])
        return result.stdout

    def test_fixture_first_match_and_override(self):
        self.configure(RULE, {**RULE, "pattern": "*", "freeSpawns": 5})
        self.assertFalse(self.call())
        del self.event["tool_input"]["model"]
        self.assertTrue(self.call())
        self.event["tool_input"]["prompt"] += "\nTier reason:   "
        self.assertTrue(self.call())
        self.event["tool_input"]["prompt"] += "\nTier reason: audit ownership"
        self.assertFalse(self.call())
        log, = self.state.glob("*.reasons.jsonl")
        row = json.loads(log.read_text())
        self.assertEqual(row, {"timestamp": row["timestamp"], "rule": RULE["pattern"], "reason": "audit ownership"})
        self.assertRegex(row["timestamp"], r"^\d{4}-\d{2}-\d{2}T")
        self.assertEqual(log.stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.state / (self.key + ".count")).read_text(), "2\n")
        self.assertEqual(self.state.stat().st_mode & 0o777, 0o700)
        self.event["tool_input"]["prompt"] = "Another task"
        self.assertFalse(self.call({**self.event, "session_id": "new-session"}))
        self.event["tool_input"]["subagent_type"] = "other-agent"
        self.assertFalse(self.call())

    def test_invalid_or_ineligible_input_is_silent(self):
        for field, value in (("tool_name", "Read"), ("session_id", ""), ("hook_event_name", "PostToolUse")):
            self.assertFalse(self.call({**self.event, field: value}))
        for field, value in (("subagent_type", "unmatched"), ("prompt", None)):
            event = copy.deepcopy(self.event)
            event["tool_input"][field] = value
            self.assertFalse(self.call(event))
        self.assertFalse(self.call("{"))
        self.assertFalse(self.call(PATH=str(self.config)))
        for bad in ({**RULE, "freeSpawns": True}, {**RULE, "reasonRegex": "["}, {"pattern": "*"}):
            self.configure({**RULE, "freeSpawns": 0}, bad)
            self.assertFalse(self.call())
        (self.config / "agent-kaizen.json").write_text("{")
        self.assertFalse(self.call())
        self.assertFalse(self.state.exists())

    def test_state_errors_allow(self):
        self.assertFalse(self.call())
        count = self.state / (self.key + ".count")
        count.write_text("invalid")
        self.assertFalse(self.call())
        count.write_text("1\n")
        (self.state / (self.key + ".reasons.jsonl")).mkdir(mode=0o700)
        self.event["tool_input"]["prompt"] += "\nTier reason: audit ownership"
        self.assertFalse(self.call())
        self.assertEqual(count.read_text(), "1\n")
        self.state.chmod(0o755)
        self.assertFalse(self.call())
        self.state.rename(self.config / "moved")
        self.state.symlink_to(self.config / "moved")
        self.assertFalse(self.call())

    def test_parallel_requests_and_stale_lock(self):
        self.configure({**RULE, "freeSpawns": 4})
        lock = self.lock()
        with subprocess.Popen(["/usr/bin/true"]) as dead:
            dead.wait()
        (lock / str(dead.pid)).touch(mode=0o600)
        with ThreadPoolExecutor(max_workers=12) as pool:
            outcomes = list(pool.map(lambda _: bool(self.call()), range(12)))
        denied = sum(outcomes)
        self.assertGreaterEqual(12 - denied, 4)
        self.assertGreaterEqual(denied, 1)
        self.assertLessEqual(denied, 8)
        self.assertEqual(len(outcomes), 12)
        self.assertEqual((self.state / (self.key + ".count")).read_text(), "4\n")
        self.assertFalse(lock.exists())

    def test_live_lock_times_out_and_allows(self):
        self.configure({**RULE, "freeSpawns": 0})
        lock = self.lock()
        owner = lock / str(os.getpid())
        owner.touch(mode=0o600)
        owner.write_bytes(self.script["process_identity"](os.getpid()))
        old = time.time() - 31
        os.utime(owner, (old, old))
        self.assertFalse(self.call())
        self.assertTrue(owner.exists())
        owner.unlink()
        self.assertTrue(self.call())  # A crash during cleanup can leave an empty lock.

    def test_matching_reason_line_is_logged(self):
        self.configure({**RULE, "freeSpawns": 0})
        self.event["tool_input"]["prompt"] = "Tier reason: foo\nTier reason: audit ownership"
        self.assertFalse(self.call())
        log, = self.state.glob("*.reasons.jsonl")
        self.assertEqual(json.loads(log.read_text())["reason"], "audit ownership")

    def test_long_reason_is_truncated(self):
        self.configure({**RULE, "freeSpawns": 0})
        reason = "audit " + "x" * 250
        self.event["tool_input"]["prompt"] = "Tier reason: " + reason
        self.assertFalse(self.call())
        log, = self.state.glob("*.reasons.jsonl")
        self.assertEqual(json.loads(log.read_text())["reason"], reason[:199] + "…")

    def test_old_state_is_pruned(self):
        self.state.mkdir(mode=0o700)
        paths = [self.state / name for name in ("old.count", "old.reasons.jsonl", "recent.count", "old.other")]
        for path in paths:
            path.touch(mode=0o600)
        old = time.time() - 31 * 86400
        for path in (paths[0], paths[1], paths[3]):
            os.utime(path, (old, old))
        self.assertFalse(self.call())
        self.assertEqual([p.exists() for p in paths], [False, False, True, True])

    def test_prune_skips_a_locked_key(self):
        lock = self.lock()
        owner = lock / str(os.getpid())
        owner.touch(mode=0o600)
        counter = self.state / (self.key + ".count")
        counter.touch(mode=0o600)
        old = time.time() - 31 * 86400
        os.utime(counter, (old, old))
        other = {**self.event, "session_id": "other-session"}

        self.assertFalse(self.call(other))
        self.assertTrue(counter.exists())
        owner.unlink()
        self.assertTrue(self.call(other))
        self.assertFalse(counter.exists())

    def test_deny_includes_rule_and_regex(self):
        self.configure({**RULE, "freeSpawns": 0})
        output = json.loads(self.call())["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn(RULE["pattern"], output)
        self.assertIn(RULE["reasonRegex"], output)

    def test_deny_escapes_control_characters_in_regex(self):
        self.configure({**RULE, "freeSpawns": 0, "reasonRegex": "^Tier reason: audit\x00\townership$"})
        output = json.loads(self.call())["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn(r"^Tier reason: audit\x00\townership$", output)
        self.assertNotIn("\x00", output)
        self.assertNotIn("\t", output)
        self.event["tool_input"]["prompt"] = "Tier reason: audit\x00\townership"
        self.assertFalse(self.call())

    def test_live_pid_with_mismatched_identity_is_stale(self):
        self.configure({**RULE, "freeSpawns": 0})
        lock = self.lock()
        owner = lock / str(os.getpid())
        owner.touch(mode=0o600)
        owner.write_text(hashlib.sha256(b"different process start").hexdigest())
        self.assertTrue(self.call())
        self.assertFalse(lock.exists())

    def test_prune_rechecks_other_keys_fresh_counter(self):
        self.configure({**RULE, "freeSpawns": 2})
        self.state.mkdir(mode=0o700)
        other = {**self.event, "session_id": "other-session"}
        other_key = hashlib.sha256(json.dumps([other["session_id"], RULE["pattern"]]).encode()).hexdigest()
        counter = self.state / (other_key + ".count")
        counter.touch(mode=0o600)
        counter.write_text("1\n")
        old = time.time() - 31 * 86400
        os.utime(counter, (old, old))
        lstat = Path.lstat

        def replace_after_stat(path):
            info = lstat(path)
            if path == counter and time.time() - info.st_mtime > 30 * 86400:
                # The expired count is ignored, so this request restarts it at 1.
                self.assertFalse(self.call(other))
                self.assertEqual(counter.read_text(), "1\n")
            return info

        with mock.patch.object(Path, "lstat", replace_after_stat):
            self.run_guard(io.StringIO())
        # The prune saw the old age but rechecked under the key lock and kept it.
        self.assertEqual(counter.read_text(), "1\n")
        self.assertFalse(self.call(other))
        self.assertTrue(self.call(other))

    def test_expired_counter_does_not_deny(self):
        self.configure({**RULE, "freeSpawns": 1})
        self.state.mkdir(mode=0o700)
        counter = self.state / (self.key + ".count")
        counter.touch(mode=0o600)
        counter.write_text("5\n")
        old = time.time() - 31 * 86400
        os.utime(counter, (old, old))
        self.assertFalse(self.call())
        self.assertEqual(counter.read_text(), "1\n")
        self.assertTrue(self.call())

    def test_prune_error_preserves_allow_and_deny(self):
        counter = self.state / (self.key + ".count")
        for free in (0, 1):
            with self.subTest(free=free):
                self.configure({**RULE, "freeSpawns": free})
                baseline = io.StringIO()
                self.run_guard(baseline)
                self.assertEqual(bool(baseline.getvalue()), free == 0)
                counter.unlink(missing_ok=True)
                output = io.StringIO()

                def fail_scan(path):
                    self.assertEqual(path, self.state)
                    self.assertEqual(output.getvalue(), baseline.getvalue())
                    if free:
                        self.assertEqual(counter.read_text(), "1\n")
                    raise PermissionError("injected prune error")

                with mock.patch("os.scandir", side_effect=fail_scan) as scan:
                    self.run_guard(output)
                scan.assert_called_once_with(self.state)
                self.assertEqual(output.getvalue(), baseline.getvalue())
