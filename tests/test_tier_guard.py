"""Exercise the opt-in Agent hook with real processes and private state."""
import copy
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/hooks/pretooluse_agent.json"
HOOK = ROOT / "hooks/tier-guard.sh"
RULE = {"pattern": "<agent *", "freeSpawns": 1, "reasonRegex": r"^Tier reason: audit\b"}


@unittest.skipUnless(shutil.which("jq"), "jq is required")
class TierGuardTests(unittest.TestCase):
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
        (lock / str(dead.pid)).touch()
        with ThreadPoolExecutor(max_workers=12) as pool:
            outcomes = list(pool.map(lambda _: bool(self.call()), range(12)))
        self.assertEqual(sum(outcomes), 8)
        self.assertEqual((self.state / (self.key + ".count")).read_text(), "4\n")
        self.assertFalse(lock.exists())

    def test_live_lock_times_out_and_allows(self):
        self.configure({**RULE, "freeSpawns": 0})
        lock = self.lock()
        owner = lock / str(os.getpid())
        owner.touch()
        self.assertFalse(self.call())
        self.assertTrue(owner.exists())
        owner.unlink()
        self.assertTrue(self.call())  # A crash during cleanup can leave an empty lock.
