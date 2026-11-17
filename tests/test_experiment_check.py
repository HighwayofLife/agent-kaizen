"""Tests for the read-only experiment ledger checker."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/experiment-check'
HEADER = '| date | change | why | expected effect | measured effect | keep/revert | metric command | review date |\n| --- | --- | --- | --- | --- | --- | --- | --- |\n'


class ExperimentCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.directory = self.root / 'docs/kaizen'
        self.directory.mkdir(parents=True)
        self.env = dict(os.environ, CLAUDE_CONFIG_DIR=str(self.root / 'global'))

    def run_check(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), '--project', str(self.root), '--today', '2026-11-27', *args], text=True, capture_output=True, env=self.env)

    def ledger(self, text):
        (self.directory / 'LEDGER.md').write_text(text)

    def data(self, *args):
        result = self.run_check('--json', *args)
        return result, json.loads(result.stdout)

    def test_boundaries_legacy_and_closed(self):
        self.ledger(HEADER + '| 2026-11-17 | equal | | | pending | | `echo x` | 2026-11-27 |\n'
                    '| 2026-11-16 | old | | | pending | | | |\n'
                    '| 2026-11-17 | missing | | | pending | | | |\n'
                    '| 2026-11-27 | review | | | pending now | | `echo x` | 2026-11-26 |\n'
                    '| bad | done | | | done | | | bad |\n'
                    '| bad | reverted | | | pending | reverted yesterday | | bad |\n')
        result, data = self.data()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(data['counts'], dict(past_review=1, pending_too_long=1, missing_metadata=1, malformed=0))
        self.assertEqual(data['legacy_rows'], 1)
        self.assertEqual(set(data), {'project', 'today', 'pending_days', 'ledger', 'legacy_table', 'legacy_rows', 'metadata_since', 'findings', 'counts', 'status'})

    def test_legacy_table_and_missing(self):
        result = self.run_check()
        self.assertEqual(result.returncode, 0)
        self.assertIn('no ledger', result.stdout)
        self.ledger('| date | change | why | expected effect | measured effect | keep/revert |\n| --- | --- | --- | --- | --- | --- |\n| 2026-11-16 | old | | | pending | |\n')
        result, data = self.data('--pending-days', '11')
        self.assertEqual(result.returncode, 0)
        self.assertTrue(data['legacy_table'])
        self.assertEqual(data['legacy_rows'], 1)

    def test_escape_short_malformed_and_no_execution(self):
        marker = self.root / 'marker'
        self.ledger(HEADER + f'| 2026-11-27 | pipe | | | pending | | `touch {marker} \\| cat` | 2026-11-27 |\n'
                    '| bad | invalid | | | pending | | | wrong |\n| 2026-11-27 | short |\n')
        result, data = self.data()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(data['counts']['malformed'], 1)
        self.assertEqual(data['counts']['missing_metadata'], 1)
        self.assertFalse(marker.exists())
        self.ledger(HEADER + f'| 2026-11-17 | pipe | | | pending | | `touch {marker} \\| cat` | 2026-11-26 |\n')
        _, data = self.data()
        self.assertIn('| cat', data['findings'][0]['metric_command'])

    def test_config_precedence_and_invalid(self):
        global_dir = Path(self.env['CLAUDE_CONFIG_DIR'])
        global_dir.mkdir()
        config = global_dir / 'agent-kaizen.json'
        config.write_text('{"pendingDays": 7}')
        project_config = self.directory / 'config.json'
        self.ledger(HEADER)
        for invalid in (0, -1, 'x', True):
            project_config.write_text(json.dumps({'pendingDays': invalid}))
            result, data = self.data()
            self.assertEqual(data['pending_days'], 7)
            self.assertIn('invalid pendingDays', result.stderr)
        project_config.write_text('{"pendingDays": 5}')
        self.assertEqual(self.data()[1]['pending_days'], 5)
        self.assertEqual(self.data('--pending-days', '3')[1]['pending_days'], 3)
        self.assertEqual(self.run_check('--pending-days', '0').returncode, 2)
        config.unlink()
        project_config.unlink()
        self.assertEqual(self.data()[1]['pending_days'], 10)

    def test_due_checks(self):
        state = self.root / 'checks.json'
        self.assertEqual(self.run_check('--checks').returncode, 2)
        result, data = self.data('--checks', '--state-file', str(state))
        self.assertEqual(result.returncode, 1)
        self.assertEqual([c['status'] for c in data['checks']], ['never_run'] * 3)
        state.write_text(json.dumps({'models': '2026-10-28', 'roster': '2026-09-27',
                                     'whats-new': '2026-10-27', 'other': 'kept'}))
        original = state.read_bytes()
        result, data = self.data('--checks', '--state-file', str(state))
        self.assertEqual([c['status'] for c in data['checks']], ['fresh', 'overdue', 'overdue'])
        self.assertEqual(set(data['checks'][0]), {'name', 'last', 'cadence_days', 'age_days', 'status', 'reason'})
        self.assertEqual(state.read_bytes(), original)
        state.write_text('{"models": "2026-11-28", "roster": 3, "whats-new": "bad"}')
        self.assertEqual([c['status'] for c in self.data('--checks', '--state-file', str(state))[1]['checks']], ['unknown'] * 3)
        state.write_text('{')
        self.assertEqual([c['status'] for c in self.data('--checks', '--state-file', str(state))[1]['checks']], ['unknown'] * 3)
        self.assertEqual(self.run_check().stdout, 'experiment-check: 0 finding(s)\nno ledger\n')

    def test_errors_and_bounded_output(self):
        self.ledger('| date | change |\n| --- | --- |\n')
        self.assertEqual(self.run_check().returncode, 2)
        (self.directory / 'LEDGER.md').unlink()
        (self.directory / 'LEDGER.md').mkdir()
        self.assertEqual(self.run_check().returncode, 2)
        (self.directory / 'LEDGER.md').rmdir()
        self.ledger(HEADER + '| 2026-11-17 | item | | | pending | | | |\n' * 20)
        result = self.run_check()
        self.assertTrue(result.stdout.startswith('experiment-check: 20 finding(s)\n'))
        self.assertLess(len(result.stdout.splitlines()), 40)
        self.assertIn('... 12 more', result.stdout)


if __name__ == '__main__':
    unittest.main()
