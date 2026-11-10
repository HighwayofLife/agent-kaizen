"""Robustness regressions for the scheduled runner (S-2, S-3, S-5, S-10, S-11, S-15 last bullet)."""
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import re
import runpy
import signal
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

from test_hooks import run as run_hook
from test_schedule_security import SecurityCase
from test_scripts import SCRIPTS, executable, write

LEDGER_ROW = '2026-10-01,test,Existing,manual,active,no\n'
SLEEPER = '#!' + sys.executable + '\nimport os, pathlib, time\n' \
    "pathlib.Path(os.environ['PID_FILE']).write_text(str(os.getpid()))\ntime.sleep(120)\n"
AUTO_CLAUDE = '#!' + sys.executable + '\n' + """
import os, pathlib, subprocess, sys, time
target = pathlib.Path(os.environ['TARGET'])
subprocess.check_output([sys.executable, os.environ['BACKUP_SCRIPT'], 'begin', '--skill', 'trim',
                         '--ledger', 'test', target], text=True)
target.write_text('applied')
if os.environ.get('TAMPER') == '1':
    pathlib.Path(os.environ['CSV']).write_bytes(b'')
pathlib.Path(os.environ['PID_FILE']).write_text(str(os.getpid()))
if os.environ.get('HANG') == '1':
    time.sleep(120)
"""


def wait_for(path, seconds=30):
    deadline = time.monotonic() + seconds
    while not path.exists():
        if time.monotonic() > deadline:
            raise AssertionError(f'{path} never appeared')
        time.sleep(0.05)


