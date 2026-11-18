"""SessionStart audit scheduling with isolated config, reports and transcripts."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import subprocess
import sys
import time

from test_schedule_robustness import wait_for
from test_scripts import SCRIPTS, StubCase, jsonl, write


ROOT = SCRIPTS.parent
HOOK = ROOT / 'hooks/session-audit.sh'
FIXTURE = ROOT / 'tests/fixtures/hooks/sessionstart.json'
STUB_AUDIT = '''
import json, os, sys, time
from pathlib import Path
args = sys.argv[1:]
with open(os.environ['AUDIT_CALLS'], 'a') as stream:
    stream.write(json.dumps(args) + '\\n')
if os.environ.get('HOLD_AUDIT'):
    while not Path(os.environ['HOLD_AUDIT']).exists():
        time.sleep(0.02)
mode = os.environ.get('AUDIT_MODE', 'ok')
report = Path(args[args.index('--out') + 1]) / f'token-audit-{mode}.md'
if mode != 'missing':
    report.write_text('stub audit report')
print(report)
sys.exit(3 if mode == 'failed' else 0)
'''


class HookScheduleTests(StubCase):
    def setUp(self):
        super().setUp()
        self.cfg = self.root / 'config'
        self.audits = self.cfg / 'audits'
        self.state = self.audits / 'auto-audit-state.json'
        self.calls = self.root / 'audit-calls'
        self.scripts = self.root / 'plugin' / 'scripts'
        self.scripts.mkdir(parents=True)
        self.scheduler = self.scripts / 'kaizen-scheduled'
        shutil.copyfile(SCRIPTS / self.scheduler.name, self.scheduler)
        for name in ('kaizen_credentials.py', 'pricing.json'):
            (self.scripts / name).symlink_to(SCRIPTS / name)
        write(self.scripts / 'token-audit', STUB_AUDIT)
        self.env.update(CLAUDE_CONFIG_DIR=str(self.cfg), CODEX_HOME=str(self.root / 'codex'),
                        CLAUDE_PLUGIN_ROOT=str(self.scripts.parent), AUDIT_CALLS=str(self.calls),
                        KAIZEN_SKIP_CHECKS='1', KAIZEN_USAGE_DB=str(self.cfg / 'kaizen-usage.db'))
        self.payload = FIXTURE.read_text()

    def hook(self, **env):
        result = subprocess.run(['bash', str(HOOK)], input=self.payload, cwd=self.work,
                                env={**self.env, **env}, capture_output=True, text=True, timeout=20)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))

    def call_args(self):
        return [json.loads(line) for line in self.calls.read_text().splitlines()]

    def set_age(self, days):
        last = datetime.now(timezone.utc) - timedelta(days=days)
        return write(self.state, json.dumps({'last_audit_ok': last.isoformat()})).read_bytes()

    def test_registration_and_absent_then_fresh_state(self):
        hooks = json.loads((ROOT / 'hooks/hooks.json').read_text())['hooks']
        entries = [(event, hook) for event, groups in hooks.items() for group in groups
                   for hook in group['hooks'] if 'session-audit.sh' in hook['command']]
        self.assertEqual(entries, [('SessionStart', {
            'type': 'command', 'command': 'bash "${CLAUDE_PLUGIN_ROOT}/hooks/session-audit.sh"',
            'async': True})])
        self.assertEqual(json.loads(self.payload)['hook_event_name'], 'SessionStart')
        self.hook()
        first = self.state.read_bytes()
        last = datetime.fromisoformat(json.loads(first)['last_audit_ok'].replace('Z', '+00:00'))
        self.assertEqual(last.utcoffset(), timedelta(0))
        self.assertLess(abs(datetime.now(timezone.utc) - last), timedelta(minutes=1))
        self.assertNotIn('--cwd', self.call_args()[0])
        self.hook()
        self.assertEqual(len(self.call_args()), 1)
        self.assertEqual(self.state.read_bytes(), first)

    def test_stale_and_malformed_state_are_due(self):
        self.set_age(4)
        self.hook()
        for index, broken in enumerate(('{broken', '[]', '{"last_audit_ok":"yesterday"}'), 2):
            with self.subTest(state=broken):
                write(self.state, broken)
                self.hook()
                self.assertEqual(len(self.call_args()), index)
                self.assertTrue(json.loads(self.state.read_text())['last_audit_ok'].endswith('Z'))
        self.assertEqual(list(self.audits.glob(self.state.name + '.*')), [])

    def test_opt_out_and_runner_errors_are_silent(self):
        config = self.cfg / 'agent-kaizen.json'
        for settings in ('{"autoAudit":false}', '{"enabled":false}'):
            write(config, settings)
            self.hook()
        self.assertFalse(self.audits.exists())
        config.unlink()
        self.hook(CLAUDE_PLUGIN_ROOT='')
        write(self.audits, 'blocks the audits directory')
        self.hook()
        self.assertFalse(self.calls.exists())

    def test_failed_and_missing_report_keep_state_and_retry(self):
        original = self.set_age(4)
        for mode in ('failed', 'missing'):
            self.hook(AUDIT_MODE=mode)
            self.assertEqual(self.state.read_bytes(), original)
        self.hook()
        self.assertEqual(len(self.call_args()), 3)
        self.assertNotEqual(self.state.read_bytes(), original)

    def test_concurrent_start_skips_held_lock(self):
        release = self.root / 'release-audit'
        env = {**self.env, 'HOLD_AUDIT': str(release)}
        with FIXTURE.open() as payload, subprocess.Popen(
                ['bash', str(HOOK)], cwd=self.work, env=env, stdin=payload,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as first:
            try:
                wait_for(self.calls, seconds=5)
                self.hook()
                self.assertFalse(self.state.exists())
            finally:
                release.touch()
                out, err = first.communicate(timeout=20)
            self.assertEqual((first.returncode, out, err), (0, '', ''))
        self.assertTrue(self.state.is_file())
        self.assertEqual(len(self.call_args()), 1)

    def test_scoped_review_does_not_advance_global_state(self):
        original = self.set_age(4)
        (self.work / 'docs/kaizen').mkdir(parents=True)
        claude = write(self.root / 'fake-claude', '#!/bin/sh\nprintf "proposal\\n"\n')
        claude.chmod(0o755)
        result = subprocess.run([sys.executable, str(self.scheduler), 'review', '--force',
                                 '--project-dir', str(self.work), '--claude', str(claude)],
                                env=self.env, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('--cwd', self.call_args()[0])
        self.assertEqual(self.state.read_bytes(), original)
        self.hook()
        self.assertNotEqual(self.state.read_bytes(), original)

    def test_deadline_kills_ingest_and_its_helper(self):
        original = self.set_age(4)
        worker = self.scheduler.with_name('worker')
        self.scheduler.rename(worker)
        write(self.scheduler, f'''
import runpy, sys
main = runpy.run_path({str(worker)!r})['main']
main.__globals__['AUTO_AUDIT_TIMEOUT'] = 3
sys.exit(main())
''')
        pids = self.root / 'pids'
        write(self.scripts / 'usage-db', f'''
import os, signal, subprocess, sys, time
from pathlib import Path
signal.signal(signal.SIGTERM, signal.SIG_IGN)
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(12)'])
Path({str(pids)!r}).write_text(f'{{os.getpid()}} {{child.pid}}')
time.sleep(12)
''')
        started = time.monotonic()
        self.hook()
        self.assertLess(time.monotonic() - started, 10)
        self.assertTrue((self.audits / 'token-audit-ok.md').is_file())
        self.assertEqual(self.state.read_bytes(), original)
        self.assertIn('auto-audit: stopped by SIGALRM; will retry next session',
                      (self.audits / 'run.log').read_text())
        for pid in map(int, pids.read_text().split()):
            deadline = time.monotonic() + 3
            while True:
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    break
                status = subprocess.run(['ps', '-o', 'stat=', '-p', str(pid)],
                                        capture_output=True, text=True).stdout.strip()
                if not status or status.startswith('Z'):
                    break
                if time.monotonic() >= deadline:
                    os.kill(pid, signal.SIGKILL)
                    self.fail(f'process {pid} survived the worker deadline')
                time.sleep(0.05)
        (self.scripts / 'usage-db').unlink()
        self.hook()
        self.assertNotEqual(self.state.read_bytes(), original)

    def test_real_all_project_audit_checks_and_appends_to_os_job_database(self):
        env = {**self.env, 'CLAUDE_PLUGIN_ROOT': str(ROOT), 'KAIZEN_SKIP_CHECKS': '0'}
        date = datetime.now(timezone.utc).isoformat()

        def transcript(name, project):
            return jsonl(self.cfg / 'projects' / name / 'session.jsonl', [
                dict(type='assistant', timestamp=date, cwd=str(project),
                     message=dict(id=name, model='claude-x', content=[],
                                  usage=dict(input_tokens=5, output_tokens=1)))])

        old = transcript('old', self.work)
        result = subprocess.run([sys.executable, str(SCRIPTS / 'kaizen-scheduled'), 'audit'],
                                env=env, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        old.unlink()
        (self.work / 'docs/kaizen').mkdir(parents=True)
        other = self.root / 'unenrolled'
        other.mkdir()
        transcript('enrolled', self.work)
        transcript('unenrolled', other)
        self.hook(**env)
        self.assertEqual(len(list(self.audits.glob('token-audit-*.md'))), 1)
        self.set_age(4)
        self.hook(**env)
        reports = sorted(self.audits.glob('token-audit-*.md'))
        self.assertEqual(len(reports), 2)
        report = reports[-1].read_text()
        self.assertIn('"cwd": null', report)
        self.assertIn('"claude_calls": 2', report)
        checks = sorted(self.audits.glob('checks-*.md'))[-1].read_text()
        self.assertIn(f'## Experiments: {self.work}', checks)
        self.assertNotIn(f'## Experiments: {other}', checks)
        with sqlite3.connect(self.env['KAIZEN_USAGE_DB']) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM calls').fetchone()[0], 3)
