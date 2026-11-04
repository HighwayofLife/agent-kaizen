"""Offline checks for dirty worktree reporting."""
import subprocess
from pathlib import Path
from tests.test_scripts import StubCase


class DispatchStatusTests(StubCase):
    def git(self, *args):
        return subprocess.run(['git', *args], cwd=self.work, env=self.env,
                              capture_output=True, text=True, check=True)

    def setUp(self):
        super().setUp()
        self.git('init', '-q')
        self.git('config', 'user.email', 'test@example.invalid')
        self.git('config', 'user.name', 'Test')
        self.git('add', 'task.md')
        self.git('commit', '-qm', 'Initial subject')

    def test_clean_and_dirty_worktree(self):
        clean = self.run_script('dispatch-status', self.work).stdout
        heading = 'DIRTY WORKTREES (uncommitted paths outside out/, newest change age)'
        self.assertIn('RUNNING (pid, elapsed, command)', clean)
        self.assertIn('LATEST REPORT PER DIRECTORY\n', clean)
        self.assertEqual(clean.split(heading)[1].strip(), '')
        (self.work / 'task.md').unlink()
        (self.work / 'new file').write_text('new')
        (self.work / 'out').mkdir()
        (self.work / 'out' / 'ignored').write_text('ignored')
        dirty = self.run_script('dispatch-status', self.work).stdout.split(heading)[1].strip().splitlines()
        self.assertEqual(len(dirty), 1)
        self.assertRegex(dirty[0], r': 2 paths, \d+[mhd], Initial subject$')

    def test_default_discovers_linked_worktree(self):
        other = self.root / 'other worktree'
        self.git('worktree', 'add', '-qb', 'other', str(other))
        (other / 'task.md').write_text('changed')
        output = self.run_script('dispatch-status').stdout
        section = output.split('DIRTY WORKTREES (uncommitted paths outside out/, newest change age)')[1]
        self.assertIn(str(other), section)
        self.assertNotIn(str(self.work) + ':', section)