class RobustCase(SecurityCase):
    def setUp(self):
        super().setUp()
        self.setenv(PID_FILE=str(self.root / 'child.pid'), BACKUP_SCRIPT=str(SCRIPTS / 'kaizen-backup'),
                    KAIZEN_SKIP_CHECKS='1')
        self.pid_file = self.root / 'child.pid'

    def setenv(self, **values):
        """The subprocess environment and the patched in-process one."""
        self.env.update(values)
        os.environ.update(values)

    def assert_gone(self):
        pid = int(self.pid_file.read_text())
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)

    def start(self, *args, command='review'):
        extra = ['--claude', self.claude] if command == 'review' else []
        process = subprocess.Popen(
            [sys.executable, str(SCRIPTS / 'kaizen-scheduled'), command, '--audits', str(self.audits), *map(str, extra),
             '--token-audit', str(self.audit), '--pricing', str(self.pricing), *map(str, args)],
            cwd=self.work, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(lambda: process.poll() is None and process.kill())
        return process

    def auto_fixture(self, tamper=True, hang=True):
        """Auto mode with a ledger and a backup root; the fake model edits both then (optionally) hangs."""
        from test_notes_ledger import HEADER, TIMELINE
        path = self.due('proj')
        csv = write(self.root / 'ledger.csv', HEADER + LEDGER_ROW)
        timeline = write(self.root / 'timeline.md', TIMELINE)
        self.original_ledgers = csv.read_bytes(), timeline.read_bytes()
        write(self.global_path, json.dumps({'scheduledAutonomy': 'auto', 'notesLedger': {
            'csv': str(csv), 'timeline': str(timeline)}}))
        self.csv, self.timeline = csv, timeline
        self.target = write(path / 'instructions.md', 'original')
        self.setenv(CSV=str(csv), TIMELINE=str(timeline), TARGET=str(self.target),
                    KAIZEN_BACKUP_DIR=str(self.root / 'backups'),
                    TAMPER='1' if tamper else '0', HANG='1' if hang else '0')
        executable(self.claude, AUTO_CLAUDE)
        return path

    def folder(self, path):
        return self.audits / 'projects' / self.runner.key(path)


class SignalTests(RobustCase):
    """S-2a: a killed runner still rolls back and checks the ledger."""

    def test_sigterm_in_auto_mode_rolls_back_and_restores_ledger(self):
        path = self.auto_fixture()
        process = self.start('--project-dir', path)
        wait_for(self.pid_file)
        process.send_signal(signal.SIGTERM)
        out, err = process.communicate(timeout=60)
        self.assertEqual(process.returncode, 128 + signal.SIGTERM, out + err)
        self.assert_gone()
        self.assertEqual(self.target.read_text(), 'original')  # rollback ran
        self.assertEqual((self.csv.read_bytes(), self.timeline.read_bytes()), self.original_ledgers)  # ledger check ran
        state = self.state(path)
        self.assertEqual(state['status'], 'ledger-violation')
        self.assertIn('restored snapshot', '\n'.join(state['ledger_errors']))
        self.assertIn('terminated by SIGTERM', state['last_error'])
        report = next(self.folder(path).glob('cycle-*.failed.md')).read_text()
        self.assertIn('rolled-back: ', report)
        self.assertNotIn('reviewed_at', state)

    def test_signals_in_propose_mode_record_a_failed_project(self):
        executable(self.claude, SLEEPER)
        for number in (signal.SIGTERM, signal.SIGHUP):
            with self.subTest(signal=number.name):
                self.pid_file.unlink(missing_ok=True)
                path = self.due('proj ' + number.name.lower())
                write(self.audits / 'extracts/old.extract.json', 'x')
                old = time.time() - 40 * 86400
                os.utime(self.audits / 'extracts/old.extract.json', (old, old))
                process = self.start('--project-dir', path)
                wait_for(self.pid_file)
                process.send_signal(number)
                out, err = process.communicate(timeout=60)
                self.assertEqual(process.returncode, 128 + number, out + err)
                self.assert_gone()
                state = self.state(path)
                self.assertEqual(state['status'], 'failed')
                self.assertEqual(state['last_error'], f'terminated by {number.name}')
                self.assertNotIn('reviewed_at', state)
                self.assertTrue(list(self.folder(path).glob('cycle-*.failed.md')))
                self.assertFalse(list(self.folder(path).glob('cycle-????-??-??.md')))
                # A stopped run does no housekeeping.
                self.assertTrue((self.audits / 'extracts/old.extract.json').exists())

    def test_sigterm_during_audit_exits_cleanly(self):
        executable(self.audit, SLEEPER)
        process = self.start(command='audit')
        wait_for(self.pid_file)
        process.send_signal(signal.SIGTERM)
        out, err = process.communicate(timeout=60)
        self.assertEqual(process.returncode, 128 + signal.SIGTERM, out + err)
        self.assertNotIn('Traceback', err)
        self.assert_gone()

    def test_signal_during_cleanup_is_deferred_not_lost(self):
        # A signal that lands while rollback and the ledger check run must not abort them.
        path = self.auto_fixture(hang=False)
        original = self.runner.rollback_auto_changes

        def interrupted(*args):
            os.kill(os.getpid(), signal.SIGTERM)  # arrives inside the cleanup
            return original(*args)

        with patch.object(self.runner, 'rollback_auto_changes', interrupted), \
                redirect_stdout(io.StringIO()):
            code = self.runner.main(['review', '--audits', str(self.audits), '--claude', str(self.claude),
                                     '--token-audit', str(self.audit), '--pricing', str(self.pricing),
                                     '--project-dir', str(path)])
        self.assertEqual(code, 128 + signal.SIGTERM)
        self.assertEqual(self.target.read_text(), 'original')
        self.assertEqual(self.csv.read_bytes(), self.original_ledgers[0])
        self.assertEqual(self.state(path)['status'], 'ledger-violation')
        self.assertEqual(signal.getsignal(signal.SIGTERM), signal.SIG_DFL)  # handlers restored


    def test_held_signal_is_raised_even_when_the_protected_body_fails(self):
        # V1-2: e.g. the rollback message cannot be written (disk full); the signal must still win.
        with self.runner.terminating_on_signals():
            with self.assertRaises(self.runner.Terminated) as raised:
                with self.runner.protected():
                    os.kill(os.getpid(), signal.SIGTERM)
                    raise OSError('disk full')
            self.assertEqual(raised.exception.number, signal.SIGTERM)
            self.assertIsInstance(raised.exception.__context__, OSError)
            self.assertEqual(self.runner.SIGNALS['deferred'], 0)
            # Without a signal the body's own error is what the caller sees.
            self.runner.SIGNALS.update(fired=None, raised=False)
            with self.assertRaises(OSError):
                with self.runner.protected():
                    raise OSError('disk full')
            self.assertEqual(self.runner.SIGNALS['deferred'], 0)


class TimeoutTests(RobustCase):
    """S-2b: the model run and every helper step have a wall-clock limit."""

    def test_review_timeout_kills_child_and_records_failure(self):
        executable(self.claude, SLEEPER)
        path = self.due('proj')
        self.setenv(KAIZEN_REVIEW_TIMEOUT='1')
        started = time.monotonic()
        result = self.review('--project-dir', path)
        self.assertLess(time.monotonic() - started, 60)
        self.assert_gone()
        self.assertIn('timed out after 1 s', result.stdout)
        state = self.state(path)
        self.assertEqual(state['status'], 'timed-out')
        self.assertEqual(state['last_error'], 'timed out after 1 s')
        self.assertNotIn('reviewed_at', state)
        self.assertIn('timed out after 1 s', next(self.folder(path).glob('cycle-*.failed.md')).read_text()
                      + result.stdout)
        self.assertNotIn('Traceback', result.stderr)

    def test_review_timeout_runs_rollback_and_ledger_check(self):
        path = self.auto_fixture()
        self.setenv(KAIZEN_REVIEW_TIMEOUT='1')
        result = self.review('--project-dir', path, code=1)
        self.assert_gone()
        self.assertEqual(self.target.read_text(), 'original')
        self.assertEqual(self.csv.read_bytes(), self.original_ledgers[0])
        state = self.state(path)
        self.assertEqual(state['status'], 'ledger-violation')
        self.assertEqual(state['last_error'], 'timed out after 1 s')
        self.assertIn('rolled-back: ', next(self.folder(path).glob('cycle-*.failed.md')).read_text())
        self.assertNotIn('Traceback', result.stderr)

    def test_timeout_after_rollback_without_ledger_problem(self):
        path = self.auto_fixture(tamper=False)
        self.setenv(KAIZEN_REVIEW_TIMEOUT='1')
        self.review('--project-dir', path)
        self.assertEqual(self.target.read_text(), 'original')
        state = self.state(path)
        self.assertEqual(state['status'], 'rolled-back')
        self.assertEqual(state['last_error'], 'timed out after 1 s')

    def test_review_timeout_value_parsing(self):
        default = 3600
        cases = {None: default, '': default, 'abc': default, '-5': default, 'nan': default, 'inf': default,
                 '0': None, '7': 7, '2.5': 2.5}
        for value, expected in cases.items():
            with self.subTest(value=value):
                environment = {} if value is None else {'KAIZEN_REVIEW_TIMEOUT': value}
                with patch.dict(os.environ, environment):
                    if value is None:
                        os.environ.pop('KAIZEN_REVIEW_TIMEOUT', None)
                    self.assertEqual(self.runner.review_timeout(), expected)

    def test_every_subprocess_has_a_limit(self):
        path = self.due('proj')
        self.git(path, 'init', '-q')
        os.environ.pop('KAIZEN_SKIP_CHECKS')
        self.env.pop('KAIZEN_SKIP_CHECKS')
        calls = []
        real = subprocess.run

        def record(command, **kwargs):
            calls.append((str(command[0]), [str(part) for part in command], kwargs.get('timeout')))
            return real(command, **kwargs)

        with patch.object(self.runner.subprocess, 'run', side_effect=record), redirect_stdout(io.StringIO()):
            self.runner.main(['review', '--audits', str(self.audits), '--claude', str(self.claude),
                              '--token-audit', str(self.audit), '--pricing', str(self.pricing),
                              '--project-dir', str(path)])
        self.assertTrue(calls)
        names = {Path(part).name for _, command, _ in calls for part in command[:2]}
        self.assertTrue({'git', 'stub token-audit', 'stub claude'} <= names, names)
        for executable_name, command, limit in calls:
            with self.subTest(command=command[:3]):
                self.assertEqual(limit, 3600 if executable_name == str(self.claude) else 600)
        self.assertTrue(any('rules-lint' in ' '.join(command) for _, command, _ in calls))

    def test_step_timeout_is_a_failed_step(self):
        options = self.runner.command_options(type('Args', (), {'dry_run': True})())
        with patch.object(self.runner.subprocess, 'run',
                          side_effect=subprocess.TimeoutExpired(['x'], 600)), \
                redirect_stdout(io.StringIO()) as output:
            result = self.runner.run_step('rules-lint', options, [])
        self.assertEqual(result, 'unavailable: timed out after 600 s')
        self.assertIn('step rules-lint: failed (timed out after 600 s)', output.getvalue())

    def test_git_timeout_is_not_activity(self):
        with patch.object(self.runner.subprocess, 'run', side_effect=subprocess.TimeoutExpired(['git'], 600)):
            self.assertIsNone(self.runner._git(self.root, 'status'))

    def test_audit_timeouts_are_failures_without_traceback(self):
        real = subprocess.run

        def slow_audit(command, **kwargs):
            if str(self.audit) in [str(part) for part in command]:
                raise subprocess.TimeoutExpired(command, kwargs['timeout'])
            return real(command, **kwargs)

        with patch.object(self.runner.subprocess, 'run', side_effect=slow_audit), \
                redirect_stdout(io.StringIO()) as output:
            code = self.runner.main(['audit', '--audits', str(self.audits), '--token-audit', str(self.audit),
                                     '--pricing', str(self.pricing)])
        self.assertEqual(code, 1)
        self.assertIn('audit: failed (timed out after 600 s)', output.getvalue())
        path = self.due('proj')
        with patch.object(self.runner.subprocess, 'run', side_effect=slow_audit), \
                redirect_stdout(io.StringIO()) as output:
            self.runner.main(['review', '--audits', str(self.audits), '--claude', str(self.claude),
                              '--token-audit', str(self.audit), '--pricing', str(self.pricing),
                              '--project-dir', str(path)])
        self.assertEqual(self.state(path)['status'], 'audit-failed')
        self.assertIn('failed (timed out after 600 s)', output.getvalue())
        self.assertFalse(self.record.exists())

    def test_rollback_timeout_is_a_rollback_failure(self):
        path = self.auto_fixture(tamper=False, hang=False)
        real = subprocess.run

        def slow_undo(command, **kwargs):
            if 'undo' in [str(part) for part in command]:
                raise subprocess.TimeoutExpired(command, kwargs['timeout'])
            return real(command, **kwargs)

        with patch.object(self.runner.subprocess, 'run', side_effect=slow_undo), \
                redirect_stdout(io.StringIO()) as output:
            code = self.runner.main(['review', '--audits', str(self.audits), '--claude', str(self.claude),
                                     '--token-audit', str(self.audit), '--pricing', str(self.pricing),
                                     '--project-dir', str(path)])
        self.assertEqual(code, 1)
        self.assertEqual(self.state(path)['status'], 'failed')
        self.assertIn('rollback failed: ', output.getvalue())
        self.assertIn('timed out after 600 s', output.getvalue())


@unittest.skipIf(fcntl is None, 'fcntl required')
class LockTests(RobustCase):
    """S-3: one scheduled run at a time per audits folder."""

    LINE = 'another run holds the lock'

    def hold(self):
        self.audits.mkdir(parents=True, exist_ok=True)
        handle = open(self.audits / '.lock', 'a')
        fcntl.flock(handle, fcntl.LOCK_EX)
        self.addCleanup(handle.close)
        return handle

    def test_second_run_skips_while_lock_is_held_then_proceeds(self):
        path = self.due('proj')
        self.setenv(KAIZEN_LOCK_WAIT='0')
        handle = self.hold()
        for command, args in (('review', ('--project-dir', path)), ('audit', ())):
            with self.subTest(command=command):
                result = self.script(command, '--audits', self.audits, '--token-audit', self.audit,
                                     '--pricing', self.pricing, *(('--claude', self.claude) if command == 'review' else ()),
                                     *args)
                lines = [line for line in result.stdout.splitlines() if self.LINE in line]
                self.assertEqual(len(lines), 1, result.stdout)
                self.assertIn('this run was skipped', lines[0])
                self.assertIn(str(self.audits / '.lock'), lines[0])
                self.assertFalse(self.record.exists())
                self.assertFalse((self.root / 'audit-calls.jsonl').exists())
                self.assertFalse((self.audits / 'projects').exists())
        old = write(self.audits / 'extracts/old.extract.json', 'x')
        stamp = time.time() - 40 * 86400
        os.utime(old, (stamp, stamp))
        result = self.script('housekeep', '--audits', self.audits)
        self.assertIn(self.LINE, result.stdout)
        self.assertTrue(old.exists())
        handle.close()
        self.review('--project-dir', path)
        self.assertTrue(self.record.exists())
        self.script('housekeep', '--audits', self.audits)
        self.assertFalse(old.exists())

    def test_waits_for_the_lock_then_runs(self):
        path = self.due('proj')
        self.setenv(KAIZEN_LOCK_WAIT='30')
        handle = self.hold()
        timer = threading.Timer(2, handle.close)
        timer.start()
        self.addCleanup(timer.cancel)
        started = time.monotonic()
        result = self.review('--project-dir', path)
        self.assertGreaterEqual(time.monotonic() - started, 1.5)
        self.assertNotIn(self.LINE, result.stdout)
        self.assertTrue(self.record.exists())
        self.assertEqual(self.state(path)['status'], 'ok')

    def test_waiting_for_the_lock_is_announced_once_on_stderr(self):
        self.setenv(KAIZEN_LOCK_WAIT='2')
        handle = self.hold()
        timer = threading.Timer(1.2, handle.close)
        timer.start()
        self.addCleanup(timer.cancel)
        result = self.script('housekeep', '--audits', self.audits)
        lines = result.stderr.strip().splitlines()
        self.assertEqual(lines, [f"waiting up to 2 s for the run lock {self.audits / '.lock'}"])
        self.assertNotIn('waiting', result.stdout)

    def test_no_wait_line_when_the_lock_is_free_or_waiting_is_off(self):
        self.audits.mkdir(parents=True, exist_ok=True)
        self.assertEqual(self.script('housekeep', '--audits', self.audits).stderr, '')
        self.setenv(KAIZEN_LOCK_WAIT='0')
        self.hold()
        result = self.script('housekeep', '--audits', self.audits)
        self.assertEqual(result.stderr, '')
        self.assertIn(self.LINE, result.stdout)

    def test_dry_run_config_and_help_take_no_lock(self):
        path = self.due('proj')
        self.setenv(KAIZEN_LOCK_WAIT='0')
        self.hold()
        result = self.review('--dry-run', '--project-dir', path)
        self.assertNotIn(self.LINE, result.stdout)
        self.assertIn(str(path), result.stdout)
        self.assertNotIn(self.LINE, self.script('config', 'show').stdout)
        self.assertNotIn(self.LINE, self.script('--help').stdout)
        self.assertFalse(self.record.exists())

    def test_signal_ends_the_wait_for_the_lock(self):
        self.setenv(KAIZEN_LOCK_WAIT='60')
        self.hold()
        process = self.start(command='audit')
        time.sleep(1.5)
        process.send_signal(signal.SIGTERM)
        out, err = process.communicate(timeout=30)
        self.assertEqual(process.returncode, 128 + signal.SIGTERM, out + err)
        self.assertNotIn('Traceback', err)

    def test_wait_value_parsing(self):
        for value, expected in {'': 1800, 'abc': 1800, '-1': 1800, 'nan': 1800, '0': 0, '5': 5, '0.5': 0.5}.items():
            with self.subTest(value=value), patch.dict(os.environ, {'KAIZEN_LOCK_WAIT': value}):
                self.assertEqual(self.runner.env_seconds('KAIZEN_LOCK_WAIT', 1800), expected)
        os.environ.pop('KAIZEN_LOCK_WAIT', None)
        self.assertEqual(self.runner.env_seconds('KAIZEN_LOCK_WAIT', 1800), 1800)

    def test_runs_without_a_lock_where_fcntl_is_missing(self):
        with patch.object(self.runner, 'fcntl', None), self.runner.run_lock(self.audits) as held:
            self.assertTrue(held)
        self.assertFalse((self.audits / '.lock').exists())

    def test_lock_is_released_after_the_run(self):
        path = self.due('proj')
        self.review('--project-dir', path)
        with open(self.audits / '.lock', 'a') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)


