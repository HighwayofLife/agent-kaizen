import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/host-probe'
loader = importlib.machinery.SourceFileLoader('friction_host_probe', str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
probe_module = importlib.util.module_from_spec(spec)
loader.exec_module(probe_module)


class HostProbeTests(unittest.TestCase):
    def test_hidden_index_and_submodule_ignore_make_cleanliness_unknown(self):
        def git(root, *args):
            return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True)
        git(self.project, 'init', '-q')
        (self.project / 'tracked').write_text('original')
        git(self.project, 'add', 'tracked')
        git(self.project, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
            '-c', 'commit.gpgsign=false', 'commit', '-qm', 'initial')
        linked = self.root / 'linked'
        git(self.project, 'worktree', 'add', '-qb', 'linked', str(linked))
        self.assertTrue(self.probe().worktrees()[1]['clean'])
        for flag in ('assume-unchanged', 'skip-worktree'):
            with self.subTest(flag=flag):
                git(linked, 'update-index', '--' + flag, 'tracked')
                self.assertIsNone(self.probe().worktrees()[1]['clean'])
                git(linked, 'update-index', '--no-' + flag, 'tracked')
        for key in ('submodule.example.ignore', 'diff.ignoreSubmodules'):
            with self.subTest(key=key):
                git(linked, 'config', key, 'all')
                self.assertIsNone(self.probe().worktrees()[1]['clean'])
                git(linked, 'config', '--unset', key)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.project = self.root / 'project'
        self.project.mkdir()
        self.catalog = ROOT / 'scripts/friction-catalog.json'

    def probe(self, platform='linux'):
        return probe_module.Probe(self.project, platform, self.root / 'proc', self.catalog)

    def cli(self, out, *args):
        return subprocess.run([sys.executable, str(SCRIPT), '--project', str(self.project),
                               '--out', str(out), *args], capture_output=True, text=True)

    def test_private_unique_atomic_reports(self):
        out = self.root / 'audit'
        first = self.cli(out, '--json')
        second = self.cli(out)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        report = json.loads(first.stdout)
        self.assertNotIn(str(self.root), first.stdout)
        self.assertEqual(report['v'], 1)
        self.assertIn('generated_at', report)
        self.assertEqual(report['worktrees'], [])
        self.assertEqual(report['regenerable_dirs'], [])
        files = list(out.glob('host-probe-*.json'))
        self.assertEqual(len(files), 2)
        self.assertFalse(list(out.glob('.host-probe-*')))
        if os.name == 'posix':
            self.assertTrue(all(p.stat().st_mode & 0o077 == 0 for p in files))

    def test_shared_json_redacts_head(self):
        subprocess.run(['git', '-C', str(self.project), 'init', '-q'], check=True)
        subprocess.run(['git', '-C', str(self.project), '-c', 'user.name=Test',
                        '-c', 'user.email=test@example.invalid', '-c', 'commit.gpgsign=false', 'commit', '--allow-empty',
                        '-qm', 'initial'], check=True)
        head = subprocess.check_output(['git', '-C', str(self.project), 'rev-parse', 'HEAD'], text=True).strip()
        result = self.cli(self.root / 'audit', '--json')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(head, result.stdout)
        private = json.loads(next((self.root / 'audit').glob('*.json')).read_text())
        self.assertEqual(private['worktrees'][0]['head'], head)

    def test_worktree_registration_must_point_back(self):
        def git(*args):
            subprocess.run(['git', '-C', str(self.project), *args], check=True, capture_output=True)
        git('init', '-q')
        git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
            '-c', 'commit.gpgsign=false', 'commit', '--allow-empty', '-qm', 'initial')
        first, second = self.root / 'first', self.root / 'second'
        git('worktree', 'add', '-qb', 'first', str(first))
        git('worktree', 'add', '-qb', 'second', str(second))
        original = (second / '.git').read_text()
        (second / '.git').write_text((first / '.git').read_text())
        probe = self.probe()
        self.assertIsNone(probe.worktrees())
        self.assertIn('worktrees_unavailable', probe.warnings)
        (second / '.git').write_text(original)
        admin = Path(original.strip()[len('gitdir: '):])
        (admin / 'gitdir').write_text(str(first / '.git') + '\n')
        self.assertIsNone(self.probe().worktrees())

    def test_config_symlinked_parent_directories_refused(self):
        trees = [{'path': str(self.project), 'is_main': True}]
        outside = self.root / 'outside'
        (outside / 'kaizen').mkdir(parents=True)
        (outside / 'kaizen/config.json').write_text(json.dumps({'frictionOutputDirs': ['custom']}))
        (self.project / 'custom').mkdir()
        (self.project / 'docs').symlink_to(outside, target_is_directory=True)
        for linked in ('docs', 'kaizen'):
            for dir_fd_support in (os.supports_dir_fd, set()):
                probe = self.probe()
                with mock.patch.object(probe_module.os, 'supports_dir_fd', dir_fd_support), \
                     mock.patch.object(probe, 'git', side_effect=lambda root, *args: 'custom/\n' if args[0] == 'check-ignore' else ''):
                    self.assertEqual(probe.directories(trees), [])
                self.assertIn('output_config', probe.warnings)
            if linked == 'docs':
                (self.project / 'docs').unlink()
                (self.project / 'docs').mkdir()
                (self.project / 'docs/kaizen').symlink_to(outside / 'kaizen', target_is_directory=True)

    def test_output_refusal(self):
        target = self.root / 'target'
        target.mkdir()
        link = self.root / 'link'
        link.symlink_to(target, target_is_directory=True)
        self.assertNotEqual(self.cli(link).returncode, 0)
        self.assertEqual(list(target.iterdir()), [])
        file_path = self.root / 'file'
        file_path.write_text('occupied')
        self.assertNotEqual(self.cli(file_path / 'child').returncode, 0)

    def test_linux_findings_and_unavailable(self):
        probe = self.probe()
        with mock.patch.object(probe, 'command', side_effect=['mds\n', 'a\0b\0', None]), \
             mock.patch.object(probe, 'read_proc', return_value=1), \
             mock.patch.object(probe_module.shutil, 'disk_usage', return_value=mock.Mock(total=100, free=5)):
            report = probe.run()
        self.assertEqual({f['id'] for f in report['findings']}, {'inotify', 'low-disk'})
        self.assertTrue(all(isinstance(v, (int, float)) for f in report['findings'] for v in f['evidence'].values()))
        probe = self.probe()
        with mock.patch.object(probe, 'command', return_value=None):
            report = probe.run()
        self.assertIsNone(report['facts']['processes'])
        self.assertIsNone(report['facts']['inotify_max_user_watches'])
        self.assertIn('proc_unavailable', report['warnings'])

    def test_windows_catalogue_only_and_informational(self):
        probe = self.probe('windows')
        with mock.patch.object(probe, 'command', return_value='"MsMpEng.exe","1"\n"private.exe","2"\n'):
            report = probe.run()
        self.assertEqual(report['facts']['processes']['defender']['count'], 1)
        self.assertTrue(report['facts']['processes']['defender']['informational'])
        self.assertNotIn('private.exe', json.dumps(report))
        self.assertIn('inotify_unavailable', report['warnings'])

    def test_bounded_commands_and_budget(self):
        probe = self.probe()
        self.assertIsNone(probe.command([sys.executable, '-c', 'print("x" * 1100000)']))
        self.assertIn('command_output', probe.warnings)
        probe.deadline = time.monotonic() + 0.1
        self.assertIsNone(probe.command([sys.executable, '-c', 'import time; time.sleep(10)']))
        self.assertIn('timeout', probe.warnings)
        probe.deadline = 0
        self.assertIsNone(probe.command(['missing']))
        self.assertIn('budget', probe.warnings)

    def test_git_output_safety_and_worktree_identity(self):
        def git(*args):
            return subprocess.run(['git', '-C', str(self.project), *args],
                                  check=True, capture_output=True, text=True)
        git('init', '-q')
        git('config', 'commit.gpgsign', 'false')
        git('config', 'user.name', 'Test')
        git('config', 'user.email', 'test@example.invalid')
        (self.project / '.gitignore').write_text('build/\ndist/\nout/\ncoverage/\n')
        (self.project / 'seed').write_text('seed')
        git('add', '.')
        git('commit', '-qm', 'initial')
        for name in ('build', 'dist', 'coverage'):
            (self.project / name).mkdir()
            (self.project / name / 'data').write_text('abc')
        git('add', '-f', 'dist/data')
        (self.project / 'coverage' / '.git').mkdir()
        (self.project / 'out').symlink_to(self.project / 'build', target_is_directory=True)
        linked = self.root / 'linked'
        git('worktree', 'add', '-qb', 'linked', str(linked))
        probe = self.probe()
        trees = probe.worktrees()
        self.assertEqual({t['path'] for t in trees}, {str(self.project), str(linked)})
        directories = probe.directories(trees)
        # A nested repository makes the entire measurement unknown.
        self.assertIsNone(directories)
        (self.project / 'coverage' / '.git').rmdir()
        directories = probe.directories(trees)
        self.assertEqual([d['path'] for d in directories],
                         [str(self.project / 'build'), str(self.project / 'coverage')])
        self.assertEqual([d['size_bytes'] for d in directories], [3, 3])
        self.assertTrue(all(d['path'] != str(linked) for d in directories))

    def test_unknown_git_and_bounded_size(self):
        probe = self.probe()
        with mock.patch.object(probe, 'command', return_value=None):
            report = probe.run()
        self.assertIsNone(report['facts']['worktree_count'])
        self.assertIsNone(report['facts']['regenerable_bytes'])
        probe.deadline = 0
        self.assertIsNone(probe.size(self.project))

    def test_macos_index_exclusions_and_unknown(self):
        probe = self.probe('macos')
        output = self.project / 'build'
        output.mkdir()
        directory = {'path': str(output), 'worktree': str(self.project), 'size_bytes': 11 * 1024**3,
                     'excluded': {'nomedia': False, 'noindex_ancestor': False}}
        trees = [{'path': str(self.project), 'is_main': True}]
        def run(tm_output, marker=None, platform='macos'):
            directory['excluded'].pop('timemachine', None)
            directory['excluded'].pop('spotlight', None)
            if marker:
                marker.touch()
            probe.platform = platform
            def command(argv):
                if argv[0] == 'mdutil':
                    return 'Indexing enabled.\n'
                if argv[0] == 'tmutil':
                    self.assertEqual(argv, ['tmutil', 'isexcluded', str(output)])
                    return tm_output
                return 'mds\nbackupd\n'
            with mock.patch.object(probe, 'command', side_effect=command) as runner, \
                 mock.patch.object(probe, 'worktrees', return_value=trees), \
                 mock.patch.object(probe, 'directories', return_value=[directory]):
                report = probe.run()
            if marker:
                marker.unlink()
            return {f['catalog_id'] for f in report['findings']}, runner
        findings, _ = run('[Included] /output\n')
        self.assertIn('spotlight-output', findings)
        self.assertIn('timemachine-output', findings)
        findings, _ = run('[Excluded] /output\n', self.project / '.metadata_never_index')
        self.assertNotIn('spotlight-output', findings)
        self.assertNotIn('timemachine-output', findings)
        findings, _ = run(None, output / '.metadata_never_index')
        self.assertNotIn('spotlight-output', findings)
        self.assertNotIn('timemachine-output', findings)
        self.assertIsNone(directory['excluded']['timemachine'])
        self.assertIn('timemachine_unknown', probe.warnings)
        findings, runner = run('[Included] /output', platform='linux')
        self.assertNotIn('spotlight-output', findings)
        self.assertNotIn('timemachine-output', findings)
        self.assertFalse(any(call.args[0][0] == 'tmutil' for call in runner.call_args_list))

    def test_linked_worktree_candidate_refused(self):
        linked = self.project / 'build'
        linked.mkdir()
        probe = self.probe()
        trees = [{'path': str(self.project), 'is_main': True},
                 {'path': str(linked), 'is_main': False}]
        with mock.patch.object(probe, 'git', side_effect=['!! build/\0', '']):
            self.assertEqual(probe.directories(trees), [])

    def test_tmutil_deadline_timeout_is_unknown(self):
        probe = self.probe('macos')
        probe.deadline = time.monotonic() + 0.05
        with mock.patch.object(probe_module.subprocess, 'Popen') as popen:
            popen.side_effect = OSError('unavailable')
            self.assertIsNone(probe.command(['tmutil', 'isexcluded', str(self.project)]))
        self.assertIn('command_unavailable', probe.warnings)
        probe.deadline = 0
        self.assertIsNone(probe.command(['tmutil', 'isexcluded', str(self.project)]))
        self.assertIn('budget', probe.warnings)

    def test_sensitive_and_ambiguous_scope_refused(self):
        probe = self.probe()
        self.assertIsNone(probe.directories([{'path': str(self.root)}]))
        self.assertIn('ambiguous_scope', probe.warnings)
        for root in (Path('/'), Path.home().resolve(), self.root / 'Dropbox'):
            probe.project = root
            self.assertIsNone(probe.directories([{'path': str(root)}]))
            self.assertIn('sensitive_scope', probe.warnings)

    def test_enumeration_bounds_are_unknown(self):
        probe = self.probe()
        trees = [{'path': str(self.project), 'is_main': True}]
        with mock.patch.object(probe, 'git', return_value='!! build/\0' * 257):
            self.assertIsNone(probe.directories(trees))
        self.assertIn('directory_limit', probe.warnings)
        with mock.patch.object(probe, 'git', return_value=None):
            self.assertIsNone(probe.directories(trees))
        probe.deadline = 0
        self.assertIsNone(probe.size(self.project))
        self.assertIn('budget', probe.warnings)

    def test_config_special_files_and_mixed_entries(self):
        probe = self.probe()
        config = self.project / 'docs/kaizen/config.json'
        config.parent.mkdir(parents=True)
        trees = [{'path': str(self.project), 'is_main': True}]
        for kind in ('fifo', 'symlink', 'mixed'):
            if kind == 'fifo':
                os.mkfifo(config)
            elif kind == 'symlink':
                config.symlink_to(self.project / 'missing')
            else:
                config.write_text(json.dumps({'frictionOutputDirs': [1, 'build']}))
            with mock.patch.object(probe, 'git', return_value=''):
                self.assertEqual(probe.directories(trees), [])
            self.assertIn('output_config', probe.warnings)
            config.unlink()
            probe.warnings.clear()

    def test_exit_one_semantics(self):
        probe = self.probe()
        self.assertEqual(probe.command([sys.executable, '-c', 'raise SystemExit(1)', 'merge-base']), '\0')
        self.assertEqual(probe.command([sys.executable, '-c', 'raise SystemExit(1)', 'check-ignore']), '')
        self.assertIsNone(probe.command([sys.executable, '-c', 'raise SystemExit(2)', 'merge-base']))

    def test_unignored_candidate_does_not_abort(self):
        probe = self.probe()
        for name in ('build', 'dist'):
            (self.project / name).mkdir()
        config = self.project / 'docs/kaizen/config.json'
        config.parent.mkdir(parents=True)
        config.write_text(json.dumps({'frictionOutputDirs': ['build', 'dist']}))
        with mock.patch.object(probe, 'git', side_effect=['', '', '', 'dist/', '']):
            result = probe.directories([{'path': str(self.project)}])
        self.assertEqual([d['path'] for d in result], [str(self.project / 'dist')])

    def test_stale_excludes_prunable_and_unmerged_counts(self):
        probe = self.probe()
        trees = [{'path': str(self.project), 'is_main': True},
                 {'path': str(self.root / 'a'), 'is_main': False, 'clean': True, 'merged': True,
                  'locked': False, 'last_commit_age_days': 30},
                 {'path': str(self.root / 'b'), 'is_main': False, 'clean': True, 'merged': False,
                  'locked': False, 'last_commit_age_days': 30}]
        with mock.patch.object(probe, 'worktrees', return_value=trees), mock.patch.object(probe, 'directories', return_value=[]):
            facts = probe.run()['facts']
        self.assertEqual(facts['prunable_worktrees'], 1)
        self.assertEqual(facts['stale_worktrees'], 1)

    @unittest.skipUnless(os.name == 'posix', 'process groups required')
    def test_child_pipe_holder_is_killed(self):
        probe = self.probe()
        start = time.monotonic()
        result = probe.command([sys.executable, '-c',
            'import subprocess, sys; subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"])'])
        self.assertEqual(result, '')
        self.assertLess(time.monotonic() - start, 2)

    def test_foreign_registered_worktree_is_unknown(self):
        def git(root, *args):
            subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True)
        git(self.project, 'init', '-q')
        git(self.project, 'config', 'commit.gpgsign', 'false')
        git(self.project, 'config', 'user.email', 'test@example.invalid')
        git(self.project, 'config', 'user.name', 'Test')
        git(self.project, 'commit', '--allow-empty', '-qm', 'initial')
        linked = self.root / 'linked'
        git(self.project, 'worktree', 'add', '-qb', 'linked', str(linked))
        import shutil
        shutil.rmtree(linked)
        linked.mkdir()
        git(linked, 'init', '-q')
        probe = self.probe()
        self.assertIsNone(probe.worktrees())
        self.assertIn('worktrees_unavailable', probe.warnings)

    def test_spotlight_disabled_or_unknown(self):
        probe = self.probe('macos')
        directory = {'path': str(self.project), 'worktree': str(self.project), 'size_bytes': 11 * 1024**3,
                     'excluded': {'nomedia': False, 'noindex_ancestor': False}}
        trees = [{'path': str(self.project), 'is_main': True}]
        for state in ('Indexing disabled.\n', None, 'unexpected'):
            def command(argv):
                return state if argv[0] == 'mdutil' else 'mds\n'
            with mock.patch.object(probe, 'command', side_effect=command), mock.patch.object(probe, 'worktrees', return_value=trees), mock.patch.object(probe, 'directories', return_value=[directory]):
                self.assertNotIn('spotlight-output', [f['catalog_id'] for f in probe.run()['findings']])

    def test_missing_catalog_and_copied_install(self):
        probe = probe_module.Probe(self.project, 'unknown', self.root, self.root / 'missing')
        self.assertIn('catalogue', probe.warnings)
        install = self.root / 'install'
        install.mkdir()
        (install / 'kaizen-host-probe').write_bytes(SCRIPT.read_bytes())
        (install / 'kaizen-friction-catalog.json').write_bytes(self.catalog.read_bytes())
        result = subprocess.run([sys.executable, str(install / 'kaizen-host-probe'), '--project',
                                 str(self.project), '--out', str(self.root / 'audit'), '--json'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('catalogue', json.loads(result.stdout)['warnings'])


if __name__ == '__main__':
    unittest.main()
