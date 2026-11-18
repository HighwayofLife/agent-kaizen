import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent


class DoctorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.root = self.home / 'plugin'
        for directory in ('scripts', 'hooks', '.claude-plugin'):
            shutil.copytree(ROOT / directory, self.root / directory)
        self.bin = self.home / 'tools'
        self.bin.mkdir()
        for name in ('git', 'bash'):
            source = shutil.which(name)
            if source:
                (self.bin / name).symlink_to(source)
        self.executable('jq', 'echo jq-1.7')
        self.executable('python3', 'echo Python 3.11.0')
        self.env = dict(os.environ, HOME=str(self.home), CLAUDE_CONFIG_DIR=str(self.home / 'claude'),
                        PATH=str(self.bin), XDG_CONFIG_HOME=str(self.home / 'config'),
                        PYTHONDONTWRITEBYTECODE='1')
        self.env.pop('KAIZEN_USAGE_DB', None)
        self.claude = Path(self.env['CLAUDE_CONFIG_DIR'])
        self.claude.mkdir()
        link = self.root / 'scripts/kaizen-link'
        subprocess.run([sys.executable, str(link), '--apply', '--plugin-root', str(self.root)],
                       env=self.env, check=True, capture_output=True)
        registry = self.claude / 'plugins/installed_plugins.json'
        registry.parent.mkdir()
        name = json.loads((self.root / '.claude-plugin/plugin.json').read_text())['name']
        self.cache = self.home / 'cache'
        shutil.copytree(self.root, self.cache)
        registry.write_text(json.dumps({'plugins': {name + '@market': [{'installPath': str(self.cache)}]}}))
        pricing = self.root / 'scripts/pricing.json'
        data = json.loads(pricing.read_text())
        data['source']['checked'] = datetime.now(timezone.utc).date().isoformat()
        pricing.write_text(json.dumps(data))
        shutil.copy2(pricing, self.cache / 'scripts/pricing.json')
        self.db = self.claude / 'kaizen-usage.db'
        with sqlite3.connect(self.db) as conn:
            conn.execute('CREATE TABLE files (ingested_at TEXT)')
            conn.execute('INSERT INTO files VALUES (?)', (datetime.now(timezone.utc).isoformat(),))
        self.report = self.claude / 'audits/token-audit-20260101.md'
        self.report.parent.mkdir()
        self.canary('v1 unknown_records=0 missing_usage=0 cli=2.0')

    def executable(self, name, body):
        path = self.bin / name
        path.write_text('#!/bin/sh\n' + body + '\n')
        path.chmod(0o755)

    def canary(self, value):
        self.report.write_text('<!-- token-audit-headline ' + json.dumps({'format_canary': value}) + ' -->\n')

    def doctor(self, *args):
        result = subprocess.run([sys.executable, str(self.root / 'scripts/kaizen-doctor'),
                                 '--plugin-root', str(self.root), '--project', str(self.home), *args],
                                env=self.env, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        for line in result.stdout.splitlines():
            if line.startswith(('WARN ', 'FAIL ')):
                self.assertIn('; fix: ', line)
        return result.stdout

    def test_healthy_and_read_only(self):
        def snapshot():
            caches = self.home / 'Library' / 'Caches'
            return {p: (p.stat().st_mtime_ns, p.stat().st_size) for p in self.home.rglob('*')
                    if p.is_file() and not (sys.platform == 'darwin' and caches in p.parents)}

        before = snapshot()
        out = self.doctor()
        self.assertIn('PASS installed cache matches', out)
        self.assertIn('PASS plugin hook', out)
        self.assertIn('PASS usage database', out)
        self.assertIn('PASS latest audit format canary clean', out)
        self.assertIn('WARN optional scheduler', out)
        after = snapshot()
        self.assertEqual(before, after)
        self.assertIn('usage:', self.doctor('--help'))

    def test_empty_and_live_wal(self):
        wal = Path(str(self.db) + '-wal')
        wal.touch()
        self.assertIn('PASS usage database ingest within 7 days', self.doctor())
        wal.unlink()
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE files SET ingested_at='2000-01-01T00:00:00+00:00'")
            conn.commit()
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA wal_autocheckpoint=0')
            conn.execute('INSERT INTO files VALUES (?)', (datetime.now(timezone.utc).isoformat(),))
            conn.commit()
            self.assertGreater(wal.stat().st_size, 0)
            with sqlite3.connect(self.db.as_uri() + '?immutable=1', uri=True) as immutable:
                self.assertEqual(immutable.execute('SELECT MAX(ingested_at) FROM files').fetchone()[0],
                                 '2000-01-01T00:00:00+00:00')
            self.assertIn('PASS usage database ingest within 7 days', self.doctor())
            link = self.home / 'linked.db'
            link.symlink_to(self.db)
            self.env['KAIZEN_USAGE_DB'] = str(link)
            self.assertIn('PASS usage database ingest within 7 days', self.doctor())

    def test_stale_cache_and_hooks(self):
        (self.cache / 'scripts/kaizen-link').write_text('stale')
        self.assertIn('WARN installed cache differs', self.doctor())
        (self.root / 'hooks/hooks.json').write_text('{}')
        self.assertIn('FAIL plugin hook', self.doctor())
        (self.root / 'hooks/hooks.json').unlink()
        self.assertIn('FAIL plugin hook', self.doctor())

    def test_session_audit_registration_and_cron(self):
        path = self.root / 'hooks/hooks.json'
        data = json.loads(path.read_text())
        data['hooks']['SessionStart'][0]['hooks'].pop()
        path.write_text(json.dumps(data))
        self.assertIn('FAIL plugin hook', self.doctor())
        self.executable('crontab', "echo '0 0 * * * command # agent-kaizen-audit'")
        self.assertIn('scheduler job file found', self.doctor())

    def test_prefixed_canary(self):
        self.canary('format_canary: v1 unknown_records=1 missing_usage=0 cli=2.0')
        self.assertIn('WARN latest audit reports transcript format drift', self.doctor())
        self.canary('format_canary: v1 unknown_records=0 missing_usage=0 cli=2.0')
        self.assertIn('PASS latest audit format canary clean', self.doctor())

    def test_dependencies(self):
        (self.bin / 'jq').unlink()
        self.executable('python3', 'echo Python 3.8.0')
        out = self.doctor()
        self.assertIn('WARN jq missing', out)
        self.assertIn('WARN python3 is older', out)
        self.executable('python3', 'echo unknown')
        self.assertIn('WARN python3 missing or version unknown', self.doctor())

    def test_data_and_config(self):
        pricing = self.root / 'scripts/pricing.json'
        data = json.loads(pricing.read_text())
        data['source']['checked'] = '2000-01-01'
        pricing.write_text(json.dumps(data))
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE files SET ingested_at='2000-01-01T00:00:00+00:00'")
        (self.claude / 'agent-kaizen.json').write_text('{"pendingDays": 0}')
        out = self.doctor()
        self.assertIn('WARN pricing date', out)
        self.assertIn('WARN usage database ingest', out)
        self.assertIn('WARN scheduled config invalid', out)
        (self.claude / 'agent-kaizen.json').write_text('{')
        self.assertIn('WARN scheduled config invalid', self.doctor())

    def test_canary_drift_and_unknown(self):
        self.canary('v1 unknown_records=1 missing_usage=0 cli=2.0')
        self.assertIn('WARN latest audit reports transcript format drift', self.doctor())
        for value in ('v1 unknown_records=0 missing_usage=0 cli=unknown', 'v2'):
            self.canary(value)
            self.assertIn('WARN latest audit format canary missing or unknown', self.doctor())
        self.report.write_text('<!-- token-audit-headline {} -->\n')
        self.assertIn('WARN latest audit format canary missing or unknown', self.doctor())
        self.report.unlink()
        self.assertIn('WARN latest audit format canary missing or unknown', self.doctor())


if __name__ == '__main__':
    unittest.main()
