"""Scheduler follow-ups: signal windows, process groups, hard-kill recovery, config lock."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

from test_schedule_robustness import AUTO_CLAUDE, RobustCase, wait_for
from test_scripts import SCRIPTS, executable

# A model stand-in that starts a helper in the same process group and records both pids.
FORKER = '#!' + sys.executable + '\n' + """
import os, pathlib, subprocess, sys, time
helper = subprocess.Popen([sys.executable, '-c',
    "import os, pathlib, time\\npathlib.Path(os.environ['GRANDCHILD_PID']).write_text(str(os.getpid()))\\ntime.sleep(120)"])
pathlib.Path(os.environ['PID_FILE']).write_text(str(os.getpid()))
time.sleep(120)
"""
QUIET = '#!' + sys.executable + '\npass\n'


def gone(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    return False


class ProcessGroupTests(RobustCase):
    def setUp(self):
        super().setUp()
        self.grandchild = self.root / 'grandchild.pid'
        self.setenv(GRANDCHILD_PID=str(self.grandchild))
        executable(self.claude, FORKER)

    def assert_helper_gone(self):
        wait_for(self.grandchild)
        pid = int(self.grandchild.read_text())
        deadline = time.monotonic() + 3
        while not gone(pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertTrue(gone(pid), 'the model run left a helper process behind')

    def test_timeout_kills_the_whole_process_group(self):
        path = self.due('proj')
        self.setenv(KAIZEN_REVIEW_TIMEOUT='2')
        self.review('--project-dir', path)
        self.assert_gone()
        self.assert_helper_gone()

    def test_signal_kills_the_whole_process_group_and_exits_143(self):
        path = self.due('proj')
        process = self.start('--project-dir', path)
        wait_for(self.pid_file)
        wait_for(self.grandchild)
        started = time.monotonic()
        process.send_signal(signal.SIGTERM)
        out, err = process.communicate(timeout=60)
        self.assertLess(time.monotonic() - started, 30)
        self.assertEqual(process.returncode, 128 + signal.SIGTERM, out + err)
        self.assert_gone()
        self.assert_helper_gone()
        self.assertEqual(self.state(path)['status'], 'failed')
        self.assertEqual(self.state(path)['last_error'], 'terminated by SIGTERM')

    def test_step_runs_in_its_own_session(self):
        code = 'import os; print(os.getpid() == os.getpgrp())'
        result = self.runner.run_group([sys.executable, '-c', code], capture_output=True, text=True)
        self.assertEqual(result.stdout.strip(), 'True')  # a session leader: its pid is its group
        self.assertIs(self.runner.subprocess.Popen, subprocess.Popen)  # patched only during the call

    def test_timeout_kills_helpers_after_the_leader_exits(self):
        executable(self.claude, FORKER.rsplit('time.sleep(120)', 1)[0] + 'sys.exit(0)\n')
        with self.assertRaises(subprocess.TimeoutExpired):
            self.runner.run_group([str(self.claude)], env=self.env, capture_output=True, timeout=0.4)
        self.assert_helper_gone()

    def test_hard_kill_watchdog_kills_term_ignoring_model_and_helper(self):
        code = FORKER.replace('import os, pathlib, subprocess, sys, time',
                              'import os, pathlib, subprocess, sys, time, signal\n'
                              'signal.signal(signal.SIGTERM, signal.SIG_IGN)')
        code = code.replace('import os, pathlib, time\\n',
                            'import os, pathlib, time, signal\\n'
                            'signal.signal(signal.SIGTERM, signal.SIG_IGN)\\n')
        executable(self.claude, code)
        path = self.due('proj')
        process = self.start('--project-dir', path)
        wait_for(self.pid_file)
        wait_for(self.grandchild)
        process.kill()
        process.communicate(timeout=10)
        self.assert_helper_gone()
        self.assert_gone()

    def test_group_kill_leaves_the_runner_alone(self):
        # A child that did not get its own session must not take our group down with it.
        grouped = self.runner.GroupPopen([sys.executable, '-c', 'import time; time.sleep(60)'],
                                         start_new_session=False)
        self.addCleanup(grouped.kill)
        with patch.object(self.runner.os, 'killpg') as killpg:
            grouped.kill()  # falls back to killing only the child
        killpg.assert_not_called()
        grouped.wait(timeout=10)


class SignalWindowTests(RobustCase):
    def test_sigint_during_child_construction_has_no_untracked_window(self):
        original = subprocess.Popen.__init__
        children = []

        def interrupted(child, *args, **kwargs):
            original(child, *args, **kwargs)
            children.append(child)
            os.kill(os.getpid(), signal.SIGINT)

        def cleanup():
            for child in children:
                child.kill()
                child.wait(timeout=5)

        self.addCleanup(cleanup)
        with self.runner.terminating_on_signals(), \
                patch.object(subprocess.Popen, '__init__', interrupted):
            with self.assertRaises(BaseException) as caught:
                self.runner.run_group([sys.executable, '-c', 'import time; time.sleep(120)'])
        self.assertIsInstance(caught.exception, self.runner.Terminated)
        self.assertEqual(caught.exception.number, signal.SIGINT)
        self.assertTrue(children)
        self.assertIsNotNone(children[0].returncode)
        self.assertTrue(gone(children[0].pid))

    def test_sigint_during_protected_model_run_exits_130_after_cleanup(self):
        path = self.auto_fixture(tamper=True)
        process = self.start('--project-dir', path)
        wait_for(self.pid_file)
        process.send_signal(signal.SIGINT)
        out, err = process.communicate(timeout=10)
        self.assertEqual(process.returncode, 130, out + err)
        self.assert_gone()
        self.assertEqual(self.target.read_text(), 'original')
        self.assertEqual(self.csv.read_bytes(), self.original_ledgers[0])

    def test_signal_right_after_the_model_returns_still_rolls_back(self):
        # V1-2 (b): the old code left a gap between the child exiting and the deferred state.
        path = self.auto_fixture(tamper=False, hang=False)
        real = subprocess.run

        def late_signal(command, **kwargs):
            result = real(command, **kwargs)
            if command[0] == str(self.claude):
                os.kill(os.getpid(), signal.SIGTERM)
            return result

        output = io.StringIO()
        with patch.object(self.runner.subprocess, 'run', side_effect=late_signal), \
                redirect_stdout(output):
            code = self.runner.main(['review', '--audits', str(self.audits), '--claude', str(self.claude),
                                     '--token-audit', str(self.audit), '--pricing', str(self.pricing),
                                     '--project-dir', str(path)])
        self.assertEqual(code, 128 + signal.SIGTERM)
        self.assertEqual(self.target.read_text(), 'original', output.getvalue())
        self.assertEqual(self.state(path)['status'], 'rolled-back')
        self.assertFalse((self.runner.backup_root() / self.runner.ACTIVE_RUN).exists())

    def test_sighup_during_the_model_run_rolls_back_and_exits_129(self):
        path = self.auto_fixture(tamper=False)
        process = self.start('--project-dir', path)
        wait_for(self.pid_file)
        process.send_signal(signal.SIGHUP)
        out, err = process.communicate(timeout=60)
        self.assertEqual(process.returncode, 128 + signal.SIGHUP, out + err)
        self.assert_gone()
        self.assertEqual(self.target.read_text(), 'original')


class HardKillTests(RobustCase):
    def setUp(self):
        super().setUp()
        self.setenv(KAIZEN_BACKUP_DIR=str(self.root / 'backups'))
        self.backups = self.runner.backup_root()
        self.backups.mkdir()

    def marker(self, run_id='r1', session_id='s1', mode='auto', guard=None):
        if guard is None:
            folder = self.root / ('snapshot-' + str(time.monotonic_ns()))
            folder.mkdir()
            guard = self.runner.LedgerGuard(folder)
            guard.snapshot()
        return self.runner.write_active_run(self.audits, run_id, session_id, mode, guard)

    def recover(self):
        with redirect_stdout(io.StringIO()):
            return self.runner.recover_interrupted_run(self.audits, self.options())

    def review_in_process(self, path):
        with redirect_stdout(io.StringIO()) as output:
            code = self.runner.main(['review', '--audits', str(self.audits), '--claude', str(self.claude),
                                     '--token-audit', str(self.audit), '--pricing', str(self.pricing),
                                     '--project-dir', str(path), '--force'])
        return code, output.getvalue()

    def backup(self, target, run_id='r1', session_id='s1', finished=False):
        env = dict(self.env, KAIZEN_RUN_ID=run_id, KAIZEN_SESSION_ID=session_id)
        result = subprocess.run([sys.executable, str(SCRIPTS / 'kaizen-backup'), 'begin',
                                 '--skill', 'trim', '--ledger', 'test', str(target)],
                                env=env, capture_output=True, text=True, check=True)
        change = Path(result.stdout.strip())
        target.write_text('applied')
        if finished:
            subprocess.run([sys.executable, str(SCRIPTS / 'kaizen-backup'), 'finish', str(change),
                            '--verification', 'failed'], env=env, capture_output=True, check=True)
        return change

    def kill_run(self, path):
        process = self.start('--project-dir', path)
        wait_for(self.pid_file)
        process.kill()
        process.communicate(timeout=10)
        # No manual orphan kill: the watchdog must do this after pipe EOF.
        deadline = time.monotonic() + 3
        while not gone(int(self.pid_file.read_text())) and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assert_gone()

    def test_hard_kill_stops_model_and_keeps_unfinished_conflict_propose_only(self):
        path = self.auto_fixture(tamper=False)
        self.kill_run(path)
        marker = self.backups / self.runner.ACTIVE_RUN
        before = marker.read_bytes()
        self.assertEqual(self.target.read_text(), 'applied')
        executable(self.claude, QUIET)
        # A second project must also stay propose-only, on every retry.
        other = self.due('other')
        for _ in range(2):
            result = self.review('--project-dir', path, '--project-dir', other, '--force')
            self.assertIn('CONFLICT', result.stdout)
            self.assertIn('recovery command:', result.stdout)
            self.assertIn(f'{path}: reviewed (propose-only)', result.stdout)
            self.assertIn(f'{other}: reviewed (propose-only)', result.stdout)
            self.assertEqual(marker.read_bytes(), before)
            self.assertEqual(self.target.read_text(), 'applied')
            self.assertEqual(len(list(self.backups.glob('.active-run*.json'))), 1)
        # Owner resolves the change; the later recovery can clear its record.
        change = next(self.backups.glob('*/manifest.json')).parent
        subprocess.run([sys.executable, str(SCRIPTS / 'kaizen-backup'), 'undo', str(change)],
                       env=self.env, capture_output=True, check=True)
        result = self.review('--project-dir', path, '--force')
        self.assertFalse(marker.exists())
        self.assertIn(f'{path}: reviewed (auto)', result.stdout)

    def test_marker_and_temporary_symlinks_cannot_truncate_a_target(self):
        self.audits.mkdir()
        target = self.root / 'untouched'
        target.write_text('original')
        (self.audits / (self.runner.ACTIVE_RUN + '.tmp')).symlink_to(target)
        (self.audits / self.runner.ACTIVE_RUN).symlink_to(target)
        (self.backups / self.runner.ACTIVE_RUN).symlink_to(target)
        (self.backups / (self.runner.ACTIVE_RUN + '.tmp')).symlink_to(target)
        with patch.object(self.runner.os, 'open', wraps=os.open) as opened:
            marker = self.marker()
        for call in opened.call_args_list:
            self.assertEqual(call.args[1] & (os.O_EXCL | os.O_NOFOLLOW), os.O_EXCL | os.O_NOFOLLOW)
        self.assertEqual(marker.parent, self.backups.resolve())
        self.assertEqual(marker.stat().st_mode & 0o777, 0o600)
        self.assertFalse(marker.is_symlink())
        self.assertEqual(target.read_text(), 'original')
        self.assertIn(f'Write({self.runner.deny_path(self.backups)}/**)', self.runner.backup_deny())
        first = marker.read_bytes()
        another = self.marker()
        self.assertNotEqual(marker, another)
        self.assertEqual(marker.read_bytes(), first)

    def test_recovery_requires_both_ids_and_ignores_legacy_forgery(self):
        target = self.root / 'target'
        target.write_text('original')
        self.backup(target, session_id='another-session')
        self.backup(target, run_id='another-run')
        target.write_text('legitimate later edit')
        self.marker()
        self.assertIsNone(self.recover())
        self.assertEqual(target.read_text(), 'legitimate later edit')
        self.audits.mkdir()
        (self.audits / self.runner.ACTIVE_RUN).write_text(json.dumps({
            'run_id': 'r1', 'session_id': 'another-session', 'mode': 'auto'}))
        self.assertIn('ledger-unverified', self.recover())
        self.assertEqual(target.read_text(), 'legitimate later edit')

    def test_finished_conflict_is_never_forced_and_is_retried(self):
        target = self.root / 'target'
        target.write_text('original')
        change = self.backup(target, finished=True)
        target.write_text('legitimate later edit')
        marker = self.marker()
        self.assertIn('CONFLICT', self.recover())
        self.assertTrue(marker.exists())
        self.assertEqual(target.read_text(), 'legitimate later edit')
        target.write_text('applied')
        real = self.runner.run_group
        with patch.object(self.runner, 'run_group', wraps=real) as run:
            self.assertIsNone(self.recover())
        self.assertEqual(target.read_text(), 'original')
        self.assertNotIn('--force', run.call_args.args[0])
        self.assertTrue(json.loads((change / 'manifest.json').read_text())['reverted'])
        self.assertFalse(marker.exists())

    def test_authenticated_hard_kill_snapshot_restores_corrupted_ledger(self):
        path = self.auto_fixture(tamper=True)
        self.kill_run(path)
        executable(self.claude, QUIET)
        result = self.review('--project-dir', path)
        self.assertIn('interrupted run ', result.stdout)
        self.assertIn('ledger-violation:', result.stdout)
        self.assertEqual(self.csv.read_bytes(), self.original_ledgers[0])
        self.assertEqual(self.timeline.read_bytes(), self.original_ledgers[1])

    def test_changed_snapshot_stays_unverified_and_is_never_restored(self):
        path = self.auto_fixture(tamper=True)
        self.kill_run(path)
        marker = self.backups / self.runner.ACTIVE_RUN
        data = json.loads(marker.read_text())
        snapshot = Path(data['ledger'][0]['snapshot'])
        original = snapshot.read_bytes()
        snapshot.write_bytes(b'X' + original[1:])  # same size; trust must depend on the hash
        executable(self.claude, QUIET)
        for _ in range(2):
            result = self.review('--project-dir', path, '--force')
            self.assertIn('ledger-unverified: snapshot hash mismatch', result.stdout)
            self.assertIn(f'{path}: reviewed (propose-only)', result.stdout)
            self.assertEqual(self.csv.read_bytes(), b'')
            self.assertTrue(marker.exists())

    def test_unreadable_marker_stays_recorded(self):
        marker = self.backups / self.runner.ACTIVE_RUN
        marker.write_text('{broken')
        marker.chmod(0o600)
        for _ in range(2):
            reason = self.recover()
            self.assertIn('ledger-unverified: unreadable marker', reason)
            self.assertIn('interrupted run unknown', reason)
            self.assertTrue(marker.exists())

    def test_marker_is_cleared_after_a_normal_run(self):
        path = self.auto_fixture(tamper=False, hang=False)
        self.review('--project-dir', path)
        self.assertFalse(list(self.backups.glob('.active-run*.json')))

    def test_no_marker_means_nothing_to_recover(self):
        self.assertIsNone(self.recover())

    def assert_unresolved_ledger(self, failure):
        path = self.auto_fixture(tamper=True, hang=False)
        with failure():
            code, output = self.review_in_process(path)
        self.assertEqual(code, 1, output)
        self.assertEqual(self.target.read_text(), 'original')  # rollback succeeded
        marker = self.backups / self.runner.ACTIVE_RUN
        self.assertTrue(marker.exists(), output)
        data = json.loads(marker.read_text())
        snapshots = [Path(entry['snapshot']) for entry in data['ledger']]
        self.assertTrue(all(snapshot.is_file() for snapshot in snapshots))
        self.assertIn('interrupted run ' + data['run_id'], output)
        self.assertIn('ledger-unverified', output)
        self.assertIn('discard recovery record: rm -- ', output)
        before = marker.read_bytes()
        executable(self.claude, QUIET)
        # A later review must not replace or drop the unresolved record.
        with patch.object(self.runner, 'recovery_ledger', side_effect=OSError('still unresolved')):
            code, output = self.review_in_process(path)
        self.assertEqual(code, 0, output)
        self.assertIn(f'{path}: reviewed (propose-only)', output)
        self.assertEqual(marker.read_bytes(), before)
        self.assertTrue(all(snapshot.is_file() for snapshot in snapshots))
        # Once the external problem is fixed, authenticated recovery clears it.
        self.recover()
        self.assertFalse(marker.exists())
        self.assertEqual(self.csv.read_bytes(), self.original_ledgers[0])

    def test_ledger_verification_exception_keeps_marker_and_snapshots(self):
        self.assert_unresolved_ledger(lambda: patch.object(
            self.runner.LedgerGuard, 'verify', side_effect=OSError('cannot lock ledger')))

    def test_failed_ledger_restore_keeps_marker_and_snapshots(self):
        replace = os.replace

        def fail_restore(source, target):
            if Path(target) == self.csv:
                raise OSError('restore refused')
            return replace(source, target)

        self.assert_unresolved_ledger(lambda: patch.object(self.runner.os, 'replace', side_effect=fail_restore))

    def test_backup_change_names_and_nonregular_objects_are_not_markers(self):
        target = self.root / 'target'
        target.write_text('original')
        subprocess.run([sys.executable, str(SCRIPTS / 'kaizen-backup'), 'begin', '--run', '.active-run',
                        '--skill', 'trim.json', '--ledger', 'test', str(target)],
                       env=self.env, capture_output=True, check=True)
        # Neither an old marker-shaped backup directory nor a symlink authorizes recovery.
        link = self.backups / self.runner.ACTIVE_RUN
        link.symlink_to(target)
        fifo = self.backups / ('.active-run.' + '0' * 32 + '.json')
        os.mkfifo(fifo)
        (self.backups / ('.active-run.' + '1' * 32 + '.json')).mkdir()
        with patch.object(self.runner, 'read_recovery_json', wraps=self.runner.read_recovery_json) as read:
            self.assertIsNone(self.recover())
        read.assert_not_called()
        marker = self.marker()
        self.assertRegex(marker.name, r'^\.active-run\.[0-9a-f]{32}\.json$')
        self.assertNotRegex(marker.name, r'-[0-9]+-')
        self.assertIsNone(self.recover())
        self.assertEqual(target.read_text(), 'original')
        self.assertTrue(link.is_symlink())

    def test_old_uuid_marker_is_still_recovered(self):
        marker = self.marker()
        old = self.backups / '.active-run-12345678-1234-1234-1234-123456789abc.json'
        marker.rename(old)
        self.assertIsNone(self.recover())
        self.assertFalse(old.exists())

    def test_printed_recovery_commands_work_without_job_environment(self):
        # Quotes and spaces must survive copying the whole command into a shell.
        self.setenv(CLAUDE_CONFIG_DIR=str(self.root / "config 'quoted'"),
                    KAIZEN_BACKUP_DIR=str(self.root / "backups 'quoted'"))
        self.backups = self.runner.backup_root()
        self.backups.mkdir()
        target = self.root / 'target'
        target.write_text('original')
        change = self.backup(target, finished=True)
        target.write_text('later edit')
        marker = self.marker()
        reason = self.recover()
        command = reason.split('; recovery command: ', 1)[1].split('; resolve changes', 1)[0]
        self.assertIn('CLAUDE_CONFIG_DIR=', command)
        self.assertIn('KAIZEN_BACKUP_DIR=', command)
        self.assertNotIn('--force', shlex.split(command))
        shell_env = dict(self.env)
        for name in ('KAIZEN_BACKUP_DIR', 'CLAUDE_CONFIG_DIR'):
            shell_env.pop(name, None)
        # The command reaches the correct backup and reports the actual conflict.
        result = subprocess.run(command, shell=True, env=shell_env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn('CONFLICT', result.stdout)
        target.write_text('applied')
        subprocess.run(command, shell=True, env=shell_env, capture_output=True, check=True)
        self.assertTrue(json.loads((change / 'manifest.json').read_text())['reverted'])
        self.assertIsNone(self.recover())
        self.assertFalse(marker.exists())
        marker = self.marker()
        marker.write_text('{broken')
        command = self.recover().split('then discard recovery record: ', 1)[1]
        subprocess.run(command, shell=True, env=shell_env, capture_output=True, check=True)
        self.assertIsNone(self.recover())

    def test_printed_undo_uses_config_default_backup_root(self):
        self.env.pop('KAIZEN_BACKUP_DIR')
        os.environ.pop('KAIZEN_BACKUP_DIR')
        self.backups = self.runner.backup_root()
        self.backups.mkdir(parents=True)
        target = self.root / 'target'
        target.write_text('original')
        self.backup(target)
        self.marker()
        command = self.recover().split('; recovery command: ', 1)[1].split('; resolve changes', 1)[0]
        self.assertIn('CLAUDE_CONFIG_DIR=', command)
        self.assertNotIn('KAIZEN_BACKUP_DIR=', command)
        shell_env = dict(self.env)
        shell_env.pop('CLAUDE_CONFIG_DIR')
        subprocess.run(command, shell=True, env=shell_env, capture_output=True, check=True)
        self.assertIsNone(self.recover())

    def test_every_unresolved_state_prints_a_working_manual_exit(self):
        self.audits.mkdir()
        legacy = self.audits / self.runner.ACTIVE_RUN
        legacy.mkdir()  # removal must work for a legacy directory too
        states = ('legacy-directory', 'unreadable', 'bad-mode', 'missing-snapshot', 'tampered-snapshot')
        for state in states:
            with self.subTest(state=state):
                if state == 'legacy-directory':
                    record = legacy
                elif state == 'unreadable':
                    record = self.backups / self.runner.ACTIVE_RUN
                    record.write_text('{broken')
                    record.chmod(0o600)
                else:
                    self.auto_fixture(tamper=False, hang=False)
                    guard = self.runner.LedgerGuard(self.root / ('snapshot-' + state))
                    guard.folder.mkdir()
                    guard.snapshot()
                    record = self.marker(guard=guard)
                    if state == 'bad-mode':
                        data = json.loads(record.read_text())
                        data['mode'] = 'invalid'
                        record.write_text(json.dumps(data))
                    elif state == 'missing-snapshot':
                        guard.entries[0]['snapshot'].unlink()
                    else:
                        guard.entries[0]['snapshot'].write_bytes(b'changed')
                reason = self.recover()
                self.assertIn('ledger-unverified', reason)
                command = reason.split('then discard recovery record: ', 1)[1]
                subprocess.run(command, shell=True, env=self.env, capture_output=True, check=True)
                self.assertFalse(record.exists())
                self.assertIsNone(self.recover())

    def test_retention_keeps_unresolved_snapshots_until_marker_is_removed(self):
        path = self.auto_fixture(tamper=False, hang=False)
        folder = self.folder(path) / '.ledger-pending'
        folder.mkdir(parents=True)
        guard = self.runner.LedgerGuard(folder)
        guard.snapshot()
        marker = self.marker(guard=guard)
        snapshots = [entry['snapshot'] for entry in guard.entries]
        for snapshot in snapshots:
            os.utime(snapshot, (1, 1))
        # Test both authenticated metadata and unreadable state with unknown paths.
        for readable in (True, False):
            if not readable:
                marker.write_text('{broken')
            with redirect_stdout(io.StringIO()):
                self.runner.housekeep(self.audits, {}, now=time.time())
            self.assertTrue(all(snapshot.is_file() for snapshot in snapshots))
        marker.unlink()
        with redirect_stdout(io.StringIO()):
            self.runner.housekeep(self.audits, {}, now=time.time())
        self.assertFalse(any(snapshot.exists() for snapshot in snapshots))

    def test_kill_during_snapshot_cleanup_needs_no_manual_recovery(self):
        path = self.auto_fixture(tamper=False, hang=False)
        cleanup = shutil.rmtree
        folders = []

        class Killed(BaseException):
            pass

        def killed_after_first_snapshot(folder, *args, **kwargs):
            folder = Path(folder)
            if folder.name.startswith('.ledger-') and folder.parent == self.folder(path):
                folders.append(folder)
                (folder / 'csv').unlink()
                raise Killed()
            return cleanup(folder, *args, **kwargs)

        with patch.object(self.runner.shutil, 'rmtree', side_effect=killed_after_first_snapshot), \
                self.assertRaises(Killed):
            self.review_in_process(path)
        self.assertEqual(len(folders), 1)
        self.assertTrue(folders[0].exists())
        self.assertIsNone(self.recover())
        self.assertFalse(list(self.runner.recovery_markers(self.backups)))
        executable(self.claude, QUIET)
        result = self.review('--project-dir', path, '--force')
        self.assertIn(f'{path}: reviewed (auto)', result.stdout)


class ReadScopeTests(RobustCase):
    def test_backup_root_equal_to_audits_reuses_the_run_lock(self):
        path = self.due('proj')
        self.setenv(KAIZEN_BACKUP_DIR=str(self.audits), KAIZEN_LOCK_WAIT='0')
        executable(self.claude, QUIET)
        result = self.review('--project-dir', path)
        self.assertIn(f'{path}: reviewed (propose-only)', result.stdout)
        self.assertNotIn('another run holds the lock', result.stdout)

    def test_actual_custom_audits_folder_is_in_auto_read_allow_list(self):
        path = self.due('proj')
        self.global_path.write_text(json.dumps({'scheduledAutonomy': 'auto'}))
        self.review('--project-dir', path)
        allowed = self.values(self.last_argv(), '--allowedTools')[0].split(',')
        rule = f'Read({self.runner.deny_path(self.audits)}/**)'
        self.assertIn(rule, allowed)
        expected = set(self.runner.auto_read_allow(path)) | {rule}
        self.assertEqual({rule for rule in allowed if rule.startswith('Read(')}, expected)


@unittest.skipIf(fcntl is None, 'fcntl required')
class ConfigLockTests(RobustCase):
    def set_for(self, path):
        return subprocess.Popen([sys.executable, str(SCRIPTS / 'kaizen-scheduled'), 'config', 'set', '--for',
                                 str(path), 'scheduledAutonomy=auto'], env=self.env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def test_config_set_for_waits_for_the_global_config_lock(self):
        path = self.project('proj')
        self.global_path.parent.mkdir(parents=True, exist_ok=True)
        with open(str(self.global_path) + '.lock', 'a') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            process = self.set_for(path)
            self.addCleanup(lambda: process.poll() is None and process.kill())
            time.sleep(1.5)
            self.assertIsNone(process.poll(), 'config set --for ignored the lock')
        out, err = process.communicate(timeout=60)
        self.assertEqual(process.returncode, 0, out + err)
        listed = json.loads(self.global_path.read_text())['autoProjects']
        self.assertEqual([os.path.realpath(item) for item in listed], [os.path.realpath(path)])

    def test_concurrent_calls_keep_every_entry(self):
        paths = [self.project(f'proj{number}') for number in range(6)]
        processes = [self.set_for(path) for path in paths]
        for process in processes:
            out, err = process.communicate(timeout=120)
            self.assertEqual(process.returncode, 0, out + err)
        listed = {os.path.realpath(item) for item in json.loads(self.global_path.read_text())['autoProjects']}
        self.assertEqual(listed, {os.path.realpath(path) for path in paths})

    def test_symlinked_global_config_stays_a_symlink(self):
        target = self.root / 'dotfiles' / 'agent-kaizen.json'
        target.parent.mkdir()
        target.write_text('{}')
        self.global_path.parent.mkdir(parents=True, exist_ok=True)
        self.global_path.symlink_to(target)
        process = self.set_for(self.project('proj'))
        out, err = process.communicate(timeout=60)
        self.assertEqual(process.returncode, 0, out + err)
        self.assertTrue(self.global_path.is_symlink())
        self.assertIn('autoProjects', json.loads(target.read_text()))


if __name__ == '__main__':
    unittest.main()
