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


def block(*items):
    return "<!-- kaizen-host-actions " + json.dumps(
        {"v": 1, "actions": [dict(id=ident, intent=intent) for ident, intent in items]}) + " -->"


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

        # In a Git repository the enrolled root wins: the nested enrollment and its selectors map onto it.
        self.git(self.project, "init")
        self.assertEqual(RUNNER["action_project"](nested), self.project)
        ids = {self.store.record(project, "target", selector, "evidence", path=True)
               for project, selector in ((self.project, target), (self.project, alias),
                                         (self.project, "Nested/File"), (nested, target.name))}
        self.assertEqual(len(ids), 1)
        self.assertNotIn(ident, ids)
        row, = self.store.scoped(nested)
        self.assertEqual((row["id"], row["canonical_project"], row["selector_key"], row["projects"]),
                         (*ids, str(self.project), str(target), [RUNNER["key"](self.project)]))
        self.assertEqual(self.store.scoped(self.project), [row])

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

        # Once the repository root is enrolled it wins: every nested enrollment in any worktree joins it.
        for worktree in (main, first, second):
            (worktree / "docs/kaizen").mkdir(parents=True)
        scheduled = [RUNNER["discover"](None, None, {}, [directory])[0][0]
                     for directory in (first / component, second / component, first, main)]
        self.assertEqual([project.canonical for project in scheduled], [main] * 4)
        for directory in (main, main / component, first / component, second):
            self.assertEqual(RUNNER["action_project"](directory), main)
        root_ids = {self.store.record(worktree / component, "target", worktree / component / "File",
                                      "evidence", path=True) for worktree in (first, second)}
        root_ids |= {self.store.record(project, "target", selector, "evidence", path=True)
                     for project, selector in ((main, f"{component}/File"), (first, f"{component}/File"),
                                               (second / component, "File"))}
        self.assertEqual(len(root_ids), 1)
        self.assertTrue(root_ids.isdisjoint(path_ids))
        row, = json.loads(self.cli("list", "--json", project=first / component))
        self.assertEqual((row["id"], row["canonical_project"], row["selector_key"], row["projects"]),
                         (*root_ids, str(main), str(main / component / "File"), [RUNNER["key"](main)]))
        self.assertEqual([row["id"] for row in self.store.scoped(second / component)], [*root_ids])
        before = self.store.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "unavailable host-action ID"):
            self.store.import_actions(block((path_row["id"], "suggest")),
                                      {path_row["id"]: dict(path_row, intents=["suggest"])}, first, "stale")
        self.assertEqual(self.store.path.read_bytes(), before)

        self.git(first / component, "init")
        with self.assertRaisesRegex(ValueError, "outside the canonical project"):
            self.store.action_id(main, "target", first / component / "File", path=True)
        shutil.rmtree(first / component / ".git")
        counterpart = main / component / "File"
        counterpart.unlink()
        counterpart.symlink_to(self.root)
        with self.assertRaisesRegex(ValueError, "scope is unknown"):
            self.store.action_id(first, "target", first / component / "File", path=True)
        counterpart.unlink()
        counterpart.touch()
        (main / component / "docs/kaizen").mkdir(parents=True)
        self.git(main / component, "init")  # An independently enrolled repository at the same prefix.
        self.assertEqual(RUNNER["action_project"](main / component), main / component)
        self.assertEqual(RUNNER["action_project"](first / component), main)
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
        self.assertEqual(events[events.index("file"):], ["file", "replace", "directory"])
        self.assertEqual(set(events[:events.index("file")]), {"directory"})

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

    def test_import_validation_receipt_and_interrupted_retry(self):
        ident = self.store.action_id(self.project, "low-disk", "ls", allowed=LITERALS)
        frozen = {ident: dict(canonical_project=str(self.project), catalog_id="low-disk", selector_key="ls",
                              intents=["suggest", "apply"], evidence="observed")}
        apply, suggest = block((ident, "apply")), block((ident, "suggest"))
        for fragment, rows in (
            (suggest.replace('"v": 1', '"v": true'), frozen),
            (suggest.replace('"v": 1', '"v": 1, "v": 1'), frozen),
            (suggest.replace('"intent": "suggest"', '"intent": []'), frozen),
            (block(*[(ident, "suggest")] * 2), frozen), (suggest + "\n", frozen),
            (block(*[("fa1_" + f"{i:064x}", "suggest") for i in range(17)]), frozen),
            (suggest.replace('"actions"', " " * 8192 + '"actions"'), frozen),
            (suggest, {}), (suggest, {ident: dict(frozen[ident], selector_key="wrong")}),
            (apply, {ident: dict(frozen[ident], intents=["suggest"])}),
            (suggest, {ident: dict(frozen[ident], canonical_project=str(self.other))}),
        ):
            with self.assertRaises(ValueError):
                self.store.import_actions(fragment, rows, self.project, "bad")
            self.assertFalse(self.store.path.exists())
        fsync = os.fsync
        audit_inode = self.store.path.parent.stat().st_ino

        def interrupt(fd):
            if os.fstat(fd).st_ino == audit_inode and self.store.path.exists():
                raise OSError("interrupted directory sync")
            fsync(fd)

        with patch.object(os, "fsync", side_effect=interrupt):
            for _ in range(2):
                with self.assertRaises(OSError):
                    self.store.import_actions(apply, frozen, self.project, "apply")
        before = self.store.path.read_bytes()
        self.assertEqual(self.store.import_actions(apply, frozen, self.project, "apply"), {ident: "pending"})
        self.assertEqual(self.store.path.read_bytes(), before)
        self.assertEqual(self.store.import_actions(suggest, frozen, self.project, "suggest"), {ident: "terminal"})
        self.assertEqual(self.store.import_actions(block(), {}, self.project, "empty"), {})
        self.assertEqual(self.cli("verify"), f"{ident} pending\n")
        self.cli("done", ident, code=2)
        (self.project / ".nomedia").touch()
        marker = self.store.record(self.project, "linux-localsearch", self.project, "observed", path=True)
        with patch.object(actions.sys, "platform", "linux"):
            self.assertEqual(self.store.verify(self.project), {ident: "pending", marker: "done"})
        done = next(row for row in self.store.scoped(self.project) if row["id"] == marker)
        self.assertEqual((done["done_by"], done["metric_at_done"]), ("verify", None))

    def test_manual_verification_and_evidence_flaps(self):
        ident = self.record()
        row, = self.store.scoped(self.project)
        frozen = {ident: dict(row, intents=["suggest"], evidence="initial")}
        suggest = block((ident, "suggest"))
        self.store.import_actions(suggest, frozen, self.project, "initial")
        probe = self.store.path.parent / "projects" / row["projects"][0] / "host-probe-fixture.json"
        probe.parent.mkdir(parents=True)
        probe.touch(mode=0o600)
        probe.write_text(json.dumps(dict(v=1, project=str(self.project), generated_at=row["first_seen"],
                                         facts=dict(free_disk_bytes=42))))
        for flaps in (1, 2):
            self.cli("done", ident)
            done, = self.store.scoped(self.project)
            self.assertEqual((done["done_by"], done["metric_at_done"]["value"]), ("user", 42))
            self.store.import_actions(suggest, frozen, self.project, f"same-{flaps}")
            self.assertEqual(self.store.scoped(self.project), [done])
            frozen[ident]["evidence"] = f"changed-{flaps}"
            self.store.import_actions(suggest, frozen, self.project, f"changed-{flaps}")
            reopened, = self.store.scoped(self.project)
            self.assertEqual((reopened["status"], reopened["flaps"]), ("open", flaps))
        with patch.object(self.store, "_probe", side_effect=AssertionError):
            self.assertEqual(self.store.verify(self.project), {ident: "unavailable"})
        self.cli("dismiss", ident)
        before = self.store.scoped(self.project)
        self.store.import_actions(suggest, frozen, self.project, "changed-2")
        self.assertEqual(self.store.scoped(self.project), before)

    def test_completed_apply_replays_without_changing_intent(self):
        ident = self.record()
        row, = self.store.scoped(self.project)
        frozen = {ident: dict(row, intents=["suggest", "apply"])}
        request = block((ident, "apply"))
        self.store.import_actions(request, frozen, self.project, "review")
        with actions._directory(self.store.path.parent) as directory:
            rows, _, receipts = self.store._load(directory)
            receipts[str(self.project)]["review"][ident] = "terminal"
            self.store._save(directory, rows, receipts)
        before = self.store.path.read_bytes()
        self.assertEqual(self.store.import_actions(request, frozen, self.project, "review"), {ident: "terminal"})
        with self.assertRaisesRegex(ValueError, "different requests"):
            self.store.import_actions(block((ident, "suggest")), frozen, self.project, "review")
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_import_prunes_old_empty_and_acknowledged_generations(self):
        ident = self.record()
        row, = self.store.scoped(self.project)
        frozen = {ident: dict(row, intents=["suggest", "apply"])}
        request = block((ident, "suggest"))
        generations = [f"scheduled:{i:020d}" for i in range(1, 6)]
        self.store.import_actions(block(), {}, self.project, generations[0])
        for generation in generations[1:3]:
            self.store.import_actions(request, frozen, self.project, generation)
        other = self.record(self.other)
        other_row, = self.store.scoped(self.other)
        self.store.import_actions(block((other, "apply")), {other: dict(other_row, intents=["apply"])},
                                  self.other, generations[0])
        state = self.secret.parent / ("prepare-" + row["projects"][0] + ".json")
        state.touch(mode=0o600)
        state.write_text(json.dumps(dict(v=1, project=str(self.project),
                                         acknowledged_generation=generations[1].split(":")[1])))
        for generation in generations[3:]:
            self.store.import_actions(block(), {}, self.project, generation)
        stored = json.loads(self.store.path.read_bytes())["receipts"]
        self.assertEqual(stored[str(self.project)], {generations[2]: {ident: "terminal"}, generations[4]: {}})
        self.assertEqual(stored[str(self.other)], {generations[0]: {other: "pending"}})

    def test_localsearch_verifies_linked_outputs(self):
        main, (member,) = self.linked("worktree")
        main = main / member.name
        (main / "docs/kaizen").mkdir(parents=True)
        for project in (main, member):
            (project / "build").mkdir()
        ident = self.store.record(member, "linux-localsearch", member / "build", "observed", path=True)
        (main / "build/.nomedia").touch()
        with patch.object(actions.sys, "platform", "linux"):
            self.assertEqual(self.store.verify(main), {ident: "open"})
            (member / "build/.nomedia").touch()
            self.assertEqual(self.store.verify(main), {ident: "done"})

    def test_inotify_verification_uses_tracked_file_threshold(self):
        ident = self.store.record(self.project, "inotify-limit", "inotify", "observed", allowed=["inotify"])
        row, = self.store.scoped(self.project)
        probe = SimpleNamespace(read_proc=lambda _: 120000, git=lambda *_: "f\0" * 100000)
        with patch.object(actions.sys, "platform", "linux"), \
                patch.object(runpy, "run_path", return_value={"Probe": lambda *_: probe, "sibling": lambda *_: None}):
            self.assertFalse(self.store._probe(str(self.project), row)[0])
            probe.read_proc = lambda _: 200000
            self.assertTrue(self.store._probe(str(self.project), row)[0])

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

    def linked(self, *names, component=" component"):
        main = self.root / "main"
        (main / component).mkdir(parents=True)
        (main / component / "File").touch()
        self.git(main, "init")
        self.git(main, "add", ".")
        self.git(main, "commit", "-m", "Add component")
        worktrees = [self.root / name for name in names]
        for number, worktree in enumerate(worktrees):
            self.git(main, "worktree", "add", "-b", f"branch-{number}", str(worktree))
            (worktree / component / "docs/kaizen").mkdir(parents=True)
        return main, [worktree / component for worktree in worktrees]

    @unittest.skipUnless(sys.platform == "darwin", "Darwin extended ACLs")
    def test_darwin_extended_acls_refuse_store_key_and_locks(self):
        self.record()
        second = actions.HostActions(self.root / "second-audits", self.secret.parent.parent,
                                     RUNNER["action_project"], RUNNER["key"])
        key_lock = self.secret.with_suffix(".key.lock")
        rows_lock = self.store.path.with_suffix(".json.lock")
        before = self.store.path.read_bytes()
        for path in (self.store.path.parent.parent, self.secret.parent.parent, self.store.path.parent,
                     self.store.path, rows_lock, self.secret.parent, self.secret, key_lock):
            use = second if path == key_lock else self.store
            if path in (self.store.path.parent.parent, self.secret.parent.parent):
                grant = "group:everyone allow delete_child"
            else:
                grant = "group:everyone allow " + ("list" if path.is_dir() else "read")
            subprocess.run(["chmod", "+a", grant, str(path)], check=True)
            try:
                with self.subTest(path=path.name), self.assertRaisesRegex(ValueError, "ACL"):
                    use.action_id(self.project, "low-disk", "ls -a", allowed=LITERALS)
                if path not in (rows_lock, key_lock):
                    with self.subTest(path=path.name, read=True), self.assertRaisesRegex(ValueError, "ACL"):
                        self.store.scoped(self.project)
            finally:
                subprocess.run(["chmod", "-N", str(path)], check=True)
        self.assertEqual(self.store.path.read_bytes(), before)
        self.assertFalse(second.path.exists())
        self.assertEqual(len(self.store.scoped(self.project)), 1)

    @unittest.skipUnless(sys.platform == "darwin", "Darwin extended ACLs")
    def test_darwin_deny_only_ancestor_acl_allows_store_access(self):
        parent = self.store.path.parent.parent
        parent.mkdir()
        subprocess.run(["chmod", "+a", "group:everyone deny delete", str(parent)], check=True)
        try:
            self.assertEqual(self.record(), self.store.scoped(self.project)[0]["id"])
        finally:
            subprocess.run(["chmod", "-N", str(parent)], check=True)

    def test_failed_git_probe_leaves_linked_scope_unknown(self):
        _, (member, peer) = self.linked("worktree", "peer")
        canonical = RUNNER["action_project"](member)
        namespace = RUNNER["discover"].__globals__
        real = namespace["_git"]
        for probe in ("--git-common-dir", "list", "--show-prefix", "-z"):
            def timed_out(directory, *arguments):
                return None if probe in arguments else real(directory, *arguments)

            with self.subTest(probe=probe), patch.dict(namespace, _git=timed_out):
                for mint in (self.store.action_id, self.store.record):
                    with self.assertRaisesRegex(ValueError, "unknown"):
                        mint(member, "low-disk", "ls", allowed=LITERALS)
                with self.assertRaisesRegex(ValueError, "unknown"):
                    self.store.scoped(member)
            self.assertFalse(self.store.path.parent.exists())
        fake = self.root / "bin"
        fake.mkdir()
        (fake / "git").write_text("#!/bin/sh\nexit 1\n")
        (fake / "git").chmod(0o700)
        ident = self.record(member)
        result = subprocess.run([sys.executable, str(SCRIPT), "actions", "done", ident, "--for", str(member)],
                                capture_output=True, text=True, env=dict(self.env, PATH=f"{fake}:{os.defpath}"))
        self.assertEqual((result.returncode, result.stdout), (2, ""))
        self.assertIn("scope is unknown", result.stderr)
        self.assertEqual(json.loads(self.cli("list", "--json", project=member))[0]["status"], "open")
        self.assertEqual(self.store.scoped(member)[0]["canonical_project"], str(canonical))
        member.parent.rename(self.root / "unmounted")
        with self.assertRaisesRegex(ValueError, "scope is unknown"):
            self.store.scoped(peer)

    def test_special_character_worktree_paths_keep_cli_and_scheduled_ids(self):
        _, members = self.linked('a "q\\ wt', "z-wt")
        expected = members[0]
        for member in members:
            with self.subTest(member=member):
                project, = RUNNER["discover"](None, None, {}, [member])[0]
                self.assertEqual(project.canonical, expected)
                self.assertTrue(set(members) <= set(project.paths))
                self.assertFalse(project.unknown)
        ident = self.record(members[0])
        self.assertEqual({self.record(member) for member in members}, {ident})
        row, = json.loads(self.cli("list", "--json", project=members[1]))
        self.assertEqual((row["id"], row["canonical_project"]), (ident, str(expected)))

    def test_worktree_paths_without_git_null_output_fail_closed(self):
        _, members = self.linked('a "q\\ wt', "z-wt")
        namespace = RUNNER["discover"].__globals__
        real = namespace["_git"]
        with patch.dict(namespace, _git=lambda directory, *arguments:
                        None if "-z" in arguments else real(directory, *arguments)):
            for member in members:
                with self.subTest(member=member), self.assertRaisesRegex(ValueError, "unknown"):
                    self.record(member)

    def test_newline_worktree_paths_fail_closed(self):
        _, members = self.linked("a\rworktree", "z-worktree")
        for member in members:
            with self.subTest(member=member), self.assertRaisesRegex(ValueError, "unknown"):
                self.record(member)

    def test_import_refuses_scope_change_after_lock(self):
        main, (member,) = self.linked("worktree")
        ident = self.store.action_id(member, "low-disk", "ls", allowed=LITERALS)
        project = str(RUNNER["action_project"](member))
        frozen = {ident: dict(canonical_project=project, catalog_id="low-disk", selector_key="ls",
                              intents=["apply"], evidence="observed")}
        flock = actions.fcntl.flock

        def enroll(fd, operation):
            flock(fd, operation)
            (main / "docs/kaizen").mkdir(parents=True, exist_ok=True)

        with patch.object(actions.fcntl, "flock", side_effect=enroll), \
                self.assertRaisesRegex(ValueError, "scope changed; try again"):
            self.store.import_actions(block((ident, "apply")), frozen, member, "race")
        self.assertFalse(self.store.path.exists())

    def test_existing_worktree_directory_without_registration_is_unknown(self):
        _, (member, peer) = self.linked("worktree", "peer")
        (member.parent / ".git").unlink()
        with self.assertRaisesRegex(ValueError, "unknown"):
            self.record(peer)

    def test_mapped_selector_cannot_escape_canonical_checkout(self):
        main, (member, peer) = self.linked("a-worktree", "z-worktree")
        (main / "docs/kaizen").mkdir(parents=True)
        (main / "escape").symlink_to(peer.parent / " component" / "File")
        (member.parent / "escape").touch()
        with self.assertRaisesRegex(ValueError, "unknown"):
            self.store.record(member, "target", member.parent / "escape", "evidence", path=True)

    def test_unrecoverable_project_key_skips_only_bad_rows(self):
        bad = self.record()
        good = self.record(self.other)
        document = json.loads(self.store.path.read_text())
        document["actions"][bad]["projects"] = ["legacy-key"]
        self.store.path.write_text(json.dumps(document))
        with patch("sys.stderr", new_callable=__import__("io").StringIO) as warning:
            self.assertEqual([row["id"] for row in self.store.scoped(self.other)], [good])
        self.assertIn("skipped 1 row(s)", warning.getvalue())

    def test_skipped_row_and_pending_receipt_survive_unrelated_update(self):
        bad, good = self.record(), self.record(self.other)
        document = json.loads(self.store.path.read_text())
        document["actions"][bad]["projects"] = ["legacy-key"]
        document["receipts"] = {str(self.project): {"generation": {bad: "pending"}}}
        row_bytes = json.dumps(document["actions"][bad], indent=2)
        receipt_bytes = json.dumps(document["receipts"][str(self.project)]["generation"], indent=2)
        encoded = json.dumps(document)
        encoded = encoded.replace(json.dumps(document["actions"][bad]), row_bytes)
        encoded = encoded.replace(json.dumps(document["receipts"][str(self.project)]["generation"]), receipt_bytes)
        self.store.path.write_text(encoded)
        self.store.mark(self.other, good, "done")
        saved_text = self.store.path.read_text()
        self.assertIn(row_bytes, saved_text)
        self.assertIn(receipt_bytes, saved_text)
        saved = json.loads(saved_text)
        self.assertEqual(saved["actions"][bad], document["actions"][bad])
        self.assertEqual(saved["receipts"][str(self.project)], document["receipts"][str(self.project)])
        self.assertEqual(saved["actions"][good]["status"], "done")

    def test_skipped_pending_receipt_does_not_restore_completed_sibling(self):
        bad, good = self.record(), self.record(literal="ls -a")
        document = json.loads(self.store.path.read_text())
        document["actions"][bad]["projects"] = ["legacy-key"]
        document["receipts"] = {str(self.project): {"generation": {bad: "pending", good: "pending"}}}
        escaped = r'"p\u0065nding"'
        self.store.path.write_text(json.dumps(document).replace(f'"{bad}": "pending"', f'"{bad}": {escaped}'))
        with actions._directory(self.store.path.parent) as directory:
            rows, _, receipts = self.store._load(directory)
            receipts[str(self.project)]["generation"][good] = "terminal"
            rows[good].update(status="done", done_by="verify")
            self.store._save(directory, rows, receipts)
            rows, _, receipts = self.store._load(directory)
        self.assertEqual(rows[good]["status"], "done")
        self.assertEqual(receipts[str(self.project)]["generation"], {bad: "pending", good: "terminal"})
        self.assertIn(f'"{bad}":{escaped}', self.store.path.read_text())

    def test_mark_refuses_scope_change_after_lock(self):
        main, (member,) = self.linked("worktree")
        ident = self.record(member)
        before = self.store.path.read_bytes()
        flock = actions.fcntl.flock

        def enroll(fd, operation):
            flock(fd, operation)
            (main / "docs/kaizen").mkdir(parents=True, exist_ok=True)

        with patch.object(actions.fcntl, "flock", side_effect=enroll), \
                self.assertRaisesRegex(ValueError, "scope changed; try again"):
            self.store.mark(member, ident, "done")
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_copied_worktree_pointer_scope_is_unknown(self):
        main, (member,) = self.linked("worktree")
        (main / "docs/kaizen").mkdir(parents=True)
        copy = self.root / "copy"
        shutil.copytree(member.parent, copy)
        with self.assertRaisesRegex(ValueError, "unknown"):
            self.store.scoped(copy / " component")

    def test_relative_worktree_pointers_resolve_from_their_files(self):
        main, (member,) = self.linked("worktree")
        dotgit = member.parent / ".git"
        admin = Path(dotgit.read_text().strip().removeprefix("gitdir: "))
        dotgit.write_text("gitdir: " + os.path.relpath(admin, dotgit.parent) + "\n")
        (admin / "gitdir").write_text(os.path.relpath(dotgit, admin) + "\n")
        self.assertEqual(RUNNER["action_project"](member), member)
        self.assertEqual(self.store.scoped(member), [])

    def test_git_location_environment_cannot_change_scope(self):
        _, (canonical, member) = self.linked("a-wt", "z-wt")
        ident = self.record(member)
        self.assertEqual(self.store.scoped(member)[0]["canonical_project"], str(canonical))
        other = self.root / "other-repo"
        other.mkdir()
        self.git(other, "init")
        for name, value in (("GIT_DIR", str(other / ".git")), ("GIT_COMMON_DIR", str(other / ".git")),
                            ("GIT_CEILING_DIRECTORIES", str(member.parent))):
            with self.subTest(variable=name), patch.dict(os.environ, {name: value}):
                self.assertEqual(self.record(member), ident)
                result = subprocess.run([sys.executable, str(SCRIPT), "actions", "list", "--for", str(member)],
                                        capture_output=True, text=True, env=dict(self.env, **{name: value}))
                self.assertEqual((result.returncode, result.stdout.split(" ")[0]), (0, ident), result.stderr)

    def test_store_directories_are_fsynced_before_first_use(self):
        claude, backup = self.store.path.parent.parent, self.store.friction.parent
        mkdir = os.mkdir

        def raced(name, mode=0o777, *, dir_fd=None):
            mkdir(name, 0o700, dir_fd=dir_fd)  # Another writer wins the race but has not fsynced yet.
            raise FileExistsError(name)

        for case in ("existing", "raced"):
            with self.subTest(case=case):
                for directory in (self.store.path.parent, self.store.friction):
                    shutil.rmtree(directory, ignore_errors=True)
                if case == "existing":
                    for directory in (self.store.path.parent, self.store.friction):
                        directory.mkdir(mode=0o700, parents=True)
                events = []
                fsync = os.fsync

                def observe(fd):
                    info = os.fstat(fd)
                    events.append((info.st_dev, info.st_ino) if stat.S_ISDIR(info.st_mode) else "file")
                    return fsync(fd)

                with patch.object(os, "fsync", side_effect=observe), \
                        patch.object(os, "mkdir", side_effect=raced if case == "raced" else mkdir):
                    self.record()
                first_file = events.index("file")
                for parent in (claude, backup):
                    info = parent.stat()
                    self.assertIn((info.st_dev, info.st_ino), events[:first_file])

    def test_replaced_lock_entry_refuses_write(self):
        ident = self.record()
        before = self.store.path.read_bytes()
        lock = self.store.path.with_suffix(".json.lock")
        flock = actions.fcntl.flock

        def replace_lock(fd, operation):
            flock(fd, operation)
            lock.rename(lock.with_name("displaced.lock"))
            lock.touch(mode=0o600)

        with patch.object(actions.fcntl, "flock", side_effect=replace_lock), \
                self.assertRaisesRegex(ValueError, "lock was replaced"):
            self.store.mark(self.project, ident, "done")
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_spurious_enoent_from_concurrent_lock_creation_is_retried(self):
        self.record()
        lock = self.store.path.with_suffix(".json.lock")
        lock.unlink()
        real, failures = os.open, []

        def racing(path, flags, *args, **kwargs):
            if path == lock.name and flags & os.O_CREAT and len(failures) < 3:
                failures.append(path)
                raise FileNotFoundError(path)  # What Darwin reports when two creators race.
            return real(path, flags, *args, **kwargs)

        with patch.object(os, "open", side_effect=racing):
            self.record(literal="ls -a")
        self.assertEqual(len(failures), 3)
        self.assertEqual(len(self.store.scoped(self.project)), 2)

    def test_reported_extended_acl_refuses_store_files_on_any_platform(self):
        self.record()
        before = self.store.path.read_bytes()
        for path in (self.store.path.parent, self.store.path, self.secret.parent, self.secret):
            identity = path.stat()
            with self.subTest(path=path.name), patch.object(sys, "platform", "darwin"), \
                    patch.object(actions, "_has_extended_acl",
                                 side_effect=lambda fd, **_: os.path.samestat(os.fstat(fd), identity)):
                with self.assertRaisesRegex(ValueError, "ACL"):
                    self.record(literal="ls -a")
                with self.assertRaisesRegex(ValueError, "ACL"):
                    self.store.scoped(self.project)
            self.assertEqual(self.store.path.read_bytes(), before)
