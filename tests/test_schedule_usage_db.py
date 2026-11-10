"""The scheduled audit feeds usage-db after the token audit and never changes its result."""
import io
from contextlib import redirect_stdout
import os
import sqlite3
import subprocess
from unittest.mock import patch

from test_schedule_security import SecurityCase
from test_scripts import jsonl


class UsageDbStepTests(SecurityCase):
    def setUp(self):
        super().setUp()
        self.db = self.root / 'store' / 'usage.db'
        self.env['KAIZEN_USAGE_DB'] = str(self.db)
        os.environ['KAIZEN_USAGE_DB'] = str(self.db)
        self.addCleanup(os.environ.pop, 'KAIZEN_USAGE_DB', None)
        jsonl(self.cfg / 'projects' / 'p' / 's.jsonl', [dict(
            type='assistant', timestamp='2025-01-01T12:00:00Z', cwd=str(self.root),
            message=dict(id='m1', model='claude-x', content=[], usage=dict(input_tokens=5, output_tokens=1)))])

    def audit_run(self, code=0):
        return self.script('audit', '--audits', self.audits, '--token-audit', self.audit,
                           '--pricing', self.pricing, code=code)

    def calls(self):
        with sqlite3.connect(self.db) as conn:
            return conn.execute('SELECT count(*) FROM calls').fetchone()[0]

    def test_audit_fills_database_silently(self):
        result = self.audit_run()
        self.assertEqual(self.calls(), 1)
        self.assertNotIn('usage-db', result.stdout)
        self.assertEqual(len(result.stdout.splitlines()), 1)

    def test_failing_ingest_is_logged_and_exit_code_kept(self):
        self.db.mkdir(parents=True)
        result = self.audit_run()
        self.assertIn('step usage-db: failed (exit ', result.stdout)
        self.assertIn('audit: ok ', result.stdout)
        self.env['STUB_AUDIT_EXIT'] = '3'
        result = self.audit_run(code=3)
        self.assertIn('step usage-db: failed (', result.stdout)
        self.assertIn('audit: failed (exit 3)', result.stdout)

    def test_ingest_timeout_is_reported_and_exit_code_kept(self):
        real = subprocess.run

        def slow_ingest(command, **kwargs):
            if 'usage-db' in ' '.join(str(part) for part in command):
                raise subprocess.TimeoutExpired(command, kwargs['timeout'])
            return real(command, **kwargs)

        for audit_exit, expected in ((0, 0), (3, 3)):
            with self.subTest(audit_exit=audit_exit):
                self.env['STUB_AUDIT_EXIT'] = str(audit_exit)
                os.environ['STUB_AUDIT_EXIT'] = str(audit_exit)
                self.addCleanup(os.environ.pop, 'STUB_AUDIT_EXIT', None)
                with patch.object(self.runner.subprocess, 'run', side_effect=slow_ingest), \
                        redirect_stdout(io.StringIO()) as output:
                    code = self.runner.main(['audit', '--audits', str(self.audits), '--token-audit',
                                             str(self.audit), '--pricing', str(self.pricing)])
                self.assertEqual(code, expected)
                self.assertIn('step usage-db: failed (timed out after 600 s)', output.getvalue())
                self.assertFalse(self.db.exists())

    def test_ingest_stderr_reaches_the_log(self):
        with (self.cfg / 'projects' / 'p' / 's.jsonl').open('a') as stream:
            stream.write('{"timestamp": "2025-01-01T12:01:00Z", broken\n')
        result = self.audit_run()
        self.assertIn('step usage-db: Warning: malformed rows (1)', result.stdout)

    def test_missing_script_is_skipped_silently(self):
        options = self.options()
        self.runner.HERE = self.root / 'empty'
        self.runner.run_usage_db(options)
        self.assertFalse(self.db.exists())

    def test_review_dry_run_does_not_create_database(self):
        self.script('review', '--dry-run', '--audits', self.audits, '--token-audit', self.audit,
                    '--pricing', self.pricing)
        self.assertFalse(self.db.exists())