@unittest.skipIf(fcntl is None, 'fcntl required')
class LedgerGuardTests(RobustCase):
    """S-5: the restore keeps the rejected bytes and waits for notes-ledger's lock."""

    def test_rewritten_row_is_restored_and_rejected_bytes_are_kept(self):
        path = self.auto_fixture(tamper=False, hang=False)
        executable(self.claude, '#!' + sys.executable + '\n' + """
import os, pathlib
csv = pathlib.Path(os.environ['CSV'])
csv.write_text(csv.read_text().replace('active', 'done') + '2026-10-02,user,Added,manual,active,no\\n')
""")
        rewritten = (self.csv.read_text().replace('active', 'done')
                     + '2026-10-02,user,Added,manual,active,no\n').encode()
        # Appended whole lines are fine; changing history is not.
        self.review('--project-dir', path, code=1)
        self.assertEqual(self.csv.read_bytes(), self.original_ledgers[0])
        state = self.state(path)
        self.assertEqual(state['status'], 'ledger-violation')
        message = '\n'.join(state['ledger_errors'])
        self.assertIn('restored snapshot', message)
        saved = re.search(r'rejected content saved to ([^;]+)', message)
        self.assertIsNotNone(saved, message)
        saved = Path(saved.group(1))
        self.assertEqual(saved.parent.parent, self.folder(path))
        self.assertTrue(saved.parent.name.startswith('.ledger-'))
        self.assertEqual(saved.read_bytes(), rewritten)
        self.assertLess(message.index('rejected content saved'), message.index('restored snapshot'))

    def test_missing_ledger_saves_nothing_and_still_restores(self):
        path = self.auto_fixture(tamper=False, hang=False)
        executable(self.claude, '#!' + sys.executable + '\nimport os, pathlib\npathlib.Path(os.environ["CSV"]).unlink()\n')
        self.review('--project-dir', path, code=1)
        self.assertEqual(self.csv.read_bytes(), self.original_ledgers[0])
        self.assertNotIn('rejected content', '\n'.join(self.state(path)['ledger_errors']))

    def test_verify_waits_for_the_notes_ledger_lock(self):
        self.auto_fixture(tamper=False, hang=False)
        guard = self.runner.LedgerGuard(self.root / 'guard')
        guard.folder.mkdir()
        guard.snapshot()
        results = []
        with open(str(self.csv) + '.lock', 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            thread = threading.Thread(target=lambda: results.append(guard.verify()))
            thread.start()
            thread.join(0.7)
            self.assertTrue(thread.is_alive(), 'verify did not wait for the lock')
        thread.join(30)
        self.assertFalse(thread.is_alive())
        self.assertEqual(results, [[]])

    # V1-5: a lock file that is a symlink or a FIFO fails closed, quickly, and creates nothing.
    def test_lock_file_that_is_a_symlink_fails_closed(self):
        self.auto_fixture(tamper=False, hang=False)
        guard = self.runner.LedgerGuard(self.root / 'guard')
        guard.folder.mkdir()
        guard.snapshot()
        victim = self.root / 'victim'
        os.symlink(victim, str(self.csv) + '.lock')
        with self.assertRaises(OSError) as raised:
            guard.verify()
        self.assertIn('cannot lock', str(raised.exception))
        self.assertFalse(victim.exists())

    def test_lock_file_that_is_a_fifo_fails_closed(self):
        self.auto_fixture(tamper=False, hang=False)
        guard = self.runner.LedgerGuard(self.root / 'guard')
        guard.folder.mkdir()
        guard.snapshot()
        os.mkfifo(str(self.csv) + '.lock')
        started = time.monotonic()
        with self.assertRaises(OSError) as raised:
            guard.verify()
        self.assertIn('cannot lock', str(raised.exception))
        self.assertLess(time.monotonic() - started, 5)

    def test_run_with_an_unusable_lock_file_is_a_ledger_violation(self):
        for name, make in (('symlink', 'os.symlink(os.environ["CSV"] + ".victim", lock)'),
                           ('fifo', 'os.mkfifo(lock)')):
            with self.subTest(name):
                path = self.auto_fixture(tamper=False, hang=False)
                Path(str(self.csv) + '.lock').unlink(missing_ok=True)
                executable(self.claude, '#!' + sys.executable + '\nimport os\n'
                           'lock = os.environ["CSV"] + ".lock"\n' + make + '\n')
                self.review('--project-dir', path, '--force', code=1)
                state = self.state(path)
                self.assertEqual(state['status'], 'ledger-violation')
                message = '\n'.join(state['ledger_errors'])
                self.assertIn('ledger guard failed', message)
                self.assertIn('cannot lock', message)
                self.assertNotIn('restored snapshot', message)
                self.assertFalse(Path(str(self.csv) + '.victim').exists())
                os.unlink(str(self.csv) + '.lock')

    def test_restore_does_not_write_through_a_replaced_parent(self):
        self.auto_fixture(tamper=False, hang=False)
        guard = self.runner.LedgerGuard(self.root / 'guard')
        guard.folder.mkdir()
        guard.snapshot()
        outside = self.root / 'outside'
        outside.mkdir()
        (self.root / 'ledgers-moved').mkdir()
        # Swap the csv's parent: here the parent is self.root itself, so rename it through an alias path.
        entry = next(item for item in guard.entries if item['kind'] == 'csv')
        entry['path'] = outside / 'ledger.csv'
        entry['resolved'] = self.root / 'gone' / 'ledger.csv'
        problems = guard.verify()
        self.assertTrue(problems)
        self.assertEqual(list(outside.iterdir()), [])


class ProposalNameTests(RobustCase):
    """S-10: a second proposal on the same day gets a numbered name."""

    def test_same_day_proposals_are_not_overwritten(self):
        path = self.due('proj', '{"schedule":"always"}')
        names = []
        stub = self.claude.read_text()
        for number in range(3):
            if number:
                executable(self.claude, stub.replace('stub cycle output', f'proposal {number}'))
            self.review('--project-dir', path)
            state = self.state(path)
            names.append(Path(state['proposal']))
            self.assertEqual(state['status'], 'ok')
        base = names[0].stem
        self.assertRegex(base, r'^cycle-\d{4}-\d\d-\d\d$')
        self.assertEqual([item.name for item in names], [base + '.md', base + '-2.md', base + '-3.md'])
        self.assertEqual([item.read_text() for item in names],
                         ['stub cycle output\n', 'proposal 1\n', 'proposal 2\n'])

    def test_failed_report_of_a_suffixed_proposal_is_named_after_it(self):
        path = self.due('proj', '{"schedule":"always"}')
        self.review('--project-dir', path)
        first = Path(self.state(path)['proposal'])
        self.setenv(STUB_EXIT='1')
        self.review('--project-dir', path)
        self.assertEqual(first.read_text(), 'stub cycle output\n')
        self.assertTrue(first.with_name(first.stem + '-2.failed.md').exists())

    def test_readers_find_suffixed_names(self):
        ns = runpy.run_path(str(SCRIPTS / 'kaizen-scheduled'))
        audits = self.root / 'a'
        now = datetime(2026, 10, 30, tzinfo=timezone.utc)
        cfg = {'retention': {'value': 'auto'}, 'retentionOverrides': {'value': {}}}
        for index in range(8):
            name = 'projects/p/cycle-2020-01-01' + ('' if index == 0 else f'-{index + 1}') + '.md'
            path = write(audits / name, 'x')
            stamp = now.timestamp() - (400 + index) * 86400
            os.utime(path, (stamp, stamp))
        with redirect_stdout(io.StringIO()):
            plan = ns['housekeep'](audits, cfg, False, now)
        # The newest five (the lowest ages) stay; older suffixed names expire like the plain one.
        self.assertEqual(sorted(entry['path'] for entry in plan),
                         ['projects/p/cycle-2020-01-01-6.md', 'projects/p/cycle-2020-01-01-7.md',
                          'projects/p/cycle-2020-01-01-8.md'])
        self.assertTrue(all(entry['kind'] == 'reports' for entry in plan))
        self.assertEqual(len(list((audits / 'projects/p').glob('cycle-*.md'))), 5)

    def test_notice_hook_names_the_newest_suffixed_proposal(self):
        cfg = (self.root / 'hookcfg').resolve()
        audits = cfg / 'audits'
        project = self.root / 'hookproject'
        (project / 'docs/kaizen').mkdir(parents=True)
        reports = audits / 'projects/key'
        reports.mkdir(parents=True)
        (reports.parent / 'index.json').write_text(json.dumps({'v': 1, 'projects': {str(project.resolve()): 'key'}}))
        report = reports / 'token-audit-project.md'
        report.write_text('project')
        os.utime(report, (100, 100))
        for name, stamp in (('cycle-2026-01-01.md', 300), ('cycle-2026-01-01-2.md', 400)):
            write(reports / name, 'p')
            os.utime(reports / name, (stamp, stamp))
        env = {'HOME': str(self.root / 'home'), 'CLAUDE_CONFIG_DIR': str(cfg), 'AUDIT_DIR': ''}
        text = run_hook('audit-notice.sh', {'cwd': str(project)}, env)['hookSpecificOutput']['additionalContext']
        self.assertIn(str((reports / 'cycle-2026-01-01-2.md').resolve()), text)


class LedgerConfigErrorTests(RobustCase):
    """S-11: a missing ledger file is a config error, not a violation."""

    def test_missing_ledger_skips_projects_but_not_housekeeping(self):
        a, b = self.due('a proj'), self.due('b proj')
        missing = self.root / 'missing-ledger.csv'
        write(self.global_path, json.dumps({'notesLedger': {'csv': str(missing)}}))
        old = write(self.audits / 'extracts/old.extract.json', 'x')
        stamp = time.time() - 40 * 86400
        os.utime(old, (stamp, stamp))
        result = self.review('--project-dir', a, '--project-dir', b, code=1)
        self.assertFalse(self.record.exists())  # no model run, for any project
        for path in (a, b):
            state = self.state(path)
            self.assertEqual(state['status'], 'ledger-config-error')
            self.assertNotIn('ledger_errors', state)
            self.assertIn(str(missing), state['last_error'])
            self.assertIn('fix notesLedger in the global config or create the file', state['last_error'])
            self.assertNotIn('reviewed_at', state)
            self.assertIn(f'{path}: ledger-config-error: ', result.stdout)
            self.assertFalse(list(self.folder(path).glob('.ledger-*')))
            self.assertTrue(list(self.folder(path).glob('cycle-*.failed.md')))
        self.assertNotIn('ledger-violation', result.stdout)
        self.assertFalse(old.exists())  # housekeeping still ran

    def test_creating_the_file_clears_the_error(self):
        from test_notes_ledger import HEADER
        path = self.due('proj')
        csv = self.root / 'late.csv'
        write(self.global_path, json.dumps({'notesLedger': {'csv': str(csv)}}))
        self.review('--project-dir', path, code=1)
        self.assertEqual(self.state(path)['status'], 'ledger-config-error')
        write(csv, HEADER)
        self.review('--project-dir', path)
        state = self.state(path)
        self.assertEqual(state['status'], 'ok')
        self.assertNotIn('last_error', state)

    def test_history_change_is_still_a_violation(self):
        path = self.auto_fixture(tamper=True, hang=False)
        self.review('--project-dir', path, code=1)
        self.assertEqual(self.state(path)['status'], 'ledger-violation')


class StateLeftoverTests(RobustCase):
    """V1-6: a new status never sits beside the detail of an older run."""

    STALE = {'last_error': 'timed out after 3600 s', 'ledger_errors': ['old: ledger history changed']}

    def seed(self, path):
        self.review('--project-dir', path)
        file = self.folder(path) / 'state.json'
        state = json.loads(file.read_text())
        state.update(status='ledger-violation', **self.STALE)
        file.write_text(json.dumps(state))

    def test_audit_failed_replaces_the_old_detail(self):
        path = self.due('proj')
        self.seed(path)
        self.env['STUB_AUDIT_EXIT'] = '1'
        self.review('--project-dir', path, '--force')
        state = self.state(path)
        self.assertEqual(state['status'], 'audit-failed')
        self.assertEqual(state['last_error'], 'audit failed (exit 1)')
        self.assertNotIn('ledger_errors', state)

    def test_failed_without_a_detail_drops_old_ledger_errors(self):
        path = self.due('proj')
        self.seed(path)
        self.env['STUB_EXIT'] = '1'
        self.review('--project-dir', path, '--force')
        state = self.state(path)
        self.assertEqual(state['status'], 'failed')
        self.assertNotIn('last_error', state)
        self.assertNotIn('ledger_errors', state)

    def test_ok_clears_both(self):
        path = self.due('proj')
        self.seed(path)
        self.review('--project-dir', path, '--force')
        state = self.state(path)
        self.assertEqual(state['status'], 'ok')
        self.assertNotIn('last_error', state)
        self.assertNotIn('ledger_errors', state)


class RetentionTests(RobustCase):
    """S-11: ledger snapshot folders and killed-run temp files expire."""

    def setUp(self):
        super().setUp()
        self.ns = runpy.run_path(str(SCRIPTS / 'kaizen-scheduled'))
        self.now = datetime(2026, 10, 30, tzinfo=timezone.utc)
        self.cfg = {'retention': {'value': 'auto'}, 'retentionOverrides': {'value': {}}}

    def file(self, name, days=0, hours=0):
        path = write(self.audits / name, 'x')
        stamp = self.now.timestamp() - days * 86400 - hours * 3600
        os.utime(path, (stamp, stamp))
        return path

    def cleanup(self, cfg=None):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return self.ns['housekeep'](self.audits, cfg or self.cfg, False, self.now)

    def test_ledger_folders_expire_after_seven_days(self):
        for name in ('csv', 'timeline', 'manifest.json', 'csv.rejected'):
            self.file(f'projects/p/.ledger-old/{name}', days=8)
            self.file(f'projects/p/.ledger-new/{name}', days=6)
        plan = self.cleanup()
        self.assertEqual({entry['kind'] for entry in plan}, {'ledger-runs'})
        self.assertEqual(len(plan), 4)
        self.assertFalse((self.audits / 'projects/p/.ledger-old').exists())
        self.assertEqual(len(list((self.audits / 'projects/p/.ledger-new').iterdir())), 4)

    def test_killed_run_temp_files_expire_after_one_day(self):
        old = self.file('projects/p/cycle-2026-10-01.md.k3j2h1', hours=25)
        new = self.file('projects/p/cycle-2026-10-01.md.q9w8e7', hours=23)
        keep = self.file('projects/p/cycle-2026-10-01.md', days=2)
        plan = self.cleanup()
        self.assertEqual([(entry['path'], entry['kind']) for entry in plan],
                         [('projects/p/cycle-2026-10-01.md.k3j2h1', 'temp')])
        self.assertFalse(old.exists())
        self.assertTrue(new.exists() and keep.exists())

    def test_overrides_and_retention_off_apply(self):
        self.file('projects/p/.ledger-x/csv', days=3)
        self.file('projects/p/cycle-2026-10-01.md.abc', hours=3)
        self.assertEqual(self.cleanup(), [])
        self.cfg['retentionOverrides']['value'] = {'ledger-runs': {'days': 2}, 'temp': {'hours': 2}}
        self.assertEqual(sorted(entry['kind'] for entry in self.cleanup()), ['ledger-runs', 'temp'])
        self.file('projects/p/.ledger-x/csv', days=30)
        self.cfg['retention']['value'] = 'off'
        self.assertEqual(self.cleanup(), [])

    def test_symlinked_ledger_folder_is_not_followed(self):
        outside = self.root / 'outside'
        stamp = self.now.timestamp() - 30 * 86400
        victim = write(outside / 'csv', 'keep')
        os.utime(victim, (stamp, stamp))
        (self.audits / 'projects/p').mkdir(parents=True)
        (self.audits / 'projects/p/.ledger-link').symlink_to(outside, target_is_directory=True)
        self.assertEqual(self.cleanup(), [])
        self.assertTrue(victim.exists())


class RunLogTests(RobustCase):
    """S-15: run.log is rotated at 1 MB, safely for an appending shell redirect."""

    BIG = 1024 * 1024 + 10

    def audit_with_redirect(self):
        log = self.audits / 'run.log'
        with open(log, 'ab') as stream:
            subprocess.run([sys.executable, str(SCRIPTS / 'kaizen-scheduled'), 'audit', '--audits', str(self.audits),
                            '--token-audit', str(self.audit), '--pricing', str(self.pricing)],
                           cwd=self.work, env=self.env, stdout=stream, stderr=stream, check=True)
        return log

    def test_large_log_is_rotated_and_output_follows(self):
        write(self.audits / 'run.log', 'a' * self.BIG)
        write(self.audits / 'run.log.1', 'older')
        log = self.audit_with_redirect()
        self.assertEqual((self.audits / 'run.log.1').read_text(), 'a' * self.BIG)
        text = log.read_text()
        self.assertLess(len(text), 10000)
        self.assertIn('audit: ok', text)  # the run's own lines land in the new run.log
        self.assertFalse(list(self.audits.glob('.run.log.*')))

    def test_small_log_is_kept(self):
        write(self.audits / 'run.log', 'a' * 1024 * 1024)
        log = self.audit_with_redirect()
        self.assertTrue(log.read_text().startswith('a' * 1024 * 1024))
        self.assertFalse((self.audits / 'run.log.1').exists())

    def test_symlinked_log_is_never_rotated(self):
        target = write(self.root / 'elsewhere.log', 'a' * self.BIG)
        (self.audits).mkdir(parents=True, exist_ok=True)
        (self.audits / 'run.log').symlink_to(target)
        with redirect_stdout(io.StringIO()):
            self.runner.rotate_log(self.audits)
        self.assertEqual(target.read_text(), 'a' * self.BIG)
        self.assertTrue((self.audits / 'run.log').is_symlink())
        self.assertFalse((self.audits / 'run.log.1').exists())
        self.assertFalse(list(self.audits.glob('.run.log.*')))

    def test_review_rotates_and_dry_run_does_not(self):
        path = self.due('proj')
        write(self.audits / 'run.log', 'a' * self.BIG)
        self.review('--dry-run', '--project-dir', path)
        self.assertFalse((self.audits / 'run.log.1').exists())
        self.review('--project-dir', path)
        self.assertTrue((self.audits / 'run.log.1').exists())
        self.assertLess((self.audits / 'run.log').stat().st_size, 10000)

    def test_rotation_failure_does_not_stop_the_run(self):
        write(self.audits / 'run.log', 'a' * self.BIG)
        with patch.object(self.runner.shutil, 'copyfileobj', side_effect=OSError('disk full')), \
                redirect_stdout(io.StringIO()) as output:
            code = self.runner.main(['audit', '--audits', str(self.audits), '--token-audit', str(self.audit),
                                     '--pricing', str(self.pricing)])
        self.assertEqual(code, 0)
        self.assertIn('run.log: cannot rotate', output.getvalue())


if __name__ == '__main__':
    unittest.main()
