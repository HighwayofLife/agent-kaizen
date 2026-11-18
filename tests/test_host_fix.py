"""Exercise the dark host-fix preflight and marker primitives on disposable Git output."""
import io
import os
from contextlib import redirect_stderr, redirect_stdout
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

    def apply(self, path='build'):
        FIX['apply'](SimpleNamespace(project=str(self.project), catalog_id=ID, path=str(path)))

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

    def test_exclusive_private_marker_and_identity(self):
        self.record()
        stamp = FIX['marker_stamp']()
        original = self.output.lstat()
        with FIX['checked_directory'](self.output, original) as fd:
            marker = self.output / FIX['MARKER']
            ident = FIX['create_marker'](fd, stamp)
            self.assertEqual(ident, FIX['marker_identity'](marker.stat()))
            self.assertEqual(marker.stat().st_mode & 0o777, 0o600)
            self.assertIsNone(FIX['create_marker'](fd, b'other'))
            with redirect_stdout(io.StringIO()) as out:
                self.apply()
            self.assertIn('already present', out.getvalue())
            self.assertEqual(marker.read_bytes(), stamp)
            marker.unlink()
            marker.symlink_to(self.config)
            self.assertIsNone(FIX['create_marker'](fd, stamp))
            self.assertTrue(marker.is_symlink())

        self.output.rename(self.root / 'original-build')
        self.output.mkdir()
        with self.assertRaisesRegex(FIX['Refused'], 'directory identity changed'):
            with FIX['checked_directory'](self.output, original):
                self.fail('opened a replacement directory')
