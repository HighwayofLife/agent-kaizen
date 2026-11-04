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
        self.assertFalse(Path(str(self.csv) + '.lock').exists())
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
        with self.csv.open(newline='') as stream:
            lines = stream.readlines()
        self.assertTrue(all(line.endswith('\n') and len(next(csv.reader([line]))) == 6 for line in lines))
        timeline_lines = self.timeline.read_text().splitlines(keepends=True)
        self.assertTrue(all(line.endswith('\n') for line in timeline_lines))
        self.assertTrue(all(len(line.strip().strip('|').split('|')) == 4
                            for line in timeline_lines if line.startswith('|')))

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

    def test_retry_normalized_and_effect(self):
        change = 'New | item\ncontinued'
        self.assertEqual(self.run_cli(*self.add_args(change)).returncode, 0)
        self.assertEqual(self.run_cli(*self.add_args(change)).returncode, 0)
        self.assertEqual(self.timeline.read_text().count('New &#124; item continued'), 1)
        before = self.csv.read_bytes()
        result = self.run_cli('set', '--match', 'New | item', '--effect', 'worked', '--measured', 'yes')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.csv.read_bytes().startswith(before.split(b'2026-10-03')[0]))
        # The first write has succeeded; retrying must also repair the timeline.
        self.timeline.write_text(self.timeline.read_text().replace('| 2026-10-03 | New &#124; item continued | active | yes |', '| 2026-10-03 | New &#124; item continued | active | no |'))
        self.assertEqual(self.run_cli('set', '--match', 'New | item', '--effect', 'worked', '--measured', 'yes').returncode, 0)
        self.assertEqual(self.rows()[-1]['change'].count(' Result: worked'), 1)
        self.assertEqual(self.run_cli(*self.add_args(change)).returncode, 0)
        self.assertEqual(len(self.rows()), 2)

    def test_set_preserves_other_csv_bytes(self):
        self.assertEqual(self.run_cli(*self.add_args('Target')).returncode, 0)
        self.assertEqual(self.run_cli(*self.add_args('Untouched')).returncode, 0)
        before = self.csv.read_bytes().splitlines(keepends=True)
        result = self.run_cli('set', '--match', 'Target', '--status', 'planned')
        self.assertEqual(result.returncode, 0, result.stderr)
        after = self.csv.read_bytes().splitlines(keepends=True)
        self.assertEqual(before[:2] + before[3:], after[:2] + after[3:])

    def test_bad_config_and_ambiguous_message(self):
        (self.root / 'agent-kaizen.json').write_text('[]')
        result = self.run_cli(*self.add_args())
        self.assertEqual(result.returncode, 3)
        self.assertNotIn('Traceback', result.stderr)
        (self.root / 'agent-kaizen.json').write_text(json.dumps({'notesLedger': {'csv': str(self.csv)}}))
        self.assertEqual(self.run_cli(*self.add_args('Another')).returncode, 0)
        result = self.run_cli('set', '--match', '', '--effect', 'x')
        self.assertEqual(result.returncode, 2)
        self.assertIn('exactly one', result.stderr)

    def test_help(self):
        for args in (['--help'], ['add', '--help'], ['set', '--help']):
            self.assertEqual(self.run_cli(*args).returncode, 0)


class DueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.csv = self.root / 'changes.csv'
        self.csv.write_text(HEADER + '2020-01-10,test,Change Measure: count,manual,active,no\n')
        self.config = self.root / 'agent-kaizen.json'
        self.config.write_text(json.dumps({'notesLedger': {'csv': str(self.csv)}}))
        self.env = dict(os.environ, CLAUDE_CONFIG_DIR=str(self.root))
        self.scope = dict(codex='all', cwd=None, project=None, project_dirs=[], v=1, window='7d')

    def run_due(self, *args):
        return subprocess.run(['python3', str(SCRIPT), 'due', *args], env=self.env,
                              capture_output=True, text=True)

    def report(self, date, scope=None, value=10):
        path = self.root / 'audits' / ('token-audit-' + date + '.md')
        path.parent.mkdir(exist_ok=True)
        text = '<!-- token-audit-headline ' + json.dumps({'claude_context_per_call': value, 'claude_calls': 999}) + ' -->\n'
        if scope is not False:
            text += '<!-- token-audit-scope ' + json.dumps(scope or self.scope) + ' -->\n'
        path.write_text(text)

    def test_proposal_packets_and_read_only(self):
        import hashlib
        self.report('2020-01-01', value=10)
        self.report('2020-01-11', value=15)
        self.report('2020-01-12', value=20)
        project = self.root / 'project'
        log = project / 'out' / 'packets.jsonl'
        log.parent.mkdir(parents=True)
        rows = [dict(ts=f'2020-01-{day:02}T12:00:00Z', id=str(i), model='sonnet', effort='medium',
                     status='DONE', dispatches=1, rounds=0, wall_s=60)
                for day in (1, 11) for i in range(day * 100, day * 100 + 8)]
        log.write_text(''.join(json.dumps(row) + '\n' for row in rows))
        files = [p for p in self.root.rglob('*') if p.is_file()]
        hashes = {p: hashlib.sha256(p.read_bytes()).digest() for p in files}
        result = self.run_due('--project', str(project), '--json')
        self.assertEqual(result.returncode, 0, result.stderr)
        item = json.loads(result.stdout)
        self.assertEqual(item['intensity']['claude_context_per_call']['percent_change'], 100)
        self.assertNotIn('claude_calls', item['intensity'])
        self.assertEqual(item['packets'][0]['before_n'], 8)
        self.assertIn('n=8', item['proposal'])
        self.assertEqual(hashes, {p: hashlib.sha256(p.read_bytes()).digest() for p in self.root.rglob('*') if p.is_file()})

    def test_incompatible_and_missing_scope(self):
        self.report('2020-01-01', scope=False)
        self.report('2020-01-02', scope=dict(self.scope, window='30d'))
        self.report('2020-01-11')
        self.report('2020-01-12')
        self.assertEqual(json.loads(self.run_due('--json').stdout)['reason'], 'no comparable scope')

    def test_too_few_and_filters(self):
        self.report('2020-01-01')
        self.report('2020-01-11')
        self.csv.write_text(self.csv.read_text() + '2020-01-10,test,Done,manual,active,yes\n'
                            + '2020-01-10,test,Planned,manual,planned,no\n'
                            + '2999-01-01,test,Future,manual,active,no\n')
        items = [json.loads(line) for line in self.run_due('--json').stdout.splitlines()]
        self.assertEqual([item['reason'] for item in items], ['too few reports', 'row too new'])
        self.report('2020-01-12')
        project = self.root / 'project'
        log = project / 'out' / 'packets.jsonl'
        log.parent.mkdir(parents=True)
        log.write_text('')
        self.assertEqual(json.loads(self.run_due('--project', str(project), '--json').stdout.splitlines()[0])['packets'][0]['reason'], 'too few packets')

    def test_unconfigured(self):
        self.config.unlink()
        result = self.run_due()
        self.assertEqual((result.returncode, result.stdout.strip()), (0, 'notes-ledger: not configured'))


if __name__ == '__main__':
    unittest.main()
