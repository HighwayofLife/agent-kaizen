"""Clean Git capture, manifest handoff and local commit plumbing."""
import base64
import datetime
import errno
import hashlib
import io
import json
import os
import runpy
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
import zlib
from concurrent.futures import ThreadPoolExecutor
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
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "fixture@example.invalid")
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

    def begin_in_process(self, run):
        with patch.dict(os.environ, self.env, clear=True), patch("sys.stdout"):
            self.assertEqual(self.helpers["main"](
                ["begin", "--run", run, "--repo", str(self.repo), "--skill", "trim",
                 "--ledger", "fixture", str(self.target)]), 0)
        return self.backups / f"{run}-01-trim"

    def commit_cli(self, change, baseline=None, *, raw=None, expected=0):
        option = [] if baseline is None and raw is None else ["--scheduled-baseline-stdin"]
        result = subprocess.run([sys.executable, str(SCRIPT), "commit", *option, str(change)],
                                input=raw if raw is not None else json.dumps(baseline),
                                env=self.env, cwd=self.repo, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def main(self, *args, expected=0, **overrides):
        err = io.StringIO()
        with (patch.dict(os.environ, self.env, clear=True), patch.dict(self.helpers, overrides),
              patch("sys.stdout", io.StringIO()), patch("sys.stderr", err)):
            self.assertEqual(self.helpers["main"](list(map(str, args))) or 0, expected, err.getvalue())
        return err.getvalue()

    def ready(self, run="commit"):
        change = self.begin("--run", run, "--repo", ".")
        self.target.write_text("after")
        self.script("finish", change)
        return change

    def test_scheduled_commit_preflight_and_ledger_attestation(self):
        fixture = json.loads(Path(__file__).with_name("fixtures").joinpath("ledger_attestation_v1.json").read_text())
        proof = fixture["valid"]
        ledger = self.repo / proof["ledger_relpath"]
        ledger.parent.mkdir(parents=True)
        ledger.write_bytes(base64.b64decode(proof["before_b64"]))
        self.git("add", ".")
        self.git("-c", "user.name=Test", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "ledger")
        self.env.update(KAIZEN_RUN_ID=proof["run_id"], KAIZEN_SESSION_ID=proof["session_id"])
        old = self.begin("--run", "old")
        old_stat = old.stat()
        scope = dict(v=1, baseline=self.capture(self.repo), run_id=proof["run_id"], session_id=proof["session_id"],
                     started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                     before=[[str(old)], [[old_stat.st_dev, old_stat.st_ino]]],
                     root_identity=self.helpers["backup_root_identity"](self.backups), ledger_attestation=None)
        change = self.begin()
        self.assertNotIn("git", self.manifest(change))
        self.target.write_text("after")
        self.script("finish", change)
        manifest = change / "manifest.json"
        raw = manifest.read_bytes()
        info = change.stat()
        scope.update(change_id=change.name, change_identity=[info.st_dev, info.st_ino],
                     manifest_sha256=hashlib.sha256(raw).hexdigest())
        self.commit_cli(change, scope)
        for override in ({"run_id": "other"}, {"session_id": "other"},
                         {"before": [[str(change)], []]}, {"change_id": old.name},
                         {"baseline": None}, {"manifest_sha256": "0" * 64}):
            self.commit_cli(change, dict(scope, **override), expected=2)
        self.commit_cli(change, {k: v for k, v in scope.items() if k != "session_id"}, expected=2)
        manifest.write_text(json.dumps(dict(self.manifest(change), git=scope["baseline"])))
        self.commit_cli(change, scope, expected=2)
        self.commit_cli(change, expected=2)
        manifest.write_bytes(raw)

        ledger.write_text(fixture["after_utf8"])
        self.commit_cli(change, scope, expected=2)
        attested = dict(scope, ledger_attestation=proof)
        self.commit_cli(change, attested)
        _, _, selected, _ = self.helpers["commit_preflight"](change, attested)
        self.assertEqual(set(selected), {self.target})
        for name, override in fixture["invalid_overrides"].items():
            with self.subTest(case=name):
                self.commit_cli(change, dict(scope, ledger_attestation=dict(proof, **override)), expected=2)
        duplicate = json.dumps(attested).replace('"before_b64":', '"v": 1, "before_b64":')
        self.commit_cli(change, raw=duplicate, expected=2)
        foreign_row = fixture["after_utf8"].replace(change.name, old.name)
        ledger.write_text(foreign_row)
        self.commit_cli(change, dict(scope, ledger_attestation=dict(
            proof, manifest_ids=[old.name], after_sha256=hashlib.sha256(ledger.read_bytes()).hexdigest())), expected=2)
        extra = self.repo / "unapproved"
        sibling = Path(self.script("begin", "--skill", "trim", "--ledger", "fixture", extra))
        extra.touch()
        self.script("finish", sibling)
        ledger.write_text(fixture["after_utf8"] + foreign_row.splitlines()[-1].replace(old.name, sibling.name) + "\n")
        self.commit_cli(change, dict(scope, ledger_attestation=dict(
            proof, manifest_ids=[change.name, sibling.name], after_sha256=hashlib.sha256(ledger.read_bytes()).hexdigest())),
                        expected=2)
        extra.unlink()
        self.assertEqual(self.git("for-each-ref", "refs/kaizen/"), "")
        ledger.write_text(fixture["after_utf8"] + "another line\n")
        self.commit_cli(change, attested, expected=2)
        ledger.write_text(fixture["after_utf8"])
        keyed = dict(attested, action_id="fa1_" + "a" * 64)
        first = self.commit_cli(change, keyed).stdout
        ledger.write_text(fixture["after_utf8"] + "later bookkeeping\n")
        self.assertEqual(self.commit_cli(change, keyed).stdout, first)
        for override in ({"action_id": "fa1_" + "b" * 64}, {"run_id": "other"}):
            self.commit_cli(change, dict(keyed, **override), expected=2)
        self.assertIn("already bound", self.commit_cli(old, keyed, expected=2).stderr)
        self.commit_cli(change, expected=2)
        ledger.write_text(fixture["after_utf8"])
        self.git("add", str(ledger))
        self.commit_cli(change, attested, expected=2)

    def test_local_commit_plumbing_preserves_checkout_index_and_verified_bytes(self):
        index = self.repo / ".git" / "index"
        (self.repo / ".gitattributes").write_text("tracked filter=tripwire\n")
        self.git("add", ".gitattributes")
        self.git("-c", "user.name=Test", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "attributes")
        change = self.begin("--repo", ".")
        self.target.write_text("after")
        self.script("finish", change)
        self.git("config", "filter.tripwire.clean", "exit 1")
        self.git("config", "filter.tripwire.required", "true")
        head, raw_index = self.git("rev-parse", "HEAD"), index.read_bytes()
        ref = "refs/kaizen/" + datetime.date.today().isoformat()
        self.git("update-ref", ref, head)
        branch = self.git("symbolic-ref", "HEAD")
        self.git("symbolic-ref", "HEAD", ref)
        self.assertIn("checked out", self.commit_cli(change, expected=2).stderr)
        self.git("symbolic-ref", "HEAD", branch)
        self.assertIn("no journaled owner", self.commit_cli(change, expected=2).stderr)
        self.git("update-ref", "-d", ref)
        new = self.commit_cli(change).stdout.split()[1]
        self.assertEqual(self.git("rev-parse", ref), new)
        self.assertEqual(self.git("show", f"{new}:tracked"), "after")
        self.assertTrue(self.git("show", "-s", "--format=%B", new).endswith(f"kaizen-backup change: {change.name}"))
        self.assertEqual((self.git("rev-parse", "HEAD"), index.read_bytes(), self.target.read_text()),
                         (head, raw_index, "after"))

    def test_commit_refuses_dirty_bytes_and_forged_git_objects(self):
        nested = self.repo / "nested"
        nested.mkdir()
        (nested / "keep").write_text("unchanged")
        self.git("add", ".")
        self.git("-c", "user.name=Test", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "nested")
        change = self.begin("--repo", ".")
        self.target.write_text("after")
        self.script("finish", change)
        backup = change / "files" / "1"
        backup.write_text("forged before")
        self.commit_cli(change, expected=2)
        backup.write_text("before")
        extra = self.repo / "unrelated"
        extra.touch()
        self.commit_cli(change, expected=2)
        extra.unlink()
        for kind, spec in (("commit", "HEAD"), ("tree", "HEAD^{tree}"), ("tree", "HEAD:nested")):
            oid = self.git("rev-parse", spec)
            loose = self.repo / ".git" / "objects" / oid[:2] / oid[2:]
            original = loose.read_bytes()
            header, content = zlib.decompress(original).split(b"\0", 1)
            loose.chmod(0o600)
            loose.write_bytes(zlib.compress(header + b"\0" + content[:-1] + b"x"))
            try:
                self.assertIn("commit refused", self.commit_cli(change, expected=2).stderr, kind)
            finally:
                loose.write_bytes(original)
        self.commit_cli(change)

    def test_object_size_caps_include_unchanged_blobs(self):
        unchanged = self.repo / "unchanged"
        unchanged.write_bytes(b"x" * 1024)
        self.git("add", ".")
        self.git("commit", "-qm", "unchanged blob")
        change = self.ready()
        verify = self.helpers["verify_object"]
        executable = self.helpers["resolve_git"]()
        with patch.dict(self.helpers, MAX_GIT_OBJECT_BYTES=1):
            for kind, spec in (("commit", "HEAD"), ("tree", "HEAD^{tree}")):
                with self.assertRaisesRegex(ValueError, "object exceeds its size limit"):
                    verify(self.repo, kind, self.git("rev-parse", spec).encode("ascii"), executable)
        self.assertIn("object exceeds its size limit", self.main("commit", change, expected=2,
                                                                MAX_GIT_OBJECT_BYTES=512))

    def test_object_verification_refuses_large_packs_before_content(self):
        verify = self.helpers["verify_object"]
        executable = self.helpers["resolve_git"]()
        oid = self.git("rev-parse", "HEAD:tracked").encode("ascii")
        self.git("repack", "-ad")
        with patch.dict(self.helpers, MAX_GIT_OBJECT_BYTES=64):
            with self.assertRaisesRegex(ValueError, "pack.*size limit"):
                verify(self.repo, "blob", oid, executable)

    def test_object_verification_refuses_deltas_before_content(self):
        verify = self.helpers["verify_object"]
        executable = self.helpers["resolve_git"]()
        oid = self.git("rev-parse", "HEAD:tracked").encode("ascii")
        command = self.helpers["git"]

        def delta_metadata(root, *args, **kwargs):
            if args[0] == "cat-file" and "%(deltabase)" in args[1]:
                return b" ".join((oid, b"blob", b"6", b"30", b"1" * len(oid))) + b"\n"
            return command(root, *args, **kwargs)

        with patch.dict(self.helpers, git=delta_metadata):
            with self.assertRaisesRegex(ValueError, "delta.*cannot be bounded"):
                verify(self.repo, "blob", oid, executable)

    def test_unsafe_loose_object_index_is_refused_before_object_writes(self):
        change = self.ready()
        outside = self.tmp / "outside-index"
        outside.write_text("unchanged")
        index = self.repo / ".git/objects/loose-object-idx"
        index.symlink_to(outside)
        self.assertIn("unsafe Git metadata", self.commit_cli(change, expected=2).stderr)
        self.assertEqual(outside.read_text(), "unchanged")

    def test_symbolic_refs_into_kaizen_are_refused_even_if_the_target_is_missing(self):
        change = self.ready()
        ref = "refs/kaizen/" + datetime.date.today().isoformat()
        branch = self.git("symbolic-ref", "HEAD")
        alias = "refs/heads/kaizen-alias"
        for target in (ref, "refs/kaizen/unrelated"):
            with self.subTest(target=target):
                self.git("symbolic-ref", alias, target)
                self.assertIn("symbolic ref", self.commit_cli(change, expected=2).stderr)
                self.git("symbolic-ref", "--delete", alias)
        self.git("update-ref", "refs/kaizen/unrelated", "HEAD")
        self.git("symbolic-ref", "HEAD", "refs/kaizen/unrelated")
        self.assertIn("symbolic HEAD", self.commit_cli(change, expected=2).stderr)
        self.git("symbolic-ref", "HEAD", branch)
        self.git("symbolic-ref", branch, "refs/kaizen/unrelated")
        self.assertIn("symbolic ref", self.commit_cli(change, expected=2).stderr)

    def test_ref_directory_is_synced_before_each_effect_is_done(self):
        change = self.ready()
        ref = "refs/kaizen/" + datetime.date.today().isoformat()
        parent = self.repo / ".git/refs/kaizen"
        sync, save = os.fsync, self.helpers["save_record"]
        synced = []

        def observe_sync(fd):
            if (parent / Path(ref).name).exists() and os.path.samestat(os.fstat(fd), parent.stat()):
                synced.append(self.git("rev-parse", ref))
            return sync(fd)

        def check_save(folder, record):
            effect = record.get("inverse", record["commit"])
            if effect["done"]:
                self.assertIn(effect["new"], synced)
            return save(folder, record)

        with patch.object(os, "fsync", observe_sync):
            self.main("commit", change, save_record=check_save)
            self.main("undo", change, save_record=check_save)

    def test_completed_effects_recover_when_ref_rename_was_lost(self):
        change = self.ready()
        ref = self.commit_cli(change).stdout.split()[-1]
        before = self.git("rev-parse", ref)
        self.git("update-ref", "-d", ref, before)
        self.main("commit", change)
        self.assertEqual(self.git("rev-parse", ref), before)

        def fail_restore(*args):
            raise OSError("interrupted before restoring files")

        self.main("undo", change, expected=2, restore_ref_file=fail_restore)
        inverse = self.git("rev-parse", ref)
        self.git("update-ref", ref, before, inverse)
        self.main("undo", change)
        self.assertEqual((self.git("rev-parse", ref), self.target.read_text()), (inverse, "before"))
        self.git("update-ref", ref, before, inverse)
        self.assertIn(inverse, self.main("undo", change, expected=2))
        self.assertEqual((self.git("rev-parse", ref), self.target.read_text()), (before, "before"))

    def test_pending_commit_and_inverse_stay_pinned_until_complete(self):
        change = self.ready()
        pins = "refs/kaizen/pending/"
        save = self.helpers["save_record"]

        def stop_at_journal(folder, record):
            effect = record.get("inverse", record["commit"])
            if not effect["done"]:
                self.assertEqual(self.git("for-each-ref", "--format=%(objectname)", pins), effect["new"])
                save(folder, record)
                raise OSError("interrupted before ref update")
            save(folder, record)

        def stop_after_completion(folder, record):
            save(folder, record)
            if record.get("inverse", record["commit"])["done"]:
                raise OSError("interrupted before removing the completed pin")

        for command in ("commit", "undo"):
            self.main(command, change, expected=2, save_record=stop_at_journal)
            self.git("reflog", "expire", "--expire=now", "--all")
            self.git("-c", "pack.window=0", "gc", "--prune=now")
            self.main(command, change, expected=2, save_record=stop_after_completion)
            self.assertTrue(self.git("for-each-ref", pins))
            self.main(command, change)
            self.assertEqual(self.git("for-each-ref", pins), "")

    def test_undo_refuses_editor_save_after_temp_sync(self):
        self.check_undo_race(swap=False)

    def test_undo_refuses_parent_swap_after_temp_sync(self):
        self.check_undo_race(swap=True)

    def check_undo_race(self, *, swap):
        nested = self.repo / "nested"
        nested.mkdir()
        self.target = self.target.rename(nested / "tracked")
        self.git("add", "-A")
        self.git("commit", "-qm", "move tracked file")
        change = self.ready()
        self.commit_cli(change)
        outside = self.tmp / "outside"
        outside.mkdir()
        (outside / "tracked").write_text("after")
        old_parent = self.tmp / "moved"
        sync = os.fsync

        def concurrent_save(fd):
            info = os.fstat(fd)
            if stat.S_ISREG(info.st_mode) and info.st_size == len("before"):
                if swap:
                    nested.rename(old_parent)
                    nested.symlink_to(outside, target_is_directory=True)
                else:
                    self.target.write_text("editor save")
            return sync(fd)

        with patch.object(os, "fsync", concurrent_save):
            self.main("undo", change, expected=2)
        self.assertEqual((outside / "tracked").read_text(), "after")
        self.assertEqual((old_parent / "tracked").read_text() if swap else self.target.read_text(),
                         "after" if swap else "editor save")

    def test_checkout_tmpdir_is_never_probed_and_symlink_loop_refuses(self):
        alias = self.tmp / "scratch-link"
        alias.symlink_to(self.repo, target_is_directory=True)
        self.env["TMPDIR"] = str(alias)
        with patch.object(tempfile, "gettempdir", side_effect=AssertionError("tempdir probe")):
            change = self.begin_in_process("scratch")
        self.assertTrue(self.manifest(change)["git"]["clean_start"])
        self.assertTrue((self.backups / ".kaizen-refs").is_dir())
        self.target.write_text("after")
        self.script("finish", change)
        self.target.unlink()
        self.target.symlink_to(self.target.name)
        refusal = self.commit_cli(change, expected=2).stderr
        self.assertRegex(refusal, "cannot resolve path|through symlink")
        self.assertNotIn("Traceback", refusal)
        self.assertRegex(self.main("undo", change, expected=2), "cannot resolve path|through symlink")

    def test_commit_and_inverse_reconcile_across_failures(self):
        change = self.ready()
        ref = "refs/kaizen/" + datetime.date.today().isoformat()
        journal = self.helpers["record_path"](change)
        save, update = (self.helpers[name] for name in ("save_record", "update_ref"))

        def fail_save(phase, *, done=False, after=False):
            def injected(folder, record):
                if record.get(phase, {}).get("done") == done:
                    if after:
                        save(folder, record)
                    raise OSError("interrupted record write")
                save(folder, record)
            return injected

        def fail_cas(*args):
            if cas_happens:
                update(*args)
                raise OSError("interrupted CAS")

            def reject_prepared():
                args[-1]()
                raise OSError("interrupted CAS")

            update(*args[:-1], reject_prepared)

        self.main("commit", change, expected=2, save_record=fail_save("commit"))
        self.assertFalse(journal.exists())
        self.assertTrue(self.git("for-each-ref", "refs/kaizen/pending/"))
        self.main("commit", change, expected=2, save_record=fail_save("commit", after=True))
        oid = json.loads(journal.read_text())["commit"]["new"]
        self.assertEqual(self.git("for-each-ref", ref), "")
        self.git("update-ref", ref, self.git("rev-parse", "HEAD"))
        self.assertIn("ref moved", self.main("commit", change, expected=2))
        self.git("update-ref", "-d", ref)
        cas_happens = True
        self.main("commit", change, expected=2, update_ref=fail_cas)
        self.assertEqual(self.git("rev-parse", ref), oid)
        self.main("commit", change, expected=2, save_record=fail_save("commit", done=True))
        self.main("commit", change)
        self.assertEqual(self.git("rev-parse", ref), oid)
        self.assertEqual(self.git("for-each-ref", "refs/kaizen/pending/"), "")
        cas_happens = False
        self.main("undo", change, expected=2, update_ref=fail_cas)
        inverse = json.loads(journal.read_text())["inverse"]["new"]
        self.assertEqual(self.git("rev-parse", ref), oid)
        cas_happens = True
        self.main("undo", change, expected=2, update_ref=fail_cas)
        self.assertEqual((self.git("rev-parse", ref), self.target.read_text()), (inverse, "after"))
        self.main("undo", change, expected=2, save_record=fail_save("inverse", done=True))
        def fail_copy(_, target):
            target.write(b"incomplete copy")
            raise OSError("interrupted copy")

        with patch.object(shutil, "copyfileobj", fail_copy):
            self.main("undo", change, expected=2)
        self.assertEqual(self.target.read_text(), "after")
        self.target.write_text("before")  # Files may already have been restored before interruption.
        self.main("undo", change)
        self.assertEqual(self.git("rev-parse", ref), inverse)

        abandoned = self.ready("abandoned")

        def edit_before_cas(*args):
            def edit():
                self.target.write_text("user edit")
                args[-1]()

            update(*args[:-1], edit)

        self.main("commit", abandoned, expected=2, update_ref=edit_before_cas)
        self.assertEqual(self.target.read_text(), "user edit")
        ref_lock = self.repo / ".git" / (ref + ".lock")
        ref_lock.touch()
        refusal = self.main("undo", "--force", abandoned, expected=2)
        self.assertIn(str(ref_lock), refusal)
        self.assertIn("no Git process is running", refusal)
        self.assertTrue(ref_lock.exists())
        self.assertEqual(self.target.read_text(), "user edit")
        ref_lock.unlink()
        self.main("undo", "--force", abandoned)
        self.assertEqual((self.git("rev-parse", ref), self.target.read_text()), (inverse, "before"))
        self.assertEqual(self.git("for-each-ref", "refs/kaizen/pending/"), "")
        self.main("commit", abandoned, expected=2)

    def test_inverse_keeps_later_owned_files_and_rejects_moves_and_forgery(self):
        first = self.ready()
        ref = self.commit_cli(first).stdout.split()[-1]
        original = self.git("rev-parse", ref)
        self.target.write_text("before")
        other = self.repo / "other"
        second = self.script("begin", "--repo", ".", "--skill", "trim", "--ledger", "fixture", "--run", "second", other)
        other.write_text("later")
        self.script("finish", second)
        self.commit_cli(second)
        tip = self.git("rev-parse", ref)
        self.target.write_text("after")
        manifest = first / "manifest.json"
        raw = manifest.read_bytes()
        manifest.write_bytes(raw + b" ")
        self.assertIn("manifest changed", self.main("undo", first, expected=2))
        manifest.write_bytes(raw)
        self.git("update-ref", ref, original)
        self.assertIn("ref moved", self.main("undo", "--force", first, expected=2))
        self.git("update-ref", ref, tip)
        self.main("undo", first)
        self.assertEqual(self.git("diff", "--name-only", tip, ref), self.target.name)
        self.assertEqual(self.git("show", ref + ":other"), "later")

    def test_ref_storage_and_later_overlap_refuse_without_worktree_changes(self):
        change = self.ready()
        external = self.tmp / "external"
        external.mkdir()
        redirected = self.repo / ".git" / "refs" / "kaizen"
        redirected.symlink_to(external, target_is_directory=True)
        self.assertIn("unsafe Git metadata", self.commit_cli(change, expected=2).stderr)
        self.assertEqual(list(external.iterdir()), [])
        redirected.unlink()
        ref = self.commit_cli(change).stdout.split()[-1]
        self.target.write_text("before")
        self.git("merge", "--ff-only", ref)
        later = self.begin("--run", "overlap", "--repo", ".")
        self.target.write_text("later")
        self.script("finish", later)
        self.commit_cli(later)
        tip = self.git("rev-parse", ref)
        self.assertIn("overlapping change", self.main("undo", "--force", change, expected=2))
        self.assertEqual((self.git("rev-parse", ref), self.target.read_text()), (tip, "later"))

    def test_deep_backup_root_can_reserve_a_fallback_slot(self):
        root = self.tmp
        limit = os.pathconf(root, "PC_PATH_MAX") - 45
        while len(os.fsencode(root)) < limit - 1:
            root /= "d" * min(180, limit - len(os.fsencode(root)) - 1)
        root.mkdir(parents=True)
        with patch.dict(self.helpers, ROOT=root, BACKUP_ROOT=root, fcntl=None), patch("sys.stdout"):
            self.assertEqual(self.helpers["main"](
                ["begin", "--run", ".kaizen", "--skill", "t", "--ledger", "fixture", str(self.target)]), 0)
        self.assertEqual((root / ".kaizen-01-t" / "files" / "1").read_text(), "before")

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

    def fake_git(self, name="bin"):
        fake_dir = self.tmp / name
        fake_dir.mkdir()
        fake_git, marker = fake_dir / "git", self.tmp / f"{name}-ran"
        fake_git.write_text(f"#!/bin/sh\n: > {shlex.quote(str(marker))}\nexit 1\n")
        fake_git.chmod(0o755)
        fake_dir.chmod(0o755)
        return fake_dir, fake_git, marker

    def test_git_comes_only_from_trusted_locations_with_fixed_environment(self):
        fake_dir, _, marker = self.fake_git()
        env = dict(self.env, PATH=f"{fake_dir}{os.pathsep}{self.env.get('PATH', '')}",
                   LD_PRELOAD="inherited", BASH_ENV="inherited", DEVELOPER_DIR=str(fake_dir))
        with patch.dict(os.environ, env, clear=True), patch.object(
                subprocess, "run", wraps=subprocess.run) as run:
            stamp = self.capture(self.repo)
        self.env = env
        change = self.begin("--run", "trusted", "--repo", ".")
        self.assertFalse(marker.exists())
        self.assertIsNotNone(stamp)
        executable = stamp["git_executable"]
        candidate = next(path for path in self.helpers["TRUSTED_GIT"] if os.path.lexists(path))
        self.assertEqual(executable["path"], os.path.realpath(candidate))
        info = os.stat(executable["path"])
        self.assertEqual({key: executable[key] for key in ("dev", "ino", "size", "mtime_ns")},
                         dict(dev=info.st_dev, ino=info.st_ino, size=info.st_size, mtime_ns=info.st_mtime_ns))
        self.assertEqual(executable["sha256"], hashlib.sha256(Path(executable["path"]).read_bytes()).hexdigest())
        self.assertEqual(self.manifest(change)["git"]["git_executable"], executable)
        self.assertEqual(self.helpers["verify_git"](executable), executable["path"])
        self.assertTrue(run.call_args_list)
        for call in run.call_args_list:
            self.assertEqual(call.args[0][0], executable["path"])
            self.assertEqual(call.kwargs["env"]["PATH"], "/usr/bin:/bin")
            for name in ("LD_PRELOAD", "BASH_ENV", "DEVELOPER_DIR"):
                self.assertNotIn(name, call.kwargs["env"])

    def test_untrusted_or_replaced_git_is_never_run(self):
        fake_dir, fake_git, marker = self.fake_git()
        for name, mode in (("group-writable dir", (fake_dir, 0o775)), ("group-writable file", (fake_git, 0o775))):
            with self.subTest(name), patch.dict(self.helpers, TRUSTED_GIT=(str(fake_git),)):
                mode[0].chmod(mode[1])
                with self.assertRaisesRegex(ValueError, "trusted"):
                    self.helpers["resolve_git"]()
                self.assertIsNone(self.capture(self.repo))
                mode[0].chmod(0o755)
        self.assertFalse(marker.exists())
        record = self.helpers["resolve_git"]()
        for key, value in (("sha256", "0" * 64), ("ino", record["ino"] + 1), ("path", str(fake_git))):
            with self.subTest(key=key):
                forged = dict(record, **{key: value})
                with self.assertRaisesRegex(ValueError, "Git executable"):
                    self.helpers["verify_git"](forged)
                if key != "sha256":  # Each call rechecks identity; content is rehashed at verification.
                    with self.assertRaisesRegex(ValueError, "Git executable"):
                        self.helpers["git"](self.repo, "rev-parse", "HEAD", git_exe=forged)
        self.assertFalse(marker.exists())

    def test_filter_added_during_capture_never_executes(self):
        marker = self.tmp / "filter-ran"
        (self.repo / ".git" / "info" / "attributes").write_text("tracked filter=late\n")
        git = self.helpers["git"]
        injected = False

        def configure_late(directory, *args, **kwargs):
            nonlocal injected
            result = git(directory, *args, **kwargs)
            if not injected and "--others" in args:
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

    def test_tracked_edit_after_hash_revokes_clean_start(self):
        matches_blob = self.helpers["matches_blob"]

        def edit_after_hash(path, *args):
            matches = matches_blob(path, *args)
            if path == self.target:
                self.target.write_text("edited after hashing")
            return matches

        with patch.dict(self.helpers, matches_blob=edit_after_hash):
            self.assertIsNone(self.capture(self.repo))

    def test_untracked_creation_after_enumeration_revokes_clean_start(self):
        git = self.helpers["git"]
        (self.repo / ".git" / "info" / "exclude").write_text("ignored\n")

        def create_after_enumeration(directory, *args, **kwargs):
            result = git(directory, *args, **kwargs)
            if "--others" in args:
                untracked.touch()
            return result

        for name in ("untracked", "ignored"):
            untracked = self.repo / name
            with self.subTest(name=name), patch.dict(self.helpers, git=create_after_enumeration):
                self.assertIsNone(self.capture(self.repo))
                self.assertTrue(untracked.exists())
            untracked.unlink()

    def test_creation_after_final_untracked_scan_revokes_clean_start(self):
        sub = self.repo / "sub"
        sub.mkdir()
        (sub / "kept").write_text("kept")
        self.git("add", ".")
        self.git("-c", "user.name=Test", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "sub")
        git = self.helpers["git"]

        for name, create in (("file in scanned directory", lambda: (sub / "late").touch()),
                             ("empty directory", lambda: (sub / "late").mkdir())):
            scans = 0

            def create_after_final_scan(directory, *args, **kwargs):
                nonlocal scans
                result = git(directory, *args, **kwargs)
                if "--others" in args:
                    scans += 1
                    if scans == 2:
                        create()
                return result

            with self.subTest(name), patch.dict(self.helpers, git=create_after_final_scan):
                self.assertIsNone(self.capture(self.repo))
                self.assertEqual(scans, 2)
            late = sub / "late"
            late.rmdir() if late.is_dir() else late.unlink()
        self.assertIsNotNone(self.capture(self.repo))

    def test_copied_index_swap_during_scan_revokes_clean_start(self):
        git = self.helpers["git"]

        def swap_copied_index(directory, *args, **kwargs):
            git_dir = kwargs.get("git_dir")
            if git_dir is not None and "--stage" in args:
                index = Path(git_dir) / "index"
                original = index.read_bytes()
                index.write_bytes(original)  # Same bytes, new change time.
            return git(directory, *args, **kwargs)

        with patch.dict(self.helpers, git=swap_copied_index):
            self.assertIsNone(self.capture(self.repo))

    def test_existing_scratch_index_is_refused(self):
        git = self.helpers["git"]

        def occupy_index(directory, *args, **kwargs):
            result = git(directory, *args, **kwargs)
            if args[0] == "init":
                (Path(directory) / "index").write_text("already occupied")
            return result

        with patch.dict(self.helpers, git=occupy_index):
            change = self.begin_in_process("occupied")
        self.assertIsNone(self.manifest(change)["git"])
        self.assertEqual((change / "files" / "1").read_text(), "before")

    def test_scratch_index_replaced_after_stat_revokes_clean_start(self):
        git, lstat = self.helpers["git"], Path.lstat
        copy = None

        def remember_index(directory, *args, **kwargs):
            nonlocal copy
            result = git(directory, *args, **kwargs)
            if "--others" in args:
                copy = Path(kwargs["git_dir"]) / "index"
            return result

        def replace_after_stat(path):
            info = lstat(path)
            if path == copy:
                replacement = path.with_name("replacement")
                replacement.write_bytes(path.read_bytes())
                replacement.replace(path)
            return info

        with patch.dict(self.helpers, git=remember_index), patch.object(Path, "lstat", replace_after_stat):
            change = self.begin_in_process("swapped")
        data = self.manifest(change)
        self.assertIsNone(data["git"])
        self.assertEqual(data["git_reason"], "copied Git index changed during capture")
        self.assertEqual((change / "files" / "1").read_text(), "before")

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
        data, identity, digest = self.handoff(self.backups, change, **expected)
        self.assertTrue(data["finished"])
        self.assertEqual(identity, (change.stat().st_dev, change.stat().st_ino))
        self.assertEqual(digest, hashlib.sha256((change / "manifest.json").read_bytes()).hexdigest())
        self.assertNotIn("git", data)
        for path, overrides in ((old, {}), (change, {"session_id": "foreign"}),
                                (self.begin("--run", "foreign"), {}),
                                (change, {"started": datetime.datetime.now(datetime.timezone.utc)})):
            with self.assertRaises(ValueError):
                self.handoff(self.backups, path, **dict(expected, **overrides))
        renamed = change.rename(change.with_name("scheduled-99-trim"))
        with self.assertRaises(ValueError):
            self.handoff(self.backups, renamed, **expected)
        moved = old.rename(old.with_name("scheduled-01-other"))
        with self.assertRaisesRegex(ValueError, "not new"):
            self.handoff(self.backups, moved, **expected)

    def test_forged_clean_start_is_advisory_on_all_manifest_paths(self):
        self.env.update(KAIZEN_RUN_ID="scheduled", KAIZEN_SESSION_ID="session")
        self.backups.mkdir()
        started = datetime.datetime.now(datetime.timezone.utc)
        root_identity = self.helpers["backup_root_identity"](self.backups)
        change = self.begin()
        manifest = change / "manifest.json"
        original = self.manifest(change)
        outcomes = []
        forged = self.capture(self.repo)
        self.assertTrue(forged["clean_start"])
        for fields in ({}, {"clean_start": True, "git": forged}):
            with self.subTest(stamped=bool(fields)):
                self.target.write_text("after")
                manifest.write_text(json.dumps(dict(original, **fields)))
                self.script("action", change, "--did", "edit", "--undo", "restore")
                self.script("finish", change)
                result = [self.script("list"), self.script("prune", "--older-than", "1")]
                data, *_ = self.handoff(self.backups, change, run_id="scheduled", session_id="session",
                                        started=started, before=(set(), set()), root_identity=root_identity)
                result.append({key: value for key, value in data.items() if key not in fields})
                result.extend((self.script("undo", change), self.target.read_text()))
                outcomes.append(result)
                followup = self.begin("--repo", ".")
                self.assertIsNone(self.manifest(followup)["git"])
                shutil.rmtree(followup)
        self.assertEqual(outcomes[0], outcomes[1])
        self.assertIn("advisory", self.script("begin", "--help"))

    def test_handoff_hash_detects_manifest_replacement(self):
        self.env.update(KAIZEN_RUN_ID="scheduled", KAIZEN_SESSION_ID="session")
        started = datetime.datetime.now(datetime.timezone.utc)
        change = self.begin()
        root_identity = self.helpers["backup_root_identity"](self.backups)
        expected = dict(run_id="scheduled", session_id="session", started=started, before=(set(), set()),
                        root_identity=root_identity)
        _, identity, digest = self.handoff(self.backups, change, **expected)
        verify = self.helpers["verify_change_handoff"]
        verify(self.backups, change, root_identity=root_identity, identity=identity, manifest_sha256=digest)
        manifest = change / "manifest.json"
        replacement = manifest.with_suffix(".replacement")
        replacement.write_bytes(manifest.read_bytes() + b" ")
        replacement.replace(manifest)
        _, same_identity, new_digest = self.handoff(self.backups, change, **expected)
        self.assertEqual(same_identity, identity)
        self.assertNotEqual(new_digest, digest)
        with self.assertRaisesRegex(ValueError, "manifest hash changed"):
            verify(self.backups, change, root_identity=root_identity, identity=identity, manifest_sha256=digest)

    def test_backup_root_stamp_checks_timestamps(self):
        self.backups.mkdir()
        identity = self.helpers["backup_root_identity"](self.backups)
        info = self.backups.stat()
        self.assertEqual(identity["ctime_ns"], info.st_ctime_ns)
        if sys.platform == "darwin":
            self.assertEqual(identity["birthtime"], info.st_birthtime)
        self.env.update(KAIZEN_RUN_ID="scheduled", KAIZEN_SESSION_ID="session")
        started = datetime.datetime.now(datetime.timezone.utc)
        change = self.begin()
        expected = dict(run_id="scheduled", session_id="session", started=started, before=(set(), set()))
        self.handoff(self.backups, change, root_identity=identity, **expected)
        for key in ("ctime_ns", "birthtime") if sys.platform == "darwin" else ("ctime_ns",):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "backup root was replaced"):
                self.handoff(self.backups, change, root_identity=dict(identity, **{key: identity[key] * 2}),
                             **expected)

        snapshot = self.helpers["read_manifest_snapshot"]

        def touch_root_after_read(fd):
            result = snapshot(fd)
            (self.backups / "concurrent").mkdir()
            return result

        with patch.dict(self.helpers, read_manifest_snapshot=touch_root_after_read):
            with self.assertRaisesRegex(ValueError, "backup root was replaced or changed"):
                self.handoff(self.backups, change, root_identity=identity, **expected)

    def test_enolck_still_backs_up_without_clean_start(self):
        fcntl = self.helpers["fcntl"]

        def unavailable(fd, operation):
            self.assertTrue(stat.S_ISREG(os.fstat(fd).st_mode))
            self.assertEqual(fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE, os.O_RDWR)
            self.assertTrue(operation & fcntl.LOCK_EX)
            raise OSError(errno.ENOLCK, "lock unavailable")

        with patch.dict(os.environ, self.env, clear=True), patch.object(
                fcntl, "flock", side_effect=unavailable
        ) as lock, patch("sys.stdout"):
            self.assertEqual(self.helpers["main"](
                ["begin", "--run", "unlocked", "--repo", str(self.repo), "--skill", "trim",
                 "--ledger", "fixture", str(self.target)]), 0)
        lock.assert_called_once()
        lock_file = self.backups / ".kaizen-backup.lock"
        self.assertEqual(lock_file.stat().st_mode & 0o777, 0o600)
        change = self.backups / "unlocked-01-trim"
        self.assertIsNone(self.manifest(change)["git"])
        self.assertEqual((change / "files" / "1").read_text(), "before")

    def test_any_lock_failure_still_backs_up_without_clean_start(self):
        fcntl = self.helpers["fcntl"]
        lock_file = self.backups / ".kaizen-backup.lock"

        def busy(fd, operation):
            raise OSError(errno.EWOULDBLOCK, "busy")

        def broken(fd, operation):
            raise OSError(errno.EIO, "lock failed")

        def as_directory():
            lock_file.mkdir()

        def shared_mode():
            lock_file.touch(mode=0o644)
            lock_file.chmod(0o644)

        cases = (("unopenable", as_directory, {}), ("invalid", shared_mode, {}),
                 ("flock error", None, {"flock": broken}), ("held", None, {"flock": busy}))
        for run, (name, prepare, lock_patch) in enumerate(cases, 1):
            with self.subTest(name):
                self.backups.mkdir(exist_ok=True)
                if prepare:
                    prepare()
                with patch.dict(os.environ, self.env, clear=True), patch.dict(
                        self.helpers, LOCK_WAIT_SECONDS=0.2), patch.object(
                        fcntl, "flock", lock_patch.get("flock", fcntl.flock)), patch("sys.stdout"):
                    self.assertEqual(self.helpers["main"](
                        ["begin", "--run", f"lock{run}", "--repo", str(self.repo), "--skill", "trim",
                         "--ledger", "fixture", str(self.target)]), 0)
                data = self.manifest(self.backups / f"lock{run}-01-trim")
                self.assertIsNone(data["git"])
                self.assertIn("lock", data["git_reason"])
                self.assertEqual((self.backups / f"lock{run}-01-trim" / "files" / "1").read_text(), "before")
                lock_file.rmdir() if lock_file.is_dir() else lock_file.unlink(missing_ok=True)

    def test_concurrent_lock_fallbacks_allocate_distinct_change_numbers(self):
        next_number = self.helpers["next_number"]
        barrier = threading.Barrier(2)

        def simultaneous_number(run):
            number = next_number(run)
            barrier.wait(timeout=5)
            return number

        def begin(skill):
            return self.helpers["main"](
                ["begin", "--run", "unlocked", "--repo", str(self.repo), "--skill", skill,
                 "--ledger", "fixture", str(self.target)])

        with patch.dict(os.environ, self.env, clear=True), patch.dict(
                self.helpers, fcntl=None, next_number=simultaneous_number), patch("sys.stdout"):
            with ThreadPoolExecutor(max_workers=2) as workers:
                self.assertEqual(list(workers.map(begin, ("trim", "review"))), [0, 0])
        changes = list(self.backups.glob("unlocked-*"))
        self.assertEqual(sorted(self.manifest(change)["change"] for change in changes), [1, 2])
        for change in changes:
            self.assertIsNone(self.manifest(change)["git"])
            self.assertEqual((change / "files" / "1").read_text(), "before")

    def test_deep_manifest_uses_normal_rejection_path(self):
        change = self.begin()
        manifest = change / "manifest.json"
        original = manifest.read_text().rstrip()[:-1]
        for depth in (40, 2000):
            with self.subTest(depth=depth):
                manifest.write_text(original + ',"nested":' + "[" * depth + "0" + "]" * depth + "}")
                result = subprocess.run([sys.executable, str(SCRIPT), "undo", str(change)],
                                        env=self.env, cwd=self.repo, text=True, capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("cannot read manifest", result.stderr)
                self.assertNotIn("Traceback", result.stderr)

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
