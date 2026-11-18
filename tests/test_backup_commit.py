"""Clean Git capture and ordinary manifest handoff for local backup commits."""
import datetime
import json
import os
import runpy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "kaizen-backup"


class BackupCommitTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.tmp = Path(temp.name).resolve()
        self.repo, self.backups = self.tmp / "repo", self.tmp / "backups"
        self.repo.mkdir()
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith(("GIT_", "KAIZEN_"))}
        self.env.update(HOME=str(self.tmp), XDG_CONFIG_HOME=str(self.tmp),
                        KAIZEN_BACKUP_DIR=str(self.backups))
        self.git("init", "-q")
        self.target = self.repo / "tracked"
        self.target.write_text("before")
        self.git("add", ".")
        self.git("-c", "user.name=Test", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "initial")
        with patch.dict(os.environ, self.env, clear=True):
            helpers = runpy.run_path(str(SCRIPT))
        self.capture, self.handoff = helpers["capture_git_baseline"], helpers["validate_change_handoff"]

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.repo, env=self.env, text=True).strip()

    def script(self, *args):
        return subprocess.check_output([sys.executable, str(SCRIPT), *map(str, args)],
                                       env=self.env, cwd=self.repo, text=True).strip()

    def begin(self, *args):
        return Path(self.script("begin", "--skill", "trim", "--ledger", "fixture", *args, self.target))

    def manifest(self, change):
        return json.loads((change / "manifest.json").read_text())

    def test_capture_and_interactive_inheritance(self):
        tree = self.tmp / "linked"
        self.git("worktree", "add", "-qb", "linked", str(tree))
        index = self.repo / ".git" / "index"
        before = index.stat().st_mtime_ns
        with patch.dict(os.environ, dict(self.env, GIT_DIR=str(tree / ".git"),
                                        GIT_INDEX_FILE=str(self.tmp / "foreign")), clear=True):
            stamp = self.capture(self.repo)
            linked = self.capture(tree)
        self.assertEqual(stamp["root"], str(self.repo))
        self.assertEqual(stamp["head"], self.git("rev-parse", "HEAD"))
        self.assertEqual(stamp["common_dir"], linked["common_dir"])
        self.assertNotEqual(stamp["index"], linked["index"])
        self.assertEqual(index.stat().st_mtime_ns, before)
        self.assertEqual(self.manifest(self.begin("--run", "one", "--repo", "."))["git"], stamp)
        self.target.write_text("edited")
        self.assertEqual(self.manifest(self.begin("--run", "one", "--repo", "."))["git"], stamp)
        self.assertIsNone(self.manifest(self.begin("--run", "one", "--repo", tree))["git"])
        self.git("-c", "user.name=Test", "-c", "user.email=fixture@example.invalid", "commit", "-qam", "advance")
        self.assertIsNone(self.manifest(self.begin("--run", "one", "--repo", "."))["git"])

    def test_dirty_or_hidden_start_still_backs_up_without_authority(self):
        def check(run):
            change = self.begin("--run", run, "--repo", ".")
            self.assertIsNone(self.manifest(change)["git"])
            self.assertEqual((change / "files" / "1").read_text(), self.target.read_text())

        self.target.write_text("dirty")
        check("dirty")
        self.git("restore", "tracked")
        check("dirty")  # This run cannot acquire a new baseline after its first backup.
        self.git("config", "core.filemode", "false")
        self.target.chmod(0o755)
        check("chmod")
        self.target.chmod(0o644)
        (self.repo / ".git" / "info" / "exclude").write_text("ignored\n")
        for name in ("untracked", "ignored"):
            path = self.repo / name
            path.touch()
            check(name)
            path.unlink()
        for flag in ("assume-unchanged", "skip-worktree"):
            self.git("update-index", "--" + flag, "tracked")
            check(flag)
            self.git("update-index", "--no-" + flag, "tracked")
        self.assertIsNone(self.manifest(self.begin("--run", "non-git", "--repo", self.tmp))["git"])

    def test_scheduled_handoff_requires_new_matching_ordinary_manifest(self):
        self.env.update(KAIZEN_RUN_ID="scheduled", KAIZEN_SESSION_ID="session")
        old = self.begin()
        old_info = old.stat()
        started = datetime.datetime.now(datetime.timezone.utc)
        before = ({old}, {(old_info.st_dev, old_info.st_ino)})
        change = self.begin()
        self.target.write_text("after")
        self.script("finish", change)
        expected = dict(run_id="scheduled", session_id="session", started=started, before=before)
        data, identity = self.handoff(self.backups, change, **expected)
        self.assertTrue(data["finished"])
        self.assertEqual(identity, (change.stat().st_dev, change.stat().st_ino))
        self.assertNotIn("git", data)
        for path, overrides in ((old, {}), (change, {"session_id": "foreign"}),
                                (self.begin("--run", "foreign"), {}),
                                (self.begin("--repo", "."), {}),
                                (change, {"started": datetime.datetime.now(datetime.timezone.utc)})):
            with self.assertRaises(ValueError):
                self.handoff(self.backups, path, **dict(expected, **overrides))
        renamed = change.rename(change.with_name("scheduled-99-trim"))
        with self.assertRaises(ValueError):
            self.handoff(self.backups, renamed, **expected)
        moved = old.rename(old.with_name("scheduled-01-other"))
        with self.assertRaisesRegex(ValueError, "not new"):
            self.handoff(self.backups, moved, **expected)
