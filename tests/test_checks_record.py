"""Tests for per-project completed check bookkeeping."""
import json
from datetime import datetime, timezone
from unittest.mock import patch
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/kaizen-scheduled'


class ChecksRecordTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / 'project'
        (self.project / 'docs/kaizen').mkdir(parents=True)
        self.env = dict(os.environ, CLAUDE_CONFIG_DIR=str(self.root / 'config'))

    def run_command(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), 'checks', *map(str, args)],
                              capture_output=True, text=True, env=self.env)

    def path(self, project=None):
        result = self.run_command('path', '--for', project or self.project)
        self.assertEqual(result.returncode, 0, result.stderr)
        return Path(result.stdout.strip())

    def test_record_backup_and_errors(self):
        path = self.path()
        self.assertFalse(path.parent.exists())
        self.assertEqual(self.run_command('record', '--for', self.project, 'models', '--date', '2026-01-01').returncode, 0)
        original = path.read_bytes()
        self.assertEqual(self.run_command('record', '--for', self.project, 'roster').returncode, 0)
        self.assertEqual(Path(str(path) + '.bak').read_bytes(), original)
        self.assertEqual(set(json.loads(path.read_text())), {'models', 'roster'})
        path.write_text('{')
        self.assertEqual(self.run_command('record', '--for', self.project, 'models').returncode, 2)
        self.assertEqual(path.read_text(), '{')
        for arguments in [('models', '--date', '9999-01-01'), ('bad',)]:
            self.assertEqual(self.run_command('record', '--for', self.project, *arguments).returncode, 2)
        self.assertEqual(self.run_command('record', '--for', self.root, 'models').returncode, 2)

    def test_default_date_is_the_local_date_experiment_check_uses(self):
        # Between them these zones differ from the UTC date at every hour of the day.
        checker = SCRIPT.parent / 'experiment-check'
        for zone in ('Etc/GMT-14', 'Etc/GMT+12'):
            with self.subTest(zone=zone):
                self.env['TZ'] = zone
                self.assertEqual(self.run_command('record', '--for', self.project, 'models').returncode, 0)
                result = subprocess.run([sys.executable, str(checker), '--project', str(self.project), '--checks',
                                         '--state-file', str(self.path())],
                                        capture_output=True, text=True, env=self.env)
                self.assertNotIn('invalid or future date', result.stdout + result.stderr)
                self.assertNotIn('models: never run', result.stdout)

    def test_record_pinned_local_date_ahead_of_utc(self):
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 1, 1, 12, tzinfo=timezone.utc) if tz else cls(2026, 1, 2, 2)

        module = runpy.run_path(str(SCRIPT))
        main = module['main']
        with patch.dict(os.environ, self.env), patch.dict(main.__globals__, datetime=Clock):
            self.assertEqual(main(['checks', 'record', '--for', str(self.project), 'models']), 0)
            self.assertEqual(main(['checks', 'record', '--for', str(self.project), 'models',
                                   '--date', '2026-01-03']), 2)
        self.assertEqual(json.loads(self.path().read_text())['models'], '2026-01-02')

    def test_concurrent_writers(self):
        path = self.path()
        for _ in range(10):
            path.unlink(missing_ok=True)
            processes = [subprocess.Popen([sys.executable, str(SCRIPT), 'checks', 'record', '--for',
                                          str(self.project), name], env=self.env, stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE) for name in ('models', 'roster')]
            for process in processes:
                _, err = process.communicate()
                self.assertEqual(process.returncode, 0, err)
            self.assertEqual(set(json.loads(path.read_text())), {'models', 'roster'})

    def test_linked_worktree(self):
        subprocess.run(['git', 'init', '-q', str(self.project)], check=True)
        subprocess.run(['git', '-C', str(self.project), '-c', 'user.name=Test', '-c', 'user.email=test@localhost', '-c', 'commit.gpgsign=false',
                        'commit', '--allow-empty', '-qm', 'initial'], check=True)
        worktree = self.root / 'worktree'
        subprocess.run(['git', '-C', str(self.project), 'worktree', 'add', '-qb', 'other', str(worktree)], check=True)
        (worktree / 'docs/kaizen').mkdir(parents=True)
        self.assertEqual(self.path(worktree), self.path())
        self.assertEqual(self.run_command('record', '--for', worktree, 'models').returncode, 0)
        old = os.environ.get('CLAUDE_CONFIG_DIR')
        os.environ['CLAUDE_CONFIG_DIR'] = self.env['CLAUDE_CONFIG_DIR']
        try:
            module = runpy.run_path(str(SCRIPT))
            projects, _ = module['discover'](self.root / 'none', self.root / 'none', {}, [self.project])
            self.assertEqual(self.path(), projects[0].folder / 'checks.json')
        finally:
            if old is None:
                del os.environ['CLAUDE_CONFIG_DIR']
            else:
                os.environ['CLAUDE_CONFIG_DIR'] = old


if __name__ == '__main__':
    unittest.main()
