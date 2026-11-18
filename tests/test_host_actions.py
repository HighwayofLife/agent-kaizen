"""Offline host-action store and CLI checks using disposable projects."""
from contextlib import ExitStack
import hmac
import json
import os
from pathlib import Path
import runpy
import shutil
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import kaizen_friction_actions as actions

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/kaizen-scheduled"
RUNNER = runpy.run_path(str(SCRIPT))
LITERALS = ("ls", "ls -a")
WORKER = """
import json
from pathlib import Path
import runpy
import sys
import time

from scripts.kaizen_friction_actions import HostActions

script, root, project, name, job, arg = sys.argv[1:]
root = Path(root)
runner = runpy.run_path(script)
store = HostActions(root / name, root / 'backup', runner['action_project'], runner['key'])

def record(selector):
    return store.record(project, 'test', selector, 'observed', allowed=(selector,))

print('ready', flush=True)
assert sys.stdin.read(1) == '!'
if job == 'insert':
    print(json.dumps([record('shared')] + [record(f'{arg}-{i}') for i in range(12)]))
elif job == 'mark':
    for command in ('done', 'reopen', 'dismiss'):
        store.mark(project, arg, command)
else:
    seen = set()
    deadline = time.monotonic() + 10
    while True:
        rows = store.scoped(project)
        ids = {row['id'] for row in rows}
        assert len(ids) == len(rows) and seen <= ids
        assert all(row['eligible'] is False and row['canonical_project'] == project for row in rows)
        if len(ids) == int(arg):
            break
        assert time.monotonic() < deadline, (job, len(ids), arg)
        seen = ids
        time.sleep(0.01)
"""


