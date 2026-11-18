import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest


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

    def refused(self, reason, *, cwd=None, project=None, record=None, **env):
        before = self.git(self.primary, 'worktree', 'list', '--porcelain')
        refs = self.git(self.primary, 'show-ref')
        args = ['undo', str(record)] if record else ['apply', '--path', str(self.target)]
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
