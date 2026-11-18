import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/worktree-prune'


class WorktreePruneTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.primary, self.target = self.root / 'primary', self.root / 'target'
        self.home = self.root / 'config'
        self.journal = self.home / 'audits/worktree-prunes'
        self.old = int(time.time()) - 3 * 86400
        self.env = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
        self.env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
                        CLAUDE_CONFIG_DIR=str(self.home), GIT_AUTHOR_NAME='Fixture',
                        GIT_COMMITTER_NAME='Fixture', GIT_AUTHOR_EMAIL='test@example.invalid',
                        GIT_COMMITTER_EMAIL='test@example.invalid',
                        GIT_AUTHOR_DATE=f'@{self.old} +0000', GIT_COMMITTER_DATE=f'@{self.old} +0000')
        self.git(self.root, 'init', '-qb', 'main', self.primary)
        (self.primary / 'tracked').write_text('committed\n')
        (self.primary / '.gitignore').write_text('private.local\nbuild/\n')
        (self.primary / '.gitattributes').write_text('tracked filter=fixture\n')
        self.git(self.primary, 'add', '.')
        self.git(self.primary, 'commit', '-qm', 'fixture')
        self.git(self.primary, 'worktree', 'add', '-qb', 'topic', self.target)
        self.common = self.primary / '.git'
        self.admin = Path(self.git(self.target, 'rev-parse', '--absolute-git-dir'))
        self.age()

    def git(self, path, *args):
        return subprocess.run(['git', '-C', str(path), *map(str, args)], env=self.env,
                              check=True, capture_output=True, text=True).stdout.strip()

    def age(self):
        for path in [self.target, *self.target.rglob('*'), self.admin / 'HEAD',
                     self.admin / 'index', self.admin / 'logs/HEAD', self.common / 'logs/refs/heads/topic']:
            if path.exists():
                os.utime(path, (self.old, self.old), follow_symlinks=False)

    def refused(self, reason, *, cwd=None, project=None, record=None, path=None, **env):
        before = self.git(self.primary, 'worktree', 'list', '--porcelain')
        refs = self.git(self.primary, 'show-ref')
        args = ['undo', str(record)] if record else ['apply', '--path', str(path or self.target)]
        result = subprocess.run([str(SCRIPT), *args, '--project', str(project or self.primary)],
                                env=dict(self.env, **env), cwd=cwd or self.primary,
                                capture_output=True, text=True)
        self.assertEqual((result.returncode, result.stdout), (2, ''), result.stderr)
        self.assertIn(reason, result.stderr)
        self.assertEqual(self.git(self.primary, 'worktree', 'list', '--porcelain'), before)
        self.assertEqual(self.git(self.primary, 'show-ref'), refs)

    def test_eligible_apply_and_protected_directories(self):
        self.refused('eligible worktree')
        self.assertFalse(self.home.exists())
        nested = self.target / 'nested'
        nested.mkdir()
        for cwd in (self.target, nested):
            self.refused('current directory', cwd=cwd)
        self.refused('supplied project', project=nested)

    def test_hidden_ignored_and_generated_entries(self):
        tracked = self.target / 'tracked'
        tracked.write_text('local edits\n')
        for flag in ('assume-unchanged', 'skip-worktree'):
            self.git(self.target, 'update-index', '--' + flag, 'tracked')
            self.age()
            self.refused('hidden entries')
            self.git(self.target, 'update-index', '--no-' + flag, 'tracked')
        self.git(self.target, 'restore', 'tracked')
        for name in ('private.local', 'build'):
            entry = self.target / name
            entry.mkdir() if name == 'build' else entry.touch()
            self.age()
            self.refused('worktree has')
            entry.rmdir() if entry.is_dir() else entry.unlink()
        self.git(self.target, 'init', '-q', self.target / 'nested')
        self.age()
        self.refused('worktree has')

    def test_overrides_do_not_hide_changes_or_enable_filters(self):
        (self.target / 'untracked').write_text('local edits\n')
        self.git(self.target, 'config', 'status.showUntrackedFiles', 'no')
        self.age()
        self.refused('worktree has changes', GIT_INDEX_FILE=str(self.common / 'index'),
                     GIT_DIR=str(self.common), GIT_WORK_TREE=str(self.primary))
        self.git(self.target, 'config', 'filter.fixture.clean', 'false')
        self.refused('unsafe Git configuration')

    def test_locked_recent_sparse_or_unmerged(self):
        self.git(self.primary, 'worktree', 'lock', self.target)
        self.refused('locked')
        self.git(self.primary, 'worktree', 'unlock', self.target)
        (self.target / 'tracked').touch()
        self.refused('not idle')
        self.git(self.target, 'config', 'core.sparseCheckout', 'true')
        self.refused('sparse checkout')
        self.git(self.target, 'config', '--unset', 'core.sparseCheckout')
        self.git(self.target, 'commit', '--allow-empty', '-qm', 'unmerged')
        self.age()
        self.refused('not provably merged')

    def test_undo_refuses_moved_branch_and_disables_recreation(self):
        tip = self.git(self.target, 'rev-parse', 'HEAD')
        self.git(self.primary, 'worktree', 'remove', self.target)
        self.journal.mkdir(parents=True, mode=0o700)
        record = self.journal / 'fixture.json'
        record.write_text(json.dumps(dict(v=1, phase='removed', project=str(self.primary),
                                          common=str(self.common), path=str(self.target),
                                          branch='refs/heads/topic', branch_tip=tip)))
        record.chmod(0o600)
        self.refused('disabled pending journal', record=record)
        self.git(self.primary, 'commit', '--allow-empty', '-qm', 'new tip')
        self.git(self.primary, 'branch', '-f', 'topic', 'main')
        self.refused('branch tip no longer equals', record=record)
        self.assertFalse(self.target.exists())

    def test_main_and_unregistered_directories(self):
        self.refused('not an eligible linked worktree', path=self.primary, cwd=self.root,
                     project=self.target)
        unrelated = self.root / 'unregistered'
        unrelated.mkdir()
        self.refused('not an eligible linked worktree', path=unrelated)

    def test_wrong_common_and_forged_admin(self):
        unrelated = self.root / 'unrelated'
        self.git(self.root, 'init', '-q', unrelated)
        (self.admin / 'commondir').write_text(f'{unrelated / ".git"}\n')
        self.refused('inconsistent Git directories')
        (self.admin / 'commondir').write_text('../..\n')
        for fake in (self.root / 'fake', self.admin.with_name('fake')):
            with self.subTest(fake=fake):
                shutil.copytree(self.admin, fake)
                (fake / 'commondir').write_text(f'{self.common}\n')
                (self.target / '.git').write_text(f'gitdir: {fake}\n')
                self.refused('registration' if fake.parent == self.admin.parent
                             else 'inconsistent Git directories')

    def test_registered_worktrees_overlap_in_either_direction(self):
        nested = self.target / 'nested'
        self.git(self.primary, 'worktree', 'add', '-qb', 'nested', nested)
        self.refused('overlaps another registered worktree')
        self.refused('overlaps another registered worktree', path=nested)

    def check_alias(self, alias):
        self.refused('alias', path=alias)
        self.refused('current directory', cwd=alias)
        self.refused('supplied project', project=alias)

    def test_symlink_alias(self):
        alias = self.target.with_name('alias')
        alias.symlink_to(self.target, target_is_directory=True)
        self.check_alias(alias)

    def test_case_alias(self):
        alias = self.target.with_name('TARGET')
        if not alias.exists():
            self.skipTest('case-sensitive volume')
        self.check_alias(alias)

    def test_detached_head_and_missing_branch(self):
        self.git(self.target, 'checkout', '-q', '--detach')
        self.refused('detached')
        self.git(self.target, 'checkout', '-q', 'topic')
        (self.common / 'refs/heads/topic').unlink()
        self.refused('Git check failed')

    def test_staged_and_unstaged_edits(self):
        (self.target / 'tracked').write_text('dirty\n')
        self.age()
        self.refused('changes to tracked bytes')
        self.git(self.target, 'add', 'tracked')
        self.age()
        self.refused('index does not equal HEAD')

    def test_same_size_and_mtime_edit(self):
        tracked = self.target / 'tracked'
        old = tracked.stat()
        self.git(self.target, 'update-index', '--refresh')
        os.utime(self.admin / 'index', (self.old + 60, self.old + 60))
        tracked.write_bytes(b'otherdata\n')
        os.utime(tracked, ns=(old.st_atime_ns, old.st_mtime_ns))
        self.assertEqual(tracked.stat().st_size, old.st_size)
        self.assertEqual(self.git(self.target, '-c', 'core.trustctime=false', 'status', '--porcelain'), '')
        self.refused('changes to tracked bytes')

    def test_executable_bit_change(self):
        (self.target / 'tracked').chmod(0o755)
        self.refused('worktree has changes')

    def test_gitlink(self):
        tip = self.git(self.target, 'rev-parse', 'HEAD')
        self.git(self.target, 'update-index', '--add', '--cacheinfo', f'160000,{tip},submodule')
        self.git(self.target, 'commit', '-qm', 'gitlink')
        self.git(self.primary, 'merge', '--ff-only', 'topic')
        self.age()
        self.refused('HEAD has submodules')

    def test_intent_to_add(self):
        (self.target / 'new').touch()
        self.git(self.target, 'add', '--intent-to-add', 'new')
        self.age()
        self.refused('index has hidden entries')

    def test_private_refs_and_shared_stash(self):
        tip = self.git(self.target, 'rev-parse', 'HEAD')
        self.git(self.primary, 'update-ref', 'refs/stash', tip)
        self.refused('eligible worktree')
        for name in ('refs/worktree/private', 'refs/bisect/private', 'refs/rewritten/private',
                     'refs/stash', 'packed-refs'):
            with self.subTest(name=name):
                ref = self.admin / name
                ref.parent.mkdir(parents=True, exist_ok=True)
                ref.write_text(f'{tip}\n')
                self.refused('worktree has private refs')
                ref.unlink()

    def test_unretained_and_malformed_head_reflog(self):
        self.git(self.target, 'checkout', '-q', '--detach')
        self.git(self.target, 'commit', '--allow-empty', '-qm', 'reflog only')
        self.git(self.target, 'checkout', '-q', 'topic')
        self.age()
        self.refused('reflog has unretained commits')
        (self.admin / 'logs/HEAD').write_bytes(b'malformed\n')
        self.refused('cannot parse worktree HEAD reflog')

    def test_preflight_never_runs_repository_commands(self):
        marker = self.root / 'executed'
        commands = self.target / 'commands'
        commands.mkdir()
        for name in ('git', 'post-checkout'):
            executable = commands / name
            executable.write_text(f'#!/bin/sh\ntouch "{marker}"\n')
            executable.chmod(0o755)
        command = commands / 'post-checkout'
        self.git(self.target, 'config', 'core.hooksPath', commands)
        self.git(self.target, 'config', 'core.fsmonitor', command)
        self.age()
        env = dict(PATH=f'{commands}{os.pathsep}{self.env["PATH"]}', KAIZEN_GIT=str(commands / 'git'))
        self.refused('worktree has changes', **env)
        self.git(self.target, 'config', 'filter.fixture.clean', command)
        self.refused('unsafe Git configuration', **env)
        self.assertFalse(marker.exists())

    def script_functions(self):
        with patch.object(sys, 'path', [str(SCRIPT.parent), *sys.path]):
            return runpy.run_path(str(SCRIPT))['apply'].__globals__

    def test_git_resolver_uses_absolute_path(self):
        resolve_git = self.script_functions()['resolve_git']
        with patch.dict(os.environ, {'PATH': str(self.target), 'KAIZEN_GIT': 'git'}):
            locations = ('/usr/bin/git', '/opt/homebrew/bin/git', '/usr/local/bin/git')
            self.assertIn(resolve_git(self.primary), [Path(path).resolve() for path in locations])

    def test_identity_swap_between_passes(self):
        functions = self.script_functions()
        preflight = functions['preflight']
        calls = []

        def swap(*args):
            result = preflight(*args)
            if not calls:
                retired = self.target.with_name('retired')
                self.target.rename(retired)
                shutil.copytree(retired, self.target)
            calls.append(result)
            return result

        args = type('Args', (), dict(project=str(self.primary), path=str(self.target)))
        with patch.dict(functions, {'preflight': swap}):
            with self.assertRaisesRegex(functions['Refused'], 'identity .* changed'):
                functions['apply'](args)
        self.assertEqual(len(calls), 2)
