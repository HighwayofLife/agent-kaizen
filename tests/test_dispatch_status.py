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

    def test_optional_facts_and_strict_dirty_status(self):
        other = self.root / 'linked tree'
        self.git('worktree', 'add', '-qb', 'topic', str(other))
        self.git('worktree', 'lock', str(other))
        (other / 'out').mkdir()
        (other / 'out' / 'private').write_text('data')
        output = self.run_script('dispatch-status', '--worktree-facts').stdout
        facts = output.split('WORKTREE FACTS (advisory)')[1]
        self.assertIn('primary=true linked=false locked=false detached=false clean=true merged=true', facts)
        self.assertIn('primary=false linked=true locked=true detached=false clean=false merged=true', facts)
        self.assertNotIn(str(other), output.split('WORKTREE FACTS (advisory)')[0])
        selected = self.run_script('dispatch-status', '--worktree-facts', other).stdout
        self.assertNotIn('primary=true', selected.split('WORKTREE FACTS (advisory)')[1])

    def test_detached_and_unmerged(self):
        other = self.root / 'linked'
        self.git('worktree', 'add', '-qb', 'topic', str(other))
        subprocess.run(['git', '-C', str(other), 'commit', '--allow-empty', '-qm', 'topic'],
                       env=self.env, check=True)
        subprocess.run(['git', '-C', str(other), 'checkout', '-q', '--detach'], env=self.env, check=True)
        output = self.run_script('dispatch-status', '--worktree-facts', other).stdout
        self.assertIn('branch=unknown', output)
        self.assertIn('detached=true clean=true merged=false', output)
        self.git('checkout', '-q', '--detach')
        output = self.run_script('dispatch-status', '--worktree-facts', other).stdout
        self.assertIn('merged=unknown', output)

    def test_fallback_rejects_quoted_path_and_no_git(self):
        other = self.root / 'line\nbreak'
        self.git('worktree', 'add', '-qb', 'topic', str(other))
        real = shutil.which('git', path=os.environ['PATH'])
        wrapper = self.bin / 'git'
        wrapper.write_text('#!/bin/sh\ncase "$*" in *"worktree list"*" -z"*) exit 129;; esac\n'
                           'exec "%s" "$@"\n' % real)
        wrapper.chmod(0o755)
        output = self.run_script('dispatch-status', '--worktree-facts').stdout
        self.assertIn(': unknown', output.split('WORKTREE FACTS (advisory)')[1])
        wrapper.write_text('#!/bin/sh\nexit 127\n')
        output = self.run_script('dispatch-status', '--worktree-facts').stdout
        self.assertIn(': unknown', output.split('WORKTREE FACTS (advisory)')[1])

    def test_fallback_plain_path_and_nul_unusual_path(self):
        other = self.root / 'line\nbreak'
        self.git('worktree', 'add', '-qb', 'topic', str(other))
        output = self.run_script('dispatch-status', '--worktree-facts').stdout
        self.assertIn(str(other), output.split('WORKTREE FACTS (advisory)')[1])
        self.git('worktree', 'remove', str(other))
        other = self.root / 'plain space'
        self.git('worktree', 'add', '-qb', 'topic2', str(other))
        real = shutil.which('git', path=os.environ['PATH'])
        wrapper = self.bin / 'git'
        wrapper.write_text('#!/bin/sh\ncase "$*" in *"worktree list"*" -z"*) exit 129;; esac\n'
                           'exec "%s" "$@"\n' % real)
        wrapper.chmod(0o755)
        output = self.run_script('dispatch-status', '--worktree-facts').stdout
        self.assertIn(str(other), output.split('WORKTREE FACTS (advisory)')[1])

    def test_missing_helper_preserves_default_command(self):
        standalone = self.bin / 'dispatch-status'
        shutil.copy(Path(__file__).resolve().parents[1] / 'scripts/dispatch-status', standalone)
        for args in ([], ['--worktree-facts']):
            result = subprocess.run([str(standalone), *args], cwd=self.work, env=self.env,
                                    capture_output=True, text=True, check=True)
            self.assertIn('DIRTY WORKTREES', result.stdout)
            if args:
                self.assertIn('Worktree facts unavailable', result.stdout)

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
