"""Exercise wrappers against isolated Git layouts."""
import subprocess

from test_scripts import StubCase, write


class PortabilityTests(StubCase):
    def setUp(self):
        super().setUp()
        self.env.update(GIT_AUTHOR_NAME='Test', GIT_AUTHOR_EMAIL='test@example.invalid',
                        GIT_COMMITTER_NAME='Test', GIT_COMMITTER_EMAIL='test@example.invalid',
                        FINAL='VERDICT: NO ISSUES')
        self.repo = self.root / 'git repo'
        self.repo.mkdir()
        self.git('-c', 'init.defaultBranch=main', 'init', '-q')
        self.commit('initial')

    def git(self, *args, repo=None):
        return subprocess.run(['git', '-C', str(repo or self.repo), *args], env=self.env,
                              capture_output=True, text=True, check=True).stdout.strip()

    def commit(self, value):
        write(self.repo / 'tracked', value + '\n')
        self.git('add', 'tracked')
        self.git('commit', '-qm', value)

    def remote(self, name, symbolic=False):
        self.git('update-ref', 'refs/remotes/origin/' + name, 'HEAD')
        if symbolic:
            self.git('symbolic-ref', 'refs/remotes/origin/HEAD', 'refs/remotes/origin/' + name)

    def review(self, *args, code=0, repo=None):
        return self.run_script('codex-review', 'diff', '-C', repo or self.repo, *args, code=code)

    def test_default_symbolic_main_and_report(self):
        self.remote('main', symbolic=True)
        self.commit('second')
        self.commit('third')
        result = self.review()
        self.assertIn('--base origin/main', self.calls()[-1]['prompt'])
        self.assertIn('Base: origin/main (default)', result.stdout)
        self.assertLessEqual(len(result.stdout.splitlines()), 25)

    def test_default_master_and_missing_remote_fallback(self):
        self.remote('master')
        self.commit('second')
        self.review()
        self.assertIn('--base origin/master', self.calls()[-1]['prompt'])
        self.git('update-ref', '-d', 'refs/remotes/origin/master')
        write(self.repo / 'dirty', 'change')
        self.review()
        self.assertIn('--uncommitted', self.calls()[-1]['prompt'])

    def test_clean_and_dirty_uncommitted(self):
        self.remote('main', symbolic=True)
        result = self.review(code=2)
        self.assertIn('nothing to review', result.stdout)
        self.assertTrue(result.stdout.endswith('STATUS: REVIEW FAILED\n'))
        self.assertFalse(self.record.exists())
        self.assertIn('nothing to review', self.review('--uncommitted', code=2).stdout)
        self.review('--base', 'origin/main')
        self.review('--commit', 'HEAD')
        write(self.repo / 'dirty', 'change')
        self.review()
        self.assertIn('--uncommitted', self.calls()[-1]['prompt'])

    def test_dispatch_excludes_output_once(self):
        exclude = self.repo / '.git/info/exclude'
        exclude.write_bytes(b'custom')
        self.run_script('codex-dispatch', '-C', self.repo, self.brief)
        self.run_script('codex-dispatch', '-C', self.repo, self.brief)
        self.assertEqual(exclude.read_bytes(), b'custom\nout/\n')
        self.assertNotIn('out/', self.git('status', '--porcelain'))

    def test_existing_ignore_and_external_output(self):
        write(self.repo / '.gitignore', 'out/\n')
        exclude = self.repo / '.git/info/exclude'
        before = exclude.read_bytes()
        self.review('--uncommitted')
        self.assertEqual(exclude.read_bytes(), before)
        self.run_script('codex-dispatch', '-C', self.repo, '-o', self.root / 'external', self.brief)
        self.assertEqual(exclude.read_bytes(), before)

    def test_external_output_does_not_change_exclude(self):
        exclude = self.repo / '.git/info/exclude'
        before = exclude.read_bytes()
        self.run_script('codex-dispatch', '-C', self.repo, '-o', self.root / 'external', self.brief)
        self.assertEqual(exclude.read_bytes(), before)

    def test_non_git_and_linked_worktree(self):
        self.review('--uncommitted', repo=self.work)
        self.run_script('codex-dispatch', '-C', self.work, self.brief)
        self.assertFalse((self.work / '.git').exists())
        linked = self.root / 'linked'
        self.git('worktree', 'add', '-qb', 'linked', str(linked))
        write(linked / 'dirty', 'change')
        self.review(repo=linked)
        self.assertIn('out/', (self.repo / '.git/info/exclude').read_text().splitlines())
        self.assertNotIn('out/', self.git('status', '--porcelain', repo=linked))
