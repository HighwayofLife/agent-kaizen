"""Offline checks for dirty worktree reporting."""
from contextlib import redirect_stdout
import io
import os
import runpy
import select
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import Mock, patch

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

    def test_advisory_selection_matches_case_aliases(self):
        other = self.root / 'Linked'
        self.git('worktree', 'add', '-qb', 'topic', str(other))
        (other / 'nested').mkdir()
        selected = other.with_name('linked') / 'nested'
        output = self.run_script('dispatch-status', '--worktree-facts', selected, other).stdout
        facts = output.split('WORKTREE FACTS (advisory)')[1].strip().splitlines()
        expected_unknown = [] if selected.is_dir() else [f'{selected}: unknown']
        self.assertEqual(facts[:-1], expected_unknown)
        self.assertTrue(facts[-1].startswith(f'path={other} branch=topic '), facts)

    def test_hidden_index_flags_make_clean_unknown(self):
        for flag in ('assume-unchanged', 'skip-worktree'):
            with self.subTest(flag=flag):
                self.git('update-index', '--' + flag, 'task.md')
                (self.work / 'task.md').write_text('hidden change')
                output = self.run_script('dispatch-status', '--worktree-facts', self.work).stdout
                self.assertIn('clean=unknown', output)
                self.git('update-index', '--no-' + flag, 'task.md')
                self.git('restore', 'task.md')

    def test_large_index_reports_clean_and_dirty(self):
        oid = self.git('rev-parse', 'HEAD:task.md').stdout.strip()
        names = [f'item-{number:05d}' for number in range(19000)]
        subprocess.run(['git', 'update-index', '--index-info'], cwd=self.work, env=self.env,
                       input=''.join(f'100644 {oid}\t{name}\n' for name in names), text=True, check=True)
        self.git('commit', '-qm', 'large index')
        self.git('checkout-index', '-a')
        for clean in ('true', 'false'):
            self.assertIn(f'clean={clean}', self.run_script('dispatch-status', '--worktree-facts').stdout)
            (self.work / names[0]).write_text('changed')

    def test_unborn_branch_reports_clean_and_dirty(self):
        unborn = self.root / 'unborn'
        self.git('init', '-q', str(unborn))
        for clean in ('true', 'false'):
            result = self.run_script('dispatch-status', '--worktree-facts', unborn)
            self.assertIn(f'tip=unknown primary=true linked=false locked=false detached=false clean={clean}', result.stdout)
            (unborn / 'new').touch()

    def test_submodule_ignore_configuration_cannot_hide_changes(self):
        sub = self.work / 'sub'
        self.git('init', '-q', str(sub))
        subprocess.run(['git', '-C', str(sub), 'config', 'user.email', 'test@example.invalid'], check=True)
        subprocess.run(['git', '-C', str(sub), 'config', 'user.name', 'Test'], check=True)
        (sub / 'tracked').write_text('original')
        subprocess.run(['git', '-C', str(sub), 'add', 'tracked'], check=True)
        subprocess.run(['git', '-C', str(sub), 'commit', '-qm', 'sub'], env=self.env, check=True)
        tip = subprocess.check_output(['git', '-C', str(sub), 'rev-parse', 'HEAD']).decode().strip()
        (self.work / '.gitmodules').write_text('[submodule \"sub\"]\n\tpath = sub\n\turl = ../sub\n')
        self.git('add', '.gitmodules')
        self.git('update-index', '--add', '--cacheinfo', f'160000,{tip},sub')
        self.git('commit', '-qm', 'add submodule')
        (sub / 'tracked').write_text('changed')
        for setting in ('submodule.sub.ignore', 'diff.ignoreSubmodules'):
            with self.subTest(setting=setting):
                self.git('config', setting, 'all')
                self.assertEqual(self.git('status', '--porcelain').stdout, '')
                output = self.run_script('dispatch-status', '--worktree-facts', self.work).stdout
                self.assertIn('clean=false', output)
                self.git('config', '--unset', setting)

    def test_overall_budget_leaves_unreached_worktrees_unknown(self):
        other = self.root / 'linked'
        self.git('worktree', 'add', '-qb', 'topic', str(other))
        script_dir = str(Path(__file__).resolve().parents[1] / 'scripts')
        with patch.object(sys, 'path', [script_dir, *sys.path]):
            import kaizen_worktree_facts as facts
            def slow_status(run, path):
                time.sleep(0.2)
                return run(path, 'status', '--porcelain')
            with patch.object(facts, 'TOTAL_TIMEOUT', 0.1):
                result = facts.read_facts(self.work, slow_status)
        self.assertIsNotNone(result)
        self.assertTrue(all(row['clean'] is None and row['merged'] is None for row in result))

    def test_git_communicate_is_bounded_and_does_not_use_select(self):
        script_dir = str(Path(__file__).resolve().parents[1] / 'scripts')
        with patch.object(sys, 'path', [script_dir, *sys.path]):
            import kaizen_worktree_facts as facts
            with patch.object(select, 'select', side_effect=OSError('unsupported')):
                self.assertEqual(facts.git(shutil.which('git'), self.work, 'rev-parse', '--is-inside-work-tree'),
                                 (0, b'true\n'))
            with patch.object(facts, 'MAX_OUTPUT', 2):
                self.assertIsNone(facts.git(shutil.which('git'), self.work, 'rev-parse', '--is-inside-work-tree'))
            sleeper = self.bin / 'slow-git'
            sleeper.write_text('#!/bin/sh\nsleep 2\n')
            sleeper.chmod(0o755)
            with patch.object(facts, 'TIMEOUT', 0.05):
                start = time.monotonic()
                self.assertIsNone(facts.git(sleeper, self.work, 'status'))
                self.assertLess(time.monotonic() - start, 1)

    def test_advisory_facts_fall_back_to_path_git(self):
        script = Path(__file__).resolve().parents[1] / 'scripts/dispatch-status'
        wrapper = self.bin / 'git'
        wrapper.symlink_to(shutil.which('git'))
        output = io.StringIO()
        with patch.object(sys, 'path', [str(script.parent), *sys.path]):
            import kaizen_worktree_facts
            with patch.object(kaizen_worktree_facts, 'GIT_PATHS', ()), patch.dict(os.environ, self.env):
                os.environ.pop('KAIZEN_GIT', None)
                self.assertIsNone(kaizen_worktree_facts.resolve_git(self.work))
                with patch.object(sys, 'argv', [str(script), '--worktree-facts', str(self.work)]):
                    with redirect_stdout(output):
                        runpy.run_path(str(script))['main']()
        self.assertIn(': unknown', output.getvalue())

    def test_facts_refuse_filters_stale_registration_and_report_dirty(self):
        script_dir = str(Path(__file__).resolve().parents[1] / 'scripts')
        other = self.root / 'linked'
        self.git('worktree', 'add', '-qb', 'topic', str(other))
        with patch.object(sys, 'path', [script_dir, *sys.path]):
            import kaizen_worktree_facts as facts
            status = lambda run, path: run(path, 'status', '--porcelain', '-z')
            self.git('update-index', '--assume-unchanged', 'task.md')
            (self.work / 'new').write_text('new')
            rows = facts.read_facts(self.work, status)
            self.assertFalse(rows[0]['clean'])
            self.git('update-index', '--no-assume-unchanged', 'task.md')
            self.git('config', 'filter.fixture.clean', 'touch ' + str(self.root / 'executed'))
            (self.work / '.gitattributes').write_text('task.md filter=fixture\n')
            (self.work / 'task.md').write_text('changed')
            rows = facts.read_facts(self.work, status)
            self.assertIsNone(rows[0]['clean'])
            self.assertFalse((self.root / 'executed').exists())
            self.git('config', '--unset', 'filter.fixture.clean')
            shutil.rmtree(other)
            other.mkdir()
            subprocess.run(['git', 'init', '-q', str(other)], check=True)
            rows = facts.read_facts(self.work, status)
            self.assertIsNone(rows[1]['clean'])

    def test_facts_command_does_not_use_path_git_or_run_filters(self):
        wrapper = self.bin / 'git'
        wrapper.write_text('#!/bin/sh\ntouch "' + str(self.root / 'path-git') + '"\nexit 1\n')
        wrapper.chmod(0o755)
        subprocess.run([shutil.which('git'), '-C', str(self.work), 'config',
                        'filter.fixture.clean', 'touch ' + str(self.root / 'filter-ran')], check=True)
        (self.work / '.gitattributes').write_text('task.md filter=fixture\n')
        (self.work / 'task.md').write_text('changed')
        self.run_script('dispatch-status', '--worktree-facts', self.work)
        self.assertFalse((self.root / 'path-git').exists())
        self.assertFalse((self.root / 'filter-ran').exists())

    def test_filter_added_during_advisory_status_never_runs(self):
        script_dir = str(Path(__file__).resolve().parents[1] / 'scripts')
        with patch.object(sys, 'path', [script_dir, *sys.path]):
            import kaizen_worktree_facts as facts
            marker = self.root / 'filter-ran'
            (self.work / '.gitattributes').write_text('task.md filter=late\n')
            task = self.work / 'task.md'
            task.write_bytes(b'x' * task.stat().st_size)
            os.utime(task, (time.time() - 60,) * 2)

            def status(run, path):
                self.git('config', 'filter.late.clean', f'touch "{marker}"; cat')
                return run(path, 'status', '--porcelain', '-z')

            self.assertFalse(facts.read_facts(self.work, status)[0]['clean'])
            self.assertFalse(marker.exists())

    def test_uninitialized_submodule_does_not_hide_other_dirt(self):
        tip = self.git('rev-parse', 'HEAD').stdout.strip()
        self.git('update-index', '--add', '--cacheinfo', f'160000,{tip},sub')
        self.git('commit', '-qm', 'gitlink')
        (self.work / 'task.md').write_text('changed')
        self.assertIn('clean=false', self.run_script('dispatch-status', '--worktree-facts', self.work).stdout)

    def test_submodule_initialized_during_parent_status_is_not_clean(self):
        staging = self.root / 'staging'
        self.git('clone', '-q', '.', str(staging))
        tip = self.git('rev-parse', 'HEAD').stdout.strip()
        self.git('update-index', '--add', '--cacheinfo', f'160000,{tip},sub')
        self.git('commit', '-qm', 'gitlink')
        (staging / 'task.md').write_text('dirty submodule')
        script_dir = str(Path(__file__).resolve().parents[1] / 'scripts')
        with patch.object(sys, 'path', [script_dir, *sys.path]):
            import kaizen_worktree_facts as facts

            def status(run, path):
                if staging.exists():
                    staging.rename(self.work / 'sub')
                return run(path, 'status', '--porcelain', '-z')

            self.assertFalse(facts.read_facts(self.work, status)[0]['clean'])

    def test_advisory_status_without_writable_temporary_storage(self):
        (self.work / '.gitattributes').write_text('task.md -text\n')
        (self.work / '.git/info/attributes').write_text('task.md text filter=late\n')
        task = self.work / 'task.md'
        task.write_bytes(task.read_bytes().replace(b'\n', b'\r\n'))
        self.git('add', '.gitattributes', 'task.md')
        self.git('commit', '-qm', 'attributes')
        os.utime(task, (time.time() - 60,) * 2)
        self.git('config', 'extensions.worktreeConfig', 'true')
        linked = self.root / 'linked'
        self.git('worktree', 'add', '-qb', 'topic', str(linked))
        (linked / 'task.md').write_text('dirty worktree')
        staged = self.root / 'staged'
        self.git('worktree', 'add', '-qb', 'staged', str(staged))
        (staged / 'new').touch()
        self.git('-C', str(staged), 'add', 'new')
        script_dir = str(Path(__file__).resolve().parents[1] / 'scripts')
        with patch.object(sys, 'path', [script_dir, *sys.path]):
            import kaizen_worktree_facts as facts

            def status(run, path):
                if path == linked:
                    self.git('-C', str(path), 'config', '--worktree', 'filter.late.clean',
                             f'touch "{self.root / "filter-ran"}"; cat')
                return run(path, 'status', '--porcelain', '-z')

            with patch('tempfile.TemporaryDirectory', side_effect=PermissionError('read-only')):
                rows = facts.read_facts(self.work, status)
            self.assertEqual({row['path']: row['clean'] for row in rows},
                             {self.work: True, linked: False, staged: False})
            self.assertFalse((self.root / 'filter-ran').exists())

    def test_submodule_symlink_loop_does_not_abort(self):
        tip = self.git('rev-parse', 'HEAD').stdout.strip()
        self.git('update-index', '--add', '--cacheinfo', f'160000,{tip},sub')
        (self.work / 'sub').symlink_to('sub')
        self.assertIn('clean=unknown', self.run_script('dispatch-status', '--worktree-facts', self.work).stdout)

    def test_submodule_ancestor_symlink_loop_blocks_status_scan(self):
        tip = self.git('rev-parse', 'HEAD').stdout.strip()
        self.git('update-index', '--add', '--cacheinfo', f'160000,{tip},sub/nested')
        (self.work / 'sub').symlink_to('sub')
        script_dir = str(Path(__file__).resolve().parents[1] / 'scripts')
        with patch.object(sys, 'path', [script_dir, *sys.path]):
            import kaizen_worktree_facts as facts
            status = Mock(return_value=(0, b''))
            rows = facts.read_facts(self.work, status)
        status.assert_not_called()
        self.assertIsNone(rows[0]['clean'])

    def test_replaced_primary_does_not_supply_cleanliness(self):
        other = self.root / 'linked'
        self.git('worktree', 'add', '-qb', 'topic', str(other))
        replacement = self.root / 'replacement'
        subprocess.run(['git', 'clone', '-q', str(self.work), str(replacement)], check=True)
        script_dir = str(Path(__file__).resolve().parents[1] / 'scripts')
        with patch.object(sys, 'path', [script_dir, *sys.path]):
            import kaizen_worktree_facts as facts
            records = facts.records
            def stale_primary(run, directory):
                entries = records(run, directory)
                entries[0][b'worktree'] = os.fsencode(replacement)
                return entries
            with patch.object(facts, 'records', side_effect=stale_primary):
                rows = facts.read_facts(other, lambda run, path: run(path, 'status', '--porcelain'))
        self.assertIsNone(rows[0]['clean'])
        self.assertTrue(rows[1]['clean'])

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
        self.env['KAIZEN_GIT'] = str(wrapper)
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
        self.env['KAIZEN_GIT'] = str(wrapper)
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
            running = self.run_script('dispatch-status', '--all').stdout.split('LATEST REPORT')[0]
        finally:
            for proc in procs:
                proc.kill()
                proc.wait()
        self.assertIn(str(fake), running)
        self.assertNotIn('codex-dispatch.log', running)

    def dispatch_while_listing(self, target, retarget=None, other=None):
        ready = self.root / 'check-ready'
        release = self.root / 'check-release'
        check = (f'touch {shlex.quote(str(ready))}; '
                 f'while [ ! -f {shlex.quote(str(release))} ]; do sleep 0.05; done')
        script = Path(__file__).resolve().parents[1] / 'scripts/codex-dispatch'
        with subprocess.Popen([str(script), '--allow-no-change', '-C', str(target), '-k', check, 'task.md'],
                              cwd=self.work, env=self.env, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True) as dispatch:
            try:
                deadline = time.monotonic() + 10
                while not ready.exists() and dispatch.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.025)
                self.assertTrue(ready.exists())
                if retarget is not None:
                    target.unlink()
                    target.symlink_to(retarget)
                status = runpy.run_path(str(script.with_name('dispatch-status')))['running']
                args = [str(script), '-C', str(target), 'task.md']
                ps = subprocess.CompletedProcess([], 0, stdout=f'{dispatch.pid} 00:01 {shlex.join(args)}\n')
                visible = []
                for checkout in (self.work, other) if other else (self.work,):
                    listing = io.StringIO()
                    with patch.object(Path, 'cwd', return_value=checkout), \
                            patch.object(sys, 'path', [str(script.parent), *sys.path]), \
                            patch.object(subprocess, 'run', return_value=ps), redirect_stdout(listing):
                        status(False)
                    visible.append(any(line.startswith(f'{dispatch.pid} ') for line in listing.getvalue().splitlines()))
                return visible
            finally:
                release.touch()
                stdout, stderr = dispatch.communicate(timeout=10)
                self.assertEqual(dispatch.returncode, 0, stdout + stderr)

    def test_retargeted_dispatch_symlink_cannot_expose_other_repository(self):
        other = self.root / 'private'
        self.git('clone', '-q', '.', str(other))
        target = self.root / 'dispatch-link'
        target.symlink_to(other)
        self.assertEqual(self.dispatch_while_listing(target, retarget=self.work, other=other), [False, True])

    def test_dispatch_scope_accepts_quoted_home_target(self):
        (self.home / 'linked checkout').symlink_to(self.work)
        self.assertEqual(self.dispatch_while_listing('~/linked checkout'), [True])

    def test_running_commands_are_scoped_to_current_repository(self):
        linked = self.root / 'linked tree'
        self.git('worktree', 'add', '-qb', 'topic', str(linked))
        other = self.work / 'private nested'
        self.git('init', '-q', str(other))
        dispatch = ['python3', '/bin/codex-dispatch']
        script = Path(__file__).resolve().parents[1] / 'scripts/dispatch-status'
        with patch.object(sys, 'path', [str(script.parent), *sys.path]):
            from kaizen_worktree_facts import dispatch_scope
        processes = {11: dispatch + [dispatch_scope(linked), str(linked), '-C', str(linked), 'linked-brief'],
                     12: dispatch + [dispatch_scope(other), str(other), '-C', str(other), 'private-brief'],
                     13: dispatch + [dispatch_scope(self.work), str(self.work), 'current-brief'],
                     14: dispatch + ['-C', str(self.work), 'unknown-brief']}
        ps = '\n'.join(f'{pid} 00:01 {" ".join(argv)}' for pid, argv in processes.items())
        main = runpy.run_path(str(script))['main']
        original_run = subprocess.run

        def run(argv, *args, **kwargs):
            if Path(argv[0]).name == 'ps':
                return subprocess.CompletedProcess(argv, 0, stdout=ps)
            return original_run(argv, *args, **kwargs)

        for options in ([], ['--all']):
            output = io.StringIO()
            with patch.object(sys, 'argv', [str(script), *options]), patch.object(Path, 'cwd', return_value=self.work), \
                    patch.object(sys, 'path', [str(script.parent), *sys.path]):
                with patch.dict(main.__globals__, process_args=processes.__getitem__):
                    with patch.object(subprocess, 'run', side_effect=run), redirect_stdout(output):
                        main()
            listing = output.getvalue().split('LATEST REPORT')[0]
            self.assertIn('current-brief', listing)
            self.assertIn('linked-brief', listing)
            for brief in ('private-brief', 'unknown-brief'):
                self.assertEqual(brief in listing, bool(options))
            if not options:
                self.assertIn('2 other or unverified dispatches', listing)
