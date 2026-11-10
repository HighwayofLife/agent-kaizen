"""Dispatch guards exercised with a fake Codex in isolated worktrees."""
import os
import shlex
import signal
import subprocess
import time

try:
    from tests.test_scripts import FAKE_CODEX, SCRIPTS, StubCase, executable, write
except ModuleNotFoundError:
    from test_scripts import FAKE_CODEX, SCRIPTS, StubCase, executable, write


class DispatchGuardTests(StubCase):
    def setUp(self):
        super().setUp()
        self.env.update(GIT_AUTHOR_NAME='Test', GIT_AUTHOR_EMAIL='test@example.invalid',
                        GIT_COMMITTER_NAME='Test', GIT_COMMITTER_EMAIL='test@example.invalid')
        subprocess.run(['git', 'init', '-q', str(self.work)], check=True, env=self.env)
        write(self.work / 'tracked', 'original\n')
        subprocess.run(['git', '-C', str(self.work), 'add', '.'], check=True, env=self.env)
        subprocess.run(['git', '-C', str(self.work), 'commit', '-qm', 'initial'], check=True, env=self.env)

    def test_no_change_resumes_and_fails(self):
        result = self.dispatch(code=1)
        self.assertIn('FAIL: require-change', result.stdout)
        self.assertEqual(len(self.calls()), 3)
        self.assertIn('No files changed', self.calls()[1]['prompt'])
        self.assertEqual(self.report(result)[-1], 'STATUS: CHECKS FAILING')

    def test_nested_repo_does_not_break_snapshot(self):
        nested = self.work / 'sub'
        subprocess.run(['git', 'init', '-q', str(nested)], check=True, env=self.env)
        write(nested / 'file', 'nested')
        subprocess.run(['git', '-C', str(nested), 'add', '.'], check=True, env=self.env)
        subprocess.run(['git', '-C', str(nested), 'commit', '-qm', 'nested'], check=True, env=self.env)
        self.assertEqual(self.report(self.dispatch('-p', 'planner'))[-1], 'STATUS: DONE')
        executable(self.bin / 'codex', FAKE_CODEX + "\npathlib.Path('tracked').write_text('changed')\n")
        self.assertIn('PASS: require-change', self.dispatch().stdout)

    def test_nested_repo_with_no_op_codex_still_fails_require_change(self):
        nested = self.work / 'sub'
        subprocess.run(['git', 'init', '-q', str(nested)], check=True, env=self.env)
        write(nested / 'file', 'nested')
        subprocess.run(['git', '-C', str(nested), 'add', '.'], check=True, env=self.env)
        subprocess.run(['git', '-C', str(nested), 'commit', '-qm', 'nested'], check=True, env=self.env)
        result = self.dispatch('-r', '0', code=1)
        self.assertIn('FAIL: require-change', result.stdout)
        self.assertEqual(self.report(result)[-1], 'STATUS: CHECKS FAILING')

    def test_output_directory_does_not_count_as_change(self):
        result = self.dispatch('-o', self.work / 'logs' / 'x', '-r', '0', code=1)
        self.assertIn('FAIL: require-change', result.stdout)

    def test_change_passes(self):
        executable(self.bin / 'codex', FAKE_CODEX + "\npathlib.Path('tracked').write_text('changed')\n")
        self.assertIn('PASS: require-change', self.dispatch().stdout)

    def test_dirty_tree_warns_and_unchanged_fails(self):
        write(self.work / 'new file', 'existing')
        result = self.dispatch('-r', '0', code=1)
        self.assertIn('WARNING: tree was dirty before dispatch (1 paths)', result.stdout)
        self.assertIn('FAIL: require-change', result.stdout)

    def test_existing_untracked_content_change_passes(self):
        write(self.work / 'new file', 'existing')
        executable(self.bin / 'codex', FAKE_CODEX + "\npathlib.Path('new file').write_text('updated')\n")
        self.assertIn('PASS: require-change', self.dispatch().stdout)

    def test_dirty_tracked_content_change_passes(self):
        write(self.work / 'tracked', 'already dirty')
        executable(self.bin / 'codex', FAKE_CODEX + "\npathlib.Path('tracked').write_text('new change')\n")
        result = self.dispatch()
        self.assertIn('WARNING: tree was dirty before dispatch (1 paths)', result.stdout)
        self.assertIn('PASS: require-change', result.stdout)

    def test_resume_can_satisfy_require_change(self):
        executable(self.bin / 'codex', FAKE_CODEX + "\nif number: pathlib.Path('tracked').write_text('fixed')\n")
        result = self.dispatch('-k', 'true')
        self.assertEqual(len(self.calls()), 2)
        self.assertIn('No files changed', self.calls()[1]['prompt'])
        self.assertEqual(self.report(result)[-1], 'STATUS: DONE')

    def test_report_limit_with_both_guards_and_many_checks(self):
        write(self.brief, 'Sol reason: Named reason\n')
        executable(self.bin / 'codex', FAKE_CODEX + "\npathlib.Path('tracked').write_text('changed')\n")
        result = self.dispatch('-m', 'gpt-6.1-sol', *['-k', 'true'] * 12)
        self.assertIn('WARNING: tree was dirty before dispatch (1 paths)', result.stdout)
        self.assertIn('Sol reason: Named reason', result.stdout)
        self.report(result)

    def test_allow_no_change_and_planner(self):
        for options in (('--allow-no-change',), ('-p', 'planner'), ('-p', 'none')):
            self.assertEqual(self.report(self.dispatch(*options))[-1], 'STATUS: DONE')

    def test_sol_requires_reason_before_codex(self):
        result = self.dispatch('-m', 'gpt-6.1-sol', code=2)
        self.assertIn('Reason: ', result.stdout)
        self.assertIn('Sol reason', result.stdout)
        self.assertEqual(result.stdout.splitlines()[-1], 'STATUS: CODEX FAILED')
        self.assertFalse(self.record.exists())
        self.assertFalse((self.work / 'out').exists())

    def test_sol_from_environment_rejects_empty_reason(self):
        self.env['CODEX_DISPATCH_MODEL'] = 'sol'
        write(self.brief, 'Sol reason:  \nTask\n')
        result = self.dispatch(code=2)
        self.assertEqual(len(result.stdout.splitlines()), 2)
        self.assertEqual(result.stdout.splitlines()[-1], 'STATUS: CODEX FAILED')
        self.assertFalse(self.record.exists())

    def test_sol_default_requires_reason(self):
        self.env['CODEX_DISPATCH_MODEL'] = 'sol'
        result = self.dispatch(code=2)
        self.assertIn('Sol reason', result.stdout)
        self.assertFalse(self.record.exists())

    def test_console_model_does_not_require_sol_reason(self):
        self.assertEqual(self.report(self.dispatch('-m', 'console-model', '--allow-no-change'))[-1], 'STATUS: DONE')

    def test_sol_reason_reported(self):
        write(self.brief, 'Task\n  sol reason: Needs broad reasoning\n')
        result = self.dispatch('-m', 'sol', '--allow-no-change')
        self.assertIn('Sol reason: Needs broad reasoning', result.stdout)
        self.assertTrue(self.record.exists())

    def test_resume_is_exempt(self):
        self.dispatch('-m', 'sol', '--resume', 'previous', '--allow-no-change')
        self.assertTrue(self.record.exists())

    def test_non_git_is_unaffected(self):
        work = self.root / 'non-git'
        work.mkdir()
        result = self.run_script('codex-dispatch', '-C', work, self.brief)
        self.assertEqual(self.report(result)[-1], 'STATUS: DONE')
        self.assertNotIn('require-change', result.stdout)

    def commit_all(self, message):
        subprocess.run(['git', '-C', str(self.work), 'add', '.'], check=True, env=self.env)
        subprocess.run(['git', '-C', str(self.work), 'commit', '-qm', message], check=True, env=self.env)

    # D-2: files written by checks never count as a Codex change.
    def test_check_artifact_does_not_satisfy_require_change(self):
        artifact = 'python3 -c "import time; open(\'artifact\', \'w\').write(str(time.time_ns()))"'
        result = self.dispatch('-k', artifact, code=1)
        self.assertIn('Check 0 FAIL: require-change', result.stdout)
        self.assertEqual(self.report(result)[-1], 'STATUS: CHECKS FAILING')
        self.assertEqual(len(self.calls()), 3)

    def test_change_in_first_round_only_still_passes_after_resume(self):
        executable(self.bin / 'codex', FAKE_CODEX + "\nif number == 0: pathlib.Path('tracked').write_text('first')\n")
        result = self.dispatch('-k', 'test -f marker || { touch marker; exit 1; }')
        self.assertEqual(len(self.calls()), 2)
        self.assertIn('Check 0 PASS', result.stdout)
        self.assertEqual(self.report(result)[-1], 'STATUS: DONE')

    # D-3: the output directory is never part of the snapshot.
    def test_output_inside_repo_but_outside_subdirectory_cwd(self):
        write(self.work / 'sub' / 'file', 'x')
        self.commit_all('sub')
        result = self.dispatch('-C', self.work / 'sub', '-o', self.work / 'logs' / 'x', '-r', '0', code=1)
        self.assertIn('Check 0 FAIL: require-change', result.stdout)

    # D-4: commits count, ignored files do not.
    def test_commit_by_codex_counts_as_change(self):
        executable(self.bin / 'codex', FAKE_CODEX + """
import subprocess
if number == 0:
    pathlib.Path('tracked').write_text('committed')
    subprocess.run(['git', 'commit', '-qam', 'by codex'], check=True)
""")
        result = self.dispatch('-r', '0')
        self.assertIn('Check 0 PASS: require-change', result.stdout)
        executable(self.bin / 'codex', FAKE_CODEX + """
import subprocess
if number == 1:
    subprocess.run(['git', 'commit', '--allow-empty', '-qm', 'empty'], check=True)
""")
        self.assertIn('Check 0 PASS: require-change', self.dispatch('-r', '0').stdout)

    def test_ignored_only_output_is_no_change_and_failure_names_the_flag(self):
        write(self.work / '.gitignore', 'ignored.txt\n')
        self.commit_all('ignore')
        executable(self.bin / 'codex', FAKE_CODEX + "\npathlib.Path('ignored.txt').write_text('x')\n")
        result = self.dispatch('-r', '0', code=1)
        line = [item for item in result.stdout.splitlines() if item.startswith('Check 0 FAIL')][0]
        self.assertIn('Ignored files do not count', line)
        self.assertIn('--allow-no-change', line)

    # D-6/D-7: configurable reason guard.
    def test_reason_models_environment_replaces_default(self):
        self.env['CODEX_DISPATCH_REASON_MODELS'] = ' Big , other '
        result = self.dispatch('-m', 'gpt-7-BIG', code=2)
        self.assertIn('Big reason', result.stdout)
        self.assertFalse(self.record.exists())
        self.assertEqual(self.report(self.dispatch('-m', 'sol', '--allow-no-change'))[-1], 'STATUS: DONE')

    def test_empty_reason_models_turns_guard_off(self):
        self.env['CODEX_DISPATCH_REASON_MODELS'] = ''
        self.assertEqual(self.report(self.dispatch('-m', 'sol', '--allow-no-change'))[-1], 'STATUS: DONE')

    def test_reason_token_matches_whole_segment_with_digits(self):
        self.dispatch('-m', 'sol2', code=2)
        self.dispatch('-m', 'gpt-6.1-sol-high', code=2)
        self.assertFalse(self.record.exists())
        for name in ('solhigh', 'console', 'resolve-2'):
            self.assertEqual(self.report(self.dispatch('-m', name, '--allow-no-change'))[-1], 'STATUS: DONE')

    def test_reason_line_forms(self):
        for text in ('Model reason: broad refactor\n', '**Sol reason:** broad refactor\n',
                     '__Sol reason__: broad refactor\n', '  SOL REASON: broad refactor\n'):
            write(self.brief, 'Task\n' + text)
            result = self.dispatch('-m', 'sol', '--allow-no-change')
            self.assertIn('Sol reason: broad refactor', result.stdout, text)

    def test_reason_inside_code_fence_does_not_count(self):
        for fence in ('```', '~~~'):
            write(self.brief, f'Example:\n{fence}\nSol reason: quoted\n{fence}\n')
            self.dispatch('-m', 'sol', code=2)
        write(self.brief, '```\nSol reason: quoted\n```\nSol reason: real one\n')
        self.assertIn('Sol reason: real one', self.dispatch('-m', 'sol', '--allow-no-change').stdout)

    def test_indented_code_block_and_placeholder_reasons_do_not_count(self):
        for text in ('    Sol reason: example\n', '\tSol reason: example\n', '     Model reason: example\n',
                     'Sol reason: <why>\n', 'Model reason:   <the reason>  \n', 'Sol reason: <>\n'):
            write(self.brief, 'Task\n' + text)
            result = self.dispatch('-m', 'sol', code=2)
            self.assertIn('Sol reason', result.stdout, text)
        self.assertFalse(self.record.exists())
        write(self.brief, 'Task\n    Sol reason: example\nSol reason: <why>\n   Sol reason: real one\n')
        result = self.dispatch('-m', 'sol', '--allow-no-change')
        self.assertIn('Sol reason: real one', result.stdout)
        write(self.brief, 'Task\nSol reason: needs <b>bold</b> thinking\n')
        self.assertIn('Sol reason: needs <b>bold</b> thinking', self.dispatch('-m', 'sol', '--allow-no-change').stdout)

    def test_help_documents_reason_environment(self):
        self.assertIn('CODEX_DISPATCH_REASON_MODELS', self.run_script('codex-dispatch', '--help').stdout)

    # D-8: checks have a time limit.
    def test_check_timeout_fails_the_check_and_resumes(self):
        started = time.time()
        result = self.dispatch('--allow-no-change', '-r', '1', '-k', 'sleep 30', '--check-timeout', '1', code=1)
        self.assertLess(time.time() - started, 20)
        self.assertIn('Check 1 FAIL: sleep 30', result.stdout)
        self.assertIn('TIMEOUT after 1s', result.stdout)
        self.assertEqual(len(self.calls()), 2)
        logs = list((self.work / 'out/dispatch').glob('*/check-1.log'))
        self.assertIn('TIMEOUT after 1s', logs[0].read_text())

    def test_check_timeout_environment_default_and_zero(self):
        self.env['CODEX_DISPATCH_CHECK_TIMEOUT'] = '1'
        result = self.dispatch('--allow-no-change', '-r', '0', '-k', 'sleep 30', code=1)
        self.assertIn('TIMEOUT after 1s', result.stdout)
        result = self.dispatch('--allow-no-change', '-k', 'sleep 2', '--check-timeout', '0')
        self.assertEqual(self.report(result)[-1], 'STATUS: DONE')

    # D-12: snapshot problems are visible and readable.
    def test_unreadable_untracked_file_warns_in_report(self):
        if os.geteuid() == 0:
            self.skipTest('root can read any file')
        secret = write(self.work / 'secret', 'x')
        secret.chmod(0)
        self.addCleanup(secret.chmod, 0o600)
        result = self.dispatch('-r', '0')
        report = next((self.work / 'out/dispatch').glob('*/report.md')).read_text()
        self.assertIn('WARNING: tree snapshot failed', report)
        self.assertIn('require-change skipped', report)
        self.assertEqual(self.report(result)[-1], 'STATUS: DONE')

    def test_failing_git_command_in_snapshot_is_readable(self):
        (self.work / '.git' / 'index').write_bytes(b'not an index')
        result = self.dispatch('-r', '0')
        self.assertIn('WARNING: tree snapshot failed: git status failed', result.stdout)
        self.assertNotIn('CalledProcessError', result.stdout)
        self.assertNotIn("returned non-zero exit status", result.stdout)
        self.assertEqual(self.report(result)[-1], 'STATUS: DONE')

    def test_diff_line_counts_untracked_files(self):
        executable(self.bin / 'codex', FAKE_CODEX + "\npathlib.Path('made.txt').write_text('x')\n")
        result = self.dispatch()
        self.assertIn('Check 0 PASS: require-change', result.stdout)
        self.assertIn('Diff: (no tracked diff); 1 untracked file(s)', result.stdout)
        executable(self.bin / 'codex', FAKE_CODEX + "\npathlib.Path('tracked').write_text('x')\npathlib.Path('made.txt').write_text('x')\n")
        result = self.dispatch()
        self.assertIn('Diff: 1 untracked file(s)', result.stdout)
        self.assertEqual(self.report(result)[-1], 'STATUS: DONE')


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class DispatchSignalTests(StubCase):
    """A terminated dispatcher leaves no check or Codex process behind."""

    def start(self, *args):
        process = subprocess.Popen([str(SCRIPTS / 'codex-dispatch'), '-C', str(self.work), '--allow-no-change',
                                    '-r', '0', *map(str, args), str(self.brief)], env=self.env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(process.kill)
        self.addCleanup(process.communicate)
        return process

    def pid_from(self, path, process):
        deadline = time.time() + 20
        while time.time() < deadline:
            if process.poll() is not None:
                self.fail('dispatcher ended early: ' + process.communicate()[0])
            if path.is_file() and path.read_text().strip():
                pid = int(path.read_text())
                self.addCleanup(lambda: alive(pid) and os.kill(pid, signal.SIGKILL))
                return pid
            time.sleep(0.05)
        self.fail('no pid file')

    def assert_gone(self, pid):
        deadline = time.time() + 5
        while alive(pid) and time.time() < deadline:
            time.sleep(0.05)
        self.assertFalse(alive(pid), 'process is still running')

    def check_command(self, pidfile, tail='exec sleep 300'):
        return f'echo $$ > {shlex.quote(str(pidfile))}.tmp; mv {shlex.quote(str(pidfile))}.tmp {shlex.quote(str(pidfile))}; {tail}'

    def interrupt_check(self, number, expected):
        pidfile = self.root / 'check.pid'
        process = self.start('-k', self.check_command(pidfile))
        pid = self.pid_from(pidfile, process)
        process.send_signal(number)
        process.communicate(timeout=20)
        self.assertEqual(process.returncode, expected)
        self.assert_gone(pid)

    def test_sigint_kills_running_check(self):
        self.interrupt_check(signal.SIGINT, -signal.SIGINT)

    def test_sigterm_kills_running_check(self):
        self.interrupt_check(signal.SIGTERM, 128 + signal.SIGTERM)

    def test_sighup_kills_running_check(self):
        self.interrupt_check(signal.SIGHUP, 128 + signal.SIGHUP)

    def test_sigterm_kills_running_codex_and_its_wrapper(self):
        pidfile = self.root / 'codex.pid'
        executable(self.bin / 'codex', f"""#!/usr/bin/env python3
import os, pathlib, time
pathlib.Path({str(pidfile)!r}).write_text(str(os.getpid()))
time.sleep(300)
""")
        process = self.start()
        pid = self.pid_from(pidfile, process)
        process.send_signal(signal.SIGTERM)
        process.communicate(timeout=20)
        self.assertEqual(process.returncode, 128 + signal.SIGTERM)
        self.assert_gone(pid)

    def test_timeout_kills_grandchildren_of_a_check(self):
        pidfile = self.root / 'grandchild.pid'
        command = self.check_command(pidfile, 'wait')
        command = command.replace('echo $$ >', 'sleep 300 & echo $! >', 1)
        process = self.start('-k', command, '--check-timeout', '1')
        pid = self.pid_from(pidfile, process)
        out, _ = process.communicate(timeout=30)
        self.assertEqual(process.returncode, 1, out)
        self.assertIn('TIMEOUT after 1s', out)
        self.assert_gone(pid)
