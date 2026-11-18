"""Clean Git capture and ordinary manifest handoff for local backup commits."""
import datetime
import hashlib
import json
import os
import runpy
import shlex
import shutil
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
        self.git("init", "-q", "--object-format=sha1")
        self.target = self.repo / "tracked"
        self.target.write_text("before")
        self.git("add", ".")
        self.git("-c", "user.name=Test", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "initial")
        with patch.dict(os.environ, self.env, clear=True):
            helpers = runpy.run_path(str(SCRIPT))
        self.capture, self.handoff = helpers["capture_git_baseline"], helpers["validate_change_handoff"]
        self.helpers = self.capture.__globals__

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.repo, env=self.env, text=True).strip()

    def script(self, *args):
        return subprocess.check_output([sys.executable, str(SCRIPT), *map(str, args)],
                                       env=self.env, cwd=self.repo, text=True, timeout=10).strip()

    def begin(self, *args):
        return Path(self.script("begin", "--skill", "trim", "--ledger", "fixture", *args, self.target))

    def manifest(self, change):
        return json.loads((change / "manifest.json").read_text())

    def test_capture_and_first_interactive_begin(self):
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
        self.assertIsNone(self.manifest(self.begin("--run", "one", "--repo", "."))["git"])

    def test_forged_manifest_cannot_authorize_dirty_run(self):
        stamp = self.capture(self.repo)
        self.target.write_text("dirty")
        first = self.begin("--run", "dirty", "--repo", ".")
        data = self.manifest(first)
        self.assertIsNone(data["git"])
        (first / "manifest.json").write_text(json.dumps(dict(data, git=stamp)))
        self.assertIsNone(self.manifest(self.begin("--run", "dirty", "--repo", "."))["git"])

    def test_filter_added_during_capture_never_executes(self):
        marker = self.tmp / "filter-ran"
        (self.repo / ".git" / "info" / "attributes").write_text("tracked filter=late\n")
        git = self.helpers["git"]
        injected = False

        def configure_late(directory, *args, **kwargs):
            nonlocal injected
            result = git(directory, *args, **kwargs)
            if "--name-only" in args or "--others" in args:
                self.git("config", "filter.late.clean", f"touch {shlex.quote(str(marker))}; cat")
                later = self.target.stat().st_mtime + 2
                os.utime(self.target, (later, later))
                injected = True
            return result

        with patch.dict(self.helpers, git=configure_late):
            stamp = self.capture(self.repo)
        self.assertTrue(injected)
        self.assertFalse(marker.exists())
        self.assertIsNotNone(stamp)

    def test_forged_index_stat_cannot_hide_dirty_content(self):
        before = bytes.fromhex(self.git("rev-parse", "HEAD:tracked"))
        self.target.write_text("edited")
        self.git("add", "tracked")
        after = bytes.fromhex(self.git("rev-parse", ":tracked"))
        index = self.repo / ".git" / "index"
        raw = index.read_bytes()[:-20].replace(after, before, 1)
        index.write_bytes(raw + hashlib.sha1(raw).digest())
        later = self.target.stat().st_mtime + 2
        os.utime(index, (later, later))
        self.assertEqual(self.git("rev-parse", ":tracked"), before.hex())
        self.assertIsNone(self.capture(self.repo))

    def test_index_fifo_and_oversize_are_refused(self):
        index = self.repo / ".git" / "index"
        index.unlink()
        os.mkfifo(index)
        self.assertIsNone(self.manifest(self.begin("--run", "fifo", "--repo", "."))["git"])
        index.unlink()
        with index.open("wb") as stream:
            stream.truncate(64 * 1024 * 1024 + 1)
        with patch.object(Path, "read_bytes", side_effect=AssertionError("read oversized index")):
            self.assertIsNone(self.capture(self.repo))

    def test_repo_subdirectory_is_refused(self):
        nested = self.repo / "nested"
        nested.mkdir()
        self.assertIsNone(self.capture(nested))

    def test_replaced_linked_worktree_is_refused(self):
        tree = self.tmp / "linked"
        self.git("worktree", "add", "-qb", "linked", str(tree))
        git = self.helpers["git"]
        moved = tree.with_name("original")

        def replace_tree(directory, *args, **kwargs):
            result = git(directory, *args, **kwargs)
            if args[0] == "ls-files" and "--stage" in args:
                tree.rename(moved)
                shutil.copytree(moved, tree)
            return result

        with patch.dict(self.helpers, git=replace_tree):
            self.assertIsNone(self.capture(tree))
        self.assertTrue(moved.is_dir())

    def test_edit_during_copy_revokes_baseline(self):
        copy = shutil.copy2

        def edit_then_copy(source, destination):
            self.target.write_text("concurrent edit")
            return copy(source, destination)

        with patch.dict(os.environ, self.env, clear=True), patch.object(shutil, "copy2", edit_then_copy):
            with patch("sys.stdout"):
                self.assertEqual(self.helpers["main"](
                    ["begin", "--run", "race", "--repo", str(self.repo), "--skill", "trim",
                     "--ledger", "fixture", str(self.target)]), 0)
        change = self.backups / "race-01-trim"
        self.assertIsNone(self.manifest(change)["git"])
        self.assertEqual((change / "files" / "1").read_text(), "concurrent edit")

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
        expected = dict(run_id="scheduled", session_id="session", started=started, before=before,
                        root_identity=self.helpers["backup_root_identity"](self.backups))
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

    def test_handoff_refuses_backup_root_and_manifest_swaps(self):
        self.env.update(KAIZEN_RUN_ID="scheduled", KAIZEN_SESSION_ID="session")
        self.backups.mkdir()
        expected = dict(run_id="scheduled", session_id="session", before=(set(), set()),
                        started=datetime.datetime.now(datetime.timezone.utc),
                        root_identity=self.helpers["backup_root_identity"](self.backups))
        change = self.begin()
        manifest = change / "manifest.json"
        replacement = shutil.copy2(manifest, change / "replacement.json")
        loads = json.loads

        def replace_manifest(raw):
            Path(replacement).replace(manifest)
            return loads(raw)

        with self.subTest(swap="manifest"), patch.object(json, "loads", replace_manifest):
            with self.assertRaisesRegex(ValueError, "manifest was replaced"):
                self.handoff(self.backups, change, **expected)
        original = self.backups.rename(self.tmp / "original")
        shutil.copytree(original, self.backups)
        with self.subTest(swap="directory"), self.assertRaisesRegex(ValueError, "backup root"):
            self.handoff(self.backups, change, **expected)
        shutil.rmtree(self.backups)
        self.backups.symlink_to(original, target_is_directory=True)
        with self.subTest(swap="symlink"), self.assertRaisesRegex(ValueError, "backup root"):
            self.handoff(self.backups, original / change.name, **expected)
