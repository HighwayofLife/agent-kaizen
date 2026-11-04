import csv
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'notes-ledger'
HEADER = 'date,category,change,source,status,measured\n'
TIMELINE = ('Introduction.\n\n## 2026-10-01 to 2026-10-07\n\n'
            '| date | change | status | measured |\n| --- | --- | --- | --- |\n'
            '| 2026-10-01 | Existing | active | no |\n\nFooter.\n')


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.csv = self.root / 'changes.csv'
        self.timeline = self.root / 'timeline.md'
        self.csv.write_text(HEADER + '2026-10-01,test,Existing,manual,active,no\n')
        self.timeline.write_text(TIMELINE)
        (self.root / 'agent-kaizen.json').write_text(json.dumps({'notesLedger': {
            'csv': str(self.csv), 'timeline': str(self.timeline)}}))
        self.env = dict(os.environ, CLAUDE_CONFIG_DIR=str(self.root))

    def run_cli(self, *args, env=None):
        return subprocess.run(['python3', str(SCRIPT), *args], text=True,
                              capture_output=True, env=env or self.env)

    def add_args(self, change='New, change', date='2026-10-03'):
        return ['add', '--date', date, '--category', 'test', '--change', change,
                '--why', 'because', '--measure', 'count', '--source', 'manual']

    def rows(self):
        with self.csv.open(newline='') as f:
            return list(csv.DictReader(f))

    def test_add_and_retry(self):
        original = self.csv.read_text()
        result = self.run_cli(*self.add_args())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.csv.read_text().startswith(original))
        self.assertEqual(self.rows()[-1]['change'], 'New, change Why: because Measure: count')
        expected = TIMELINE.replace('| 2026-10-01 | Existing | active | no |\n',
                                    '| 2026-10-01 | Existing | active | no |\n| 2026-10-03 | New, change | active | no |\n')
        self.assertEqual(self.timeline.read_text(), expected)
        result = self.run_cli(*self.add_args())
        self.assertIn('already recorded', result.stdout)
        self.assertEqual(len(self.rows()), 2)

    def test_new_block_and_dry_run(self):
        before = self.csv.read_bytes(), self.timeline.read_bytes()
        self.assertEqual(self.run_cli(*self.add_args(date='2026-10-18'), '--dry-run').returncode, 0)
        self.assertEqual(before, (self.csv.read_bytes(), self.timeline.read_bytes()))
        self.assertEqual(self.run_cli(*self.add_args(date='2026-10-18')).returncode, 0)
        self.assertTrue(self.timeline.read_text().startswith(TIMELINE))
        self.assertIn('## 2026-10-15 to 2026-10-21', self.timeline.read_text())

    def test_missing_config(self):
        (self.root / 'agent-kaizen.json').unlink()
        result = self.run_cli(*self.add_args())
        self.assertEqual(result.returncode, 3)
        self.assertIn('no notesLedger.csv in agent-kaizen.json', result.stderr)

    def test_partial_failure_recovery(self):
        env = dict(self.env, NOTES_LEDGER_FAIL_AFTER_CSV='1')
        self.assertEqual(self.run_cli(*self.add_args(), env=env).returncode, 1)
        self.assertEqual(self.timeline.read_text(), TIMELINE)
        self.assertEqual(self.run_cli(*self.add_args()).returncode, 0)
        self.assertEqual(len(self.rows()), 2)
        self.assertIn('New, change', self.timeline.read_text())

    def test_concurrent_adds(self):
        commands = [self.add_args('First'), self.add_args('Second')]
        processes = [subprocess.Popen(['python3', str(SCRIPT), *cmd], env=self.env,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE) for cmd in commands]
        for p in processes:
            _, err = p.communicate()
            self.assertEqual(p.returncode, 0, err)
        self.assertEqual(len(self.rows()), 3)
        for text in ('First', 'Second'):
            self.assertIn(text, self.timeline.read_text())

    def test_set_and_ambiguous(self):
        self.assertEqual(self.run_cli(*self.add_args()).returncode, 0)
        result = self.run_cli('set', '--match', 'New, change', '--status', 'superseded',
                              '--measured', 'yes', '--effect', 'worked')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('before:', result.stdout)
        row = self.rows()[-1]
        self.assertEqual((row['status'], row['measured']), ('superseded', 'yes'))
        self.assertTrue(row['change'].endswith(' Result: worked'))
        self.assertIn('| 2026-10-03 | New, change | superseded | yes |', self.timeline.read_text())
        before = self.csv.read_bytes(), self.timeline.read_bytes()
        for match in ('missing', ''):
            self.assertEqual(self.run_cli('set', '--match', match, '--measured', 'no').returncode, 2)
            self.assertEqual(before, (self.csv.read_bytes(), self.timeline.read_bytes()))

    def test_help(self):
        for args in (['--help'], ['add', '--help'], ['set', '--help']):
            self.assertEqual(self.run_cli(*args).returncode, 0)


if __name__ == '__main__':
    unittest.main()
