"""Exercise LocalSearch preflight and recovery on disposable Git output."""
import io
import os
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
with patch.object(sys, 'path', [str(SCRIPTS), *sys.path]):
    FIX = runpy.run_path(str(SCRIPTS / 'host-fix'))['main'].__globals__
ID = 'linux-localsearch'


class HostFixTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.project = self.root / 'project'
        self.config = self.project / 'docs/kaizen/config.json'
        self.config.parent.mkdir(parents=True)
        self.output = self.project / 'build'
        self.output.mkdir()
        self.env = dict(CLAUDE_CONFIG_DIR=str(self.root / 'config'), KAIZEN_BACKUP_DIR=str(self.root / 'backup'),
                        GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
        for context in (patch.dict(os.environ, self.env), patch.dict(FIX, PLATFORM='linux')):
            context.start()
            self.addCleanup(context.stop)
        self.git('init', '-q')
        (self.project / '.gitignore').write_text('build/\nprivate/\n')
        self.git('add', '.gitignore')
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture')
        runner = runpy.run_path(str(SCRIPTS / 'kaizen-scheduled'))
        self.store = FIX['HostActions'](runner['audits_dir'](), runner['backup_root'](),
                                        runner['action_project'], runner['key'])

    def git(self, *args, directory=None):
        subprocess.run(['git', '-C', str(directory or self.project), *args], check=True, capture_output=True)

    def record(self):
        return self.store.record(self.project, ID, self.output, 'fixture evidence', path=True)

    def apply(self, path='build', key=None):
        return FIX['apply'](SimpleNamespace(project=str(self.project), catalog_id=ID, path=str(path)),
                            action_id=key)

    def undo(self, record):
        FIX['undo'](SimpleNamespace(project=str(self.project), record=str(record)))

    @contextmanager
    def writes(self):
        if sys.platform == 'linux':
            with patch.dict(FIX, LINUX_WRITES=True):
                yield FIX['publish_marker']
            return
        # Model the anonymous inode on macOS with a disposable hard-link source.
        paths = {}

        def stage(directory, stamp):
            fd, path = tempfile.mkstemp(dir=self.root)
            paths[fd] = Path(path)
            os.write(fd, stamp)
            return fd

        def publish(directory, fd):
            os.link(paths[fd], FIX['MARKER'], dst_dir_fd=directory)
            paths[fd].unlink()

        with patch.dict(FIX, LINUX_WRITES=True, stage_marker=stage, publish_marker=publish):
            yield publish

    def refusal(self, reason, path='build'):
        with self.assertRaisesRegex(FIX['Refused'], reason):
            self.apply(path)

    def test_open_action_is_eligible_and_cli_writes_stay_dark(self):
        self.record()
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            for args in (['apply', '--catalog-id', ID, '--path', 'build'], ['undo', 'record.json']):
                with self.assertRaises(SystemExit) as stopped:
                    FIX['main']([*args, '--project', str(self.project)])
                self.assertEqual(stopped.exception.code, 2)
        self.assertEqual(stdout.getvalue(), '')
        self.assertEqual(stderr.getvalue().count(FIX['PENDING']), 2)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_missing_dismissed_and_blocked_policy(self):
        self.refusal('no open eligible action')
        ident = self.record()
        for config in ('{', '{"hostActions":"off"}', '{"frictionOutputDirs":["../build"]}'):
            with self.subTest(config=config):
                self.config.write_text(config)
                with self.assertRaises((ValueError, FIX['Refused'])):
                    self.apply()
        self.config.unlink()
        self.store.mark(self.project, ident, 'dismiss')
        self.refusal('no open eligible action')

    def test_nested_policy_and_independent_git_refusals(self):
        self.record()
        nested = self.project / 'build/member'
        self.git('worktree', 'add', '-q', '--detach', str(nested))
        (nested / 'build').mkdir()
        config = nested / 'docs/kaizen/config.json'
        config.parent.mkdir(parents=True)
        config.write_text('{"hostActions":"off"}')
        self.refusal('does not allow host actions', nested / 'build')
        config.unlink()
        self.refusal('eligible output', nested / 'build')
        self.refusal('contains a worktree')
        self.git('worktree', 'remove', '--force', str(nested))
        self.git('init', '-q', directory=self.output)
        self.refusal('foreign repository')
        (self.output / 'tracked').touch()
        os.rename(self.output / '.git', self.root / 'nested-git')
        self.git('add', '-f', 'build/tracked')
        self.refusal('no tracked files')

    def test_nested_custom_output_checks_each_worktree_relative_path(self):
        nested = self.output / 'member'
        self.git('worktree', 'add', '-q', '--detach', str(nested))
        with (nested / '.gitignore').open('a') as stream:
            stream.write('custom/\n')
        target = nested / 'custom'
        target.mkdir()
        (self.project / 'custom').mkdir()
        inner = nested / 'docs/kaizen/config.json'
        inner.parent.mkdir(parents=True)
        inner.write_text('{"frictionOutputDirs":["custom"]}')
        self.store.record(self.project, ID, target, 'fixture evidence', path=True)
        self.config.write_text('{"frictionOutputDirs":["custom"]}')
        self.refusal('recognized output directory', target)
        self.config.write_text('{"frictionOutputDirs":["build/member/custom"]}')
        self.refusal('eligible output', target)

    def test_overlong_policy_paths_are_refused(self):
        self.record()
        for entry in ('x/' * 65 + 'leaf', 'x' * 4097):
            with self.subTest(length=len(entry)):
                self.config.write_text('{"frictionOutputDirs":["' + entry + '"]}')
                self.refusal('invalid project output directories')

    def test_prefix_walk_checks_deadline(self):
        self.config.write_text('{"frictionOutputDirs":["one/two/three"]}')
        with patch.object(FIX['time'], 'monotonic', side_effect=[0, 20]):
            with self.assertRaisesRegex(FIX['Refused'], 'deadline'):
                FIX['check_policy'](self.root / 'config.json', {self.project: Path('build')},
                                    'build', ['build'], lambda _: True, 20)

    def test_existing_marker_is_noop_before_policy_and_candidate(self):
        marker = self.output / FIX['MARKER']
        marker.symlink_to(self.config)
        self.config.write_text('{')
        with self.writes(), redirect_stdout(io.StringIO()) as out:
            self.apply()
        self.assertIn('already present', out.getvalue())
        self.assertTrue(marker.is_symlink())

    def test_publish_after_directory_move_is_rolled_back(self):
        self.record()
        moved = self.root / 'moved'
        marker = self.output / FIX['MARKER']
        with self.writes() as link:
            def publish(directory, fd):
                self.output.rename(moved)
                self.output.mkdir()
                marker.write_text('replacement')
                link(directory, fd)

            with patch.dict(FIX, publish_marker=publish):
                self.refusal('directory identity changed')
        self.assertFalse((moved / FIX['MARKER']).exists())
        self.assertEqual(marker.read_text(), 'replacement')

    def test_roots_sensitive_unignored_and_aliases(self):
        for name in ('private', 'out'):
            (self.project / name).mkdir()
        (self.project / 'alias').symlink_to(self.output, target_is_directory=True)
        (self.root / 'foreign').mkdir()
        for path, reason in (('.', 'root'), ('private', 'sensitive'), ('out', 'ignored'),
                             ('alias', 'symlink'), ('alias/../build', 'traversal'),
                             (self.root / 'foreign', 'outside')):
            with self.subTest(path=path):
                self.refusal(reason, path)

    def test_directory_open_rejects_replacement(self):
        original = self.output.lstat()
        self.output.rename(self.root / 'original-build')
        self.output.mkdir()
        with self.assertRaisesRegex(FIX['Refused'], 'directory identity changed'):
            with FIX['checked_directory'](self.output, original):
                self.fail('opened a replacement directory')

    def test_apply_recovers_at_publish_and_record_boundaries(self):
        write = FIX['write_record']
        for crash_at in ('before-publish', 'after-publish', 'apply-pending', 'applied'):
            with self.subTest(crash_at=crash_at), self.writes() as link:
                target = self.project / crash_at / 'build'
                target.mkdir(parents=True)
                marker = target / FIX['MARKER']
                ident = self.store.record(self.project, ID, target, 'fixture evidence', path=True)
                key = None if crash_at == 'after-publish' else ident

                def publish(directory, fd):
                    if crash_at != 'before-publish':
                        link(directory, fd)
                    if crash_at.endswith('publish'):
                        raise InterruptedError()

                def persist(directory, name, store, record):
                    if record['phase'] != crash_at:
                        return write(directory, name, store, record)
                    with patch.object(os, 'replace', side_effect=InterruptedError):
                        write(directory, name, store, record)

                with patch.dict(FIX, publish_marker=publish, write_record=persist), self.assertRaises(InterruptedError):
                    self.apply(target, key)
                self.assertEqual(marker.exists(), crash_at in ('after-publish', 'applied'))
                before = marker.stat() if marker.exists() else None
                if crash_at == 'before-publish':
                    marker.write_text('foreign')
                    marker.chmod(0o600)
                    with self.assertRaisesRegex(FIX['Refused'], 'changed or replaced'):
                        self.apply(target, key)
                    self.assertEqual(marker.read_text(), 'foreign')
                    marker.unlink()
                with redirect_stdout(io.StringIO()):
                    record = self.apply(target, key)
                self.assertEqual(marker.stat().st_mode & 0o777, 0o600)
                if before:
                    self.assertEqual(marker.stat().st_ino, before.st_ino)
                self.undo(record)
                self.assertFalse(marker.exists())

    def test_direct_undo_is_retryable_after_opt_out_and_interruption(self):
        key = self.record()
        marker = self.output / FIX['MARKER']
        with self.writes():
            record = self.apply()
            self.config.write_text('{"hostActions":"off"}')
            self.store.mark(self.project, key, 'dismiss')
            persist = FIX['write_record']

            def stop_after_unlink(directory, name, store, data):
                if data['phase'] == 'undone':
                    raise InterruptedError()
                persist(directory, name, store, data)

            with patch.dict(FIX, write_record=stop_after_unlink):
                with self.assertRaises(InterruptedError):
                    self.undo(record)
            self.assertFalse(marker.exists())
            self.undo(record)
            self.undo(record)

    def test_foreign_markers_and_forged_records_are_preserved(self):
        self.record()
        marker = self.output / FIX['MARKER']
        with self.writes():
            record = self.apply()
            original = record.read_bytes()
            record.write_bytes(original.replace(b'"applied"', b'"undone"'))
            with self.assertRaisesRegex(FIX['Refused'], 'authentication'):
                self.undo(record)
            record.write_bytes(original)
            stamp = marker.read_bytes()
            marker.write_bytes(b'changed')
            with self.assertRaisesRegex(FIX['Refused'], 'changed or replaced'):
                self.undo(record)
            marker.unlink()
            marker.write_bytes(stamp)
            marker.chmod(0o600)
            with self.assertRaisesRegex(FIX['Refused'], 'changed or replaced'):
                self.undo(record)
            moved = self.root / 'moved'
            self.output.rename(moved)
            self.output.symlink_to(moved, target_is_directory=True)
            with self.assertRaisesRegex(FIX['Refused'], 'symlink'):
                self.undo(record)
            self.assertEqual((moved / marker.name).read_bytes(), stamp)

    def test_transaction_key_scope_and_concurrent_apply_undo(self):
        key = self.record()
        other = self.project / 'other/build'
        other.mkdir(parents=True)
        self.store.record(self.project, ID, other, 'other evidence', path=True)
        with self.writes():
            with self.assertRaisesRegex(FIX['Refused'], 'transaction key'):
                self.apply(other, key)
            record = self.apply(key=key)
            with self.assertRaisesRegex(FIX['Refused'], 'conflicting'):
                self.apply(other, key)
            with FIX['_directory'](record.parent, private=True) as state:
                FIX['lock_state'](state)
                for operation in (lambda: self.apply(key=key), lambda: self.undo(record)):
                    with self.assertRaisesRegex(FIX['Refused'], 'in progress'):
                        operation()
            self.undo(record)
            with self.assertRaisesRegex(FIX['Refused'], 'conflicting'):
                self.apply(key=key)
            self.assertEqual(list(other.iterdir()), [])
