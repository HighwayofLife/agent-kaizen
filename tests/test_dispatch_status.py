"""Offline checks for dirty worktree reporting."""
import os
import shutil
import subprocess
import time
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

    def test_old_git_without_z_still_discovers_worktrees(self):
        other = self.root / 'other worktree'
        self.git('worktree', 'add', '-qb', 'other', str(other))
        (other / 'task.md').write_text('changed')
        real = shutil.which('git', path=os.environ['PATH'])
        wrapper = self.bin / 'git'
        wrapper.write_text('#!/bin/sh\ncase "$*" in *"worktree list"*" -z"*) exit 129;; esac\n'
                           'exec "%s" "$@"\n' % real)
        wrapper.chmod(0o755)
        output = self.run_script('dispatch-status').stdout
        section = output.split('DIRTY WORKTREES (uncommitted paths outside out/, newest change age)')[1]
        self.assertIn(str(other), section)

    def test_running_match_needs_codex_dispatch_script(self):
        fake = self.bin / 'codex-dispatch'
        fake.write_text('#!/bin/sh\nsleep 5\n')
        fake.chmod(0o755)
        procs = [subprocess.Popen([str(fake)]),
                 subprocess.Popen(['python3', '-c', 'import time; time.sleep(5)', 'codex-dispatch.log'])]
        try:
            time.sleep(0.5)
            running = self.run_script('dispatch-status').stdout.split('LATEST REPORT')[0]
        finally:
            for proc in procs:
                proc.kill()
                proc.wait()
        self.assertIn(str(fake), running)
        self.assertNotIn('codex-dispatch.log', running)