@unittest.skipIf(actions.fcntl is None, "requires flock")
class HostActionsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = self.root = Path(temporary.name).resolve()
        self.project, self.other = root / "projäct", root / "other"
        for project in (self.project, self.other):
            (project / "docs/kaizen").mkdir(parents=True)
        self.env = dict(os.environ, CLAUDE_CONFIG_DIR=str(root / "claude"), KAIZEN_BACKUP_DIR=str(root / "backup"),
                        GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull,
                        GIT_AUTHOR_NAME="Test", GIT_AUTHOR_EMAIL="test@example.invalid",
                        GIT_COMMITTER_NAME="Test", GIT_COMMITTER_EMAIL="test@example.invalid")
        self.store = actions.HostActions(root / "claude/audits", root / "backup", RUNNER["action_project"], RUNNER["key"])
        self.secret = self.store.friction / "machine.key"

    def cli(self, *args, project=None, code=0):
        result = subprocess.run([sys.executable, str(SCRIPT), "actions", *args, "--for",
                                 str(project or self.project)], capture_output=True, text=True, env=self.env)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result.stdout

    def record(self, project=None, literal="ls"):
        return self.store.record(project or self.project, "low-disk", literal, "e" * 600, allowed=LITERALS)

    def git(self, directory, *args):
        result = subprocess.run(["git", "-C", str(directory), *args], capture_output=True, text=True, env=self.env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def processes(self, *jobs):
        with ExitStack() as stack:
            workers = []
            for job in jobs:
                worker = stack.enter_context(subprocess.Popen(
                    [sys.executable, "-c", WORKER, str(SCRIPT), str(self.root), str(self.project), *job],
                    cwd=SCRIPT.parents[1], env=self.env, text=True, stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE))
                stack.callback(worker.kill)
                workers.append(worker)
            for worker in workers:
                self.assertEqual(worker.stdout.readline(), "ready\n")
            for worker in workers:
                worker.stdin.write("!")
                worker.stdin.flush()
            outputs = []
            for worker in workers:
                stdout, stderr = worker.communicate(timeout=20)
                self.assertEqual(worker.returncode, 0, stdout + stderr)
                outputs.append(json.loads(stdout) if stdout else None)
            return outputs

    def test_nested_project_owns_resolved_target(self):
        nested = self.project / "Nested"
        (nested / "docs/kaizen").mkdir(parents=True)
        target = nested / "File"
        target.touch()
        alias = self.project / "alias"
        alias.symlink_to(target)
        for selector in (target, alias):
            with self.subTest(selector=selector), self.assertRaises(ValueError):
                self.store.record(self.project, "target", selector, "evidence", path=True)
        ident = self.store.record(nested, "target", target.name, "evidence", path=True)
        row, = self.store.scoped(nested)
        self.assertEqual((row["id"], row["canonical_project"], row["selector_key"], row["projects"]),
                         (ident, str(nested), str(target), [RUNNER["key"](nested)]))
        self.assertEqual(self.store.scoped(self.project), [])

    def test_scheduled_and_cli_share_linked_subproject_ids(self):
        main, first, second = (self.root / name for name in ("main", "z-worktree", "a-worktree"))
        component = " component"
        (main / component).mkdir(parents=True)
        (main / component / "File").touch()
        self.git(main, "init")
        self.git(main, "add", ".")
        self.git(main, "commit", "-m", "Add component")
        for branch, worktree in (("first", first), ("second", second)):
            self.git(main, "worktree", "add", "-b", branch, str(worktree))
            (worktree / component / "docs/kaizen").mkdir(parents=True)

        scheduled = [RUNNER["discover"](None, None, {}, [worktree / component])[0][0]
                     for worktree in (first, second)]
        member = second / component
        self.assertEqual([project.canonical for project in scheduled], [member, member])
        ids = {self.record(project.canonical) for project in scheduled}
        for worktree in (first, second):
            ids.add(self.record(worktree / component))
            row, = json.loads(self.cli("list", "--json", project=worktree / component))
            self.assertEqual((row["canonical_project"], row["projects"]), (str(member), [RUNNER["key"](member)]))
            self.assertIn(row["id"], ids)
        self.assertEqual(len(ids), 1)
        path_ids = {self.store.record(worktree / component, "target", worktree / component / "File",
                                      "evidence", path=True) for worktree in (first, second)}
        self.assertEqual(len(path_ids), 1)
        path_row, = [row for row in self.store.scoped(first / component) if row["id"] in path_ids]
        self.assertEqual((path_row["canonical_project"], path_row["selector_key"], path_row["eligible"]),
                         (str(member), str(member / "File"), False))
        self.cli("list", project=main / component, code=2)

        for worktree in (main, first, second):
            (worktree / "docs/kaizen").mkdir(parents=True)
        (main / component / "docs/kaizen").mkdir(parents=True)
        self.git(main / component, "init")  # An independently enrolled repository at the same prefix.
        self.assertEqual(RUNNER["action_project"](first / component), member)
        self.assertEqual(self.store.scoped(first), [])
        for project, target in ((first, first / component / "File"), (first / component, main / component / "File")):
            with self.assertRaises(ValueError):
                self.store.action_id(project, "target", target, path=True)

    def test_text_listing_requires_scope_and_validates_selectors(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "actions", "list"],
                                capture_output=True, text=True, env=self.env)
        self.assertEqual(result.returncode, 2)
        self.assertIn("--for", result.stderr)
        alias = self.root / "alias"
        alias.symlink_to(self.project)
        target = self.project / "target"
        target.touch()
        (self.project / "link").symlink_to(target)
        (self.project / "escape").symlink_to(self.other)
        for path, value in ((False, "unknown"), (True, "../other"), (True, "escape")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.store.action_id(alias, "test", value, path=path, allowed=LITERALS)
        self.assertFalse(self.store.path.parent.exists())
        ident = self.store.record(alias / "docs", "test", "link", "evidence", path=True)
        self.assertEqual(self.store.action_id(self.project, "test", target, path=True), ident)
        self.assertEqual(self.cli("list", project=alias), f"{ident} open {json.dumps(str(target))}\n")
        row, = self.store.scoped(alias)
        self.assertEqual((row["canonical_project"], row["selector_key"], row["evidence"], row["eligible"]),
                         (str(self.project), str(target), "evidence", False))

    def test_cross_process_writers_and_readers_share_one_machine_key(self):
        writers = [(name, "insert", prefix) for name in ("claude/audits", "second-audits") for prefix in ("a", "b")]
        ids = self.processes(*writers, ("claude/audits", "read", "25"), ("second-audits", "read", "25"))[:4]
        self.assertEqual(len({rows[0] for rows in ids}), 1)
        self.assertEqual(len(set(ids[0] + ids[1])), 25)
        self.assertEqual(ids[:2], ids[2:])
        second = actions.HostActions(self.root / "second-audits", self.secret.parent.parent,
                                     RUNNER["action_project"], RUNNER["key"])
        for store in (self.store, second):
            self.assertEqual({row["id"] for row in store.scoped(self.project)}, set(ids[0] + ids[1]))

    def test_cross_process_manual_transitions_race_with_inserts(self):
        ident = self.store.record(self.project, "test", "shared", "first evidence", allowed=("shared",))
        inserted, _, _ = self.processes(("claude/audits", "insert", "a"), ("claude/audits", "mark", ident),
                                       ("claude/audits", "read", "13"))
        rows = {row["id"]: row for row in self.store.scoped(self.project)}
        self.assertEqual(set(rows), set(inserted))
        self.assertEqual((rows[ident]["status"], rows[ident]["evidence"], rows[ident]["eligible"]),
                         ("dismissed", "first evidence", False))

    def test_unenrolled_scope_writes_nothing(self):
        unenrolled = self.root / "unenrolled"
        unenrolled.mkdir()
        for mint in (self.store.action_id, self.store.record):
            with self.assertRaises(ValueError):
                mint(unenrolled, "low-disk", "ls", allowed=LITERALS)
        self.cli("list", project=unenrolled, code=2)
        self.assertFalse(self.store.path.parent.exists())
        self.assertFalse(self.store.friction.parent.exists())

    def test_case_aliases_share_scope_and_target(self):
        target = self.project / "Mixed"
        target.touch()
        alias = self.project.with_name("PROJÄCT") / "mIXED"
        if not alias.exists():
            self.skipTest("case-sensitive temporary volume")
        ident = self.store.record(self.project, "target", target, "evidence", path=True)
        self.assertEqual(self.store.record(alias.parent, "target", alias, "evidence", path=True), ident)
        self.assertEqual(json.loads(self.cli("list", "--json", project=alias.parent))[0]["selector_key"], str(target))

    def test_replacement_fsyncs_file_then_directory(self):
        ident = self.record()
        events = []
        replace = os.replace

        def rename(*args, **kwargs):
            events.append("replace")
            return replace(*args, **kwargs)

        with patch.object(os, "replace", side_effect=rename), patch.object(os, "fsync", side_effect=lambda fd:
                events.append("directory" if stat.S_ISDIR(os.fstat(fd).st_mode) else "file")):
            self.store.mark(self.project, ident, "done")
        self.assertEqual(events, ["file", "replace", "directory"])

    def test_ancestor_swap_after_lock_cannot_redirect_writer(self):
        ident = self.record()
        parent = self.store.path.parent.parent
        displaced, redirect = self.root / "displaced", self.root / "redirect"
        (redirect / "audits").mkdir(parents=True)
        decoy = redirect / "audits/host-actions.json"
        decoy.write_bytes(self.store.path.read_bytes())
        decoy.chmod(0o600)
        before = decoy.read_bytes()
        flock = actions.fcntl.flock

        def swap(fd, operation):
            flock(fd, operation)
            parent.rename(displaced)
            parent.symlink_to(redirect)

        with patch.object(actions.fcntl, "flock", side_effect=swap):
            self.store.mark(self.project, ident, "done")
        self.assertEqual(decoy.read_bytes(), before)
        self.assertEqual(json.loads((displaced / "audits/host-actions.json").read_bytes())["actions"][ident]["status"],
                         "done")
    def test_missing_store_and_stable_ids(self):
        self.assertEqual(json.loads(self.cli("list", "--json")), [])
        self.assertFalse(self.store.path.parent.exists())
        ids = [self.record(), self.record(), self.record(literal="ls -a"), self.record(self.other)]
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

    def test_malformed_replaced_and_missing_keys_cannot_mint_for_existing_rows(self):
        self.record()
        original = self.secret.read_bytes()
        before = self.store.path.read_bytes()
        for key in (b"short", original + b"x", bytes(byte ^ 1 for byte in original), None):
            with self.subTest(key_length=None if key is None else len(key)):
                self.secret.unlink(missing_ok=True)
                if key is not None:
                    self.secret.touch(mode=0o600)
                    self.secret.write_bytes(key)
                with self.assertRaises((OSError, ValueError)):
                    self.record(literal="ls -a")
                self.assertEqual(self.store.path.read_bytes(), before)
                self.assertEqual(self.secret.read_bytes() if self.secret.exists() else None, key)
                self.cli("list", "--json", code=2)

    def test_duplicate_damaged_and_forged_records_refuse_reads_and_writes(self):
        ident = self.record()
        row = json.loads(self.store.path.read_bytes())["actions"][ident]
        for name, rows in (
            ("duplicate ID", f'"{ident}":{json.dumps(row)},"{ident}":{json.dumps(row)}'),
            ("damaged", json.dumps({ident: dict(row, subject="unverified")})[1:-1]),
            ("forged eligible", json.dumps({ident: dict(row, eligible=True)})[1:-1]),
        ):
            with self.subTest(case=name):
                raw = f'{{"v":1,"actions":{{{rows}}}}}'.encode()
                self.store.path.write_bytes(raw)
                with self.assertRaises(ValueError):
                    self.store.scoped(self.project)
                with self.assertRaises(ValueError):
                    self.record(literal="ls -a")
                self.assertEqual(self.store.path.read_bytes(), raw)

    def test_untrusted_store_and_backup_ancestors_are_refused(self):
        self.record()
        parent = self.store.path.parent.parent
        original_mode = stat.S_IMODE(parent.stat().st_mode)
        before = self.store.path.read_bytes()
        for mode in (0o020, 0o002):
            parent.chmod(original_mode | mode)
            try:
                with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, "directory"):
                    self.record(literal="ls -a")
            finally:
                parent.chmod(original_mode)
            self.assertEqual(self.store.path.read_bytes(), before)
        alias = self.root / "backup-alias"
        alias.symlink_to(self.root)
        other = actions.HostActions(self.store.path.parent, alias / "backup", RUNNER["action_project"], RUNNER["key"])
        with self.assertRaises(OSError):
            other.scoped(self.project)

    def test_owner_mode_and_file_type_checked_for_store_key_and_locks(self):
        self.record()
        second = actions.HostActions(self.root / "second-audits", self.secret.parent.parent,
                                     RUNNER["action_project"], RUNNER["key"])
        key_lock = self.secret.with_suffix(".key.lock")
        rows_lock = self.store.path.with_suffix(".json.lock")
        for path in (self.store.path.parent.parent, self.store.path.parent, self.store.path, rows_lock,
                     self.secret.parent.parent, self.secret.parent, self.secret, key_lock):
            use = second if path == key_lock else self.store
            original = path.stat()
            fstat = os.fstat

            def probe():
                return use.action_id(self.project, "low-disk", "ls -a", allowed=LITERALS)

            def foreign_owner(fd):
                info = fstat(fd)
                if os.path.samestat(info, original):
                    return SimpleNamespace(st_mode=info.st_mode, st_nlink=info.st_nlink, st_uid=os.geteuid() + 1)
                return info

            with self.subTest(path=path.name, check="owner"), patch.object(os, "fstat", side_effect=foreign_owner):
                with self.assertRaises(ValueError):
                    probe()
            path.chmod(stat.S_IMODE(original.st_mode) | 0o020)
            try:
                with self.subTest(path=path.name, check="mode"), self.assertRaises(ValueError):
                    probe()
            finally:
                path.chmod(stat.S_IMODE(original.st_mode))
            if not path.is_file():
                continue
            saved = path.with_name(path.name + ".saved")
            path.rename(saved)
            for link in (False, True):
                try:
                    if link:
                        path.symlink_to(saved)
                    else:
                        os.mkfifo(path, 0o600)
                    with self.subTest(path=path.name, symlink=link), self.assertRaises((ValueError, OSError)):
                        probe()
                finally:
                    path.unlink(missing_ok=True)
            saved.rename(path)
        self.assertEqual(len(self.store.scoped(self.project)), 1)

    def test_existing_commands_work_without_helper_or_available_store(self):
        installed = self.root / "installed"
        installed.mkdir()
        for name in (SCRIPT.name, "kaizen_credentials.py", "pricing.json"):
            shutil.copyfile(SCRIPT.with_name(name), installed / name)
        self.store.path.parent.mkdir(parents=True)
        self.store.path.mkdir()  # Reject a non-regular store before using it.
        for script in (installed / SCRIPT.name, SCRIPT):
            for code, args in (
                (2, ("actions", "list", "--for", self.project)),
                (0, ("config", "show", "--for", self.project)),
                (0, ("checks", "path", "--for", self.project)),
                (0, ("review", "--dry-run", "--project-dir", self.project, "--token-audit",
                     SCRIPT.with_name("token-audit"))),
            ):
                with self.subTest(script=script.parent.name, command=args[0]):
                    result = subprocess.run([sys.executable, str(script), *map(str, args)],
                                            capture_output=True, text=True, env=self.env)
                    self.assertEqual(result.returncode, code, result.stdout + result.stderr)

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
