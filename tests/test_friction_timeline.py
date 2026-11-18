"""Synthetic timeline boundaries, bounded sweeps and private report comparisons."""
from copy import deepcopy
import json
from datetime import timedelta
from pathlib import Path
import tempfile
import unittest

import test_friction_claude as claude
from test_friction_claude import AUDIT, start, end
from test_scripts import jsonl


THRESHOLDS = dict(heavy_seconds=60, slow_call_seconds=120)


def call(start=0, end=60, seconds=60, signature='cargo test', basis='measured', poll=False, session='s'):
    return (start, end, seconds, signature, basis, poll, session)


class TimelineTests(unittest.TestCase):
    def heavy(self, calls, **thresholds):
        return AUDIT['heavy_timeline'](calls, dict(THRESHOLDS, **thresholds))

    def test_half_open_ties_and_threshold(self):
        calls = [call(i * 60, (i + 1) * 60) for i in range(6)]
        rows, parallel = self.heavy(calls)
        self.assertEqual(parallel['peak'], 1)
        self.assertEqual((rows[0]['overlapped_n'], rows[0]['alone_n']), (0, 6))
        self.assertEqual(self.heavy(calls, heavy_seconds=61)[1]['peak'], 0)
        self.assertEqual(self.heavy([call()] * 3)[1]['peak'], 3)

    def test_contention_exact_ratio_without_load_and_separate_bases(self):
        calls = [call(i * 100, i * 100 + 60) for i in range(3)]
        calls += [call(400, 490, 90)] * 3
        rows, parallel = self.heavy(calls)
        self.assertEqual((rows[0]['ratio'], rows[0]['status']), (1.5, 'unconfirmed'))
        self.assertEqual(parallel['status'], 'unconfirmed')
        self.assertIsNone(parallel['load_ratio_median'])
        mixed = [call(i * 100, i * 100 + 60, basis='row_gap') for i in range(3)] + calls[3:]
        rows, _ = self.heavy(mixed)
        self.assertTrue(all(row['ratio'] is None for row in rows))
        self.assertEqual({row['basis'] for row in rows}, {'measured', 'row_gap'})
        self.assertIsNone(self.heavy(calls[:2] + calls[3:])[0][0]['ratio'])

    def test_high_fanout_is_bounded_and_order_independent(self):
        calls = [call(i % 2, 100, signature='cargo test') for i in range(16000)]
        rows, parallel = self.heavy(calls)
        self.assertEqual(parallel['peak'], 16000)
        self.assertEqual(rows[0]['overlapped_n'], 16000)
        self.assertEqual(self.heavy(list(reversed(calls))), (rows, parallel))

    def test_codex_pair_timestamps_reach_timeline(self):
        from test_friction_codex import call as codex_call, result, row
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = [row('session_meta', -1, cwd=str(root))]
            for ident in range(3):
                rows += [codex_call(str(ident), 1), result(str(ident), 121)]
            jsonl(root / '2025/01/01/rollout.jsonl', rows)
            data = AUDIT['collect']([], root, claude.SINCE, {}, None, claude.OPTIONS)
            self.assertEqual(data['friction']['parallel_heavy']['peak'], 3)
            self.assertEqual(data['friction']['comparisons'][0]['basis'], 'measured')
            self.assertNotIn(str(root), json.dumps(data['friction']))

    def test_polling_ten_minutes_union_and_sibling_boundaries(self):
        polling = AUDIT['polling_summary']
        wait = call(0, 600, 600, signature='sleep', poll=True)
        self.assertFalse(polling([wait], 120)['flagged'])
        self.assertFalse(polling([wait, call(600, 800, 200)], 120)['flagged'])
        self.assertFalse(polling([wait, call(599, 800, 200, session='other')], 120)['flagged'])
        self.assertFalse(polling([call(0, 599, poll=True), call(0, 120, 120)], 120)['flagged'])
        result = polling([wait] * 100 + [call(599, 800, 120)], 120)
        self.assertTrue(result['flagged'])
        self.assertEqual(result['seconds'], 600)
        self.assertTrue(AUDIT['is_polling']('while true; do sleep 5; done'))
        self.assertFalse(AUDIT['is_polling']('echo private-sleep'))

    def test_measured_occupancy_cannot_include_idle_gap_or_extend_pair(self):
        calls = []
        record = AUDIT['timeline_call']
        end = claude.SINCE + timedelta(seconds=600)
        record(calls, claude.SINCE, end, 1, 'sleep', True, True)
        self.assertEqual(calls[0][1] - calls[0][0], 1)
        record(calls, claude.SINCE, end, 900, 'cargo test', True)
        self.assertEqual(calls[1][1] - calls[1][0], 600)
        record(calls, end, end, 1, 'cargo test', True)
        self.assertEqual(len(calls), 2)

    def test_regression_requires_completed_matching_cohort(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old_report = root / 'token-audit-old.md'
            scope = dict(v=1, window='7d', cwd=['synthetic-scope'])
            header = ('<!-- token-audit-headline {} -->\n<!-- token-audit-scope ' + json.dumps(scope)
                      + ' -->\n<!-- token-audit-extract {"v": 1, "file": "token-audit-old.extract.json"} -->\n')
            completed = header + '<!-- token-audit-complete -->\n'
            old_report.write_text(completed)
            cohort = dict(signature='cargo test', basis='measured', count=3, p50=60)
            friction = dict(v=1, thresholds=THRESHOLDS, window=dict(kind='rolling', seconds=604800),
                            basis='measured', summary=dict(capped=False), comparisons=[cohort], flags=[], regressions=[])
            previous = dict(v=1, scope=scope, report=old_report.name, friction=friction)
            extract = root / 'token-audit-old.extract.json'

            def compare(value, current_count=3):
                extract.write_text(json.dumps(value))
                data = dict(friction=deepcopy(friction))
                data['friction']['comparisons'][0]['p50'] = 90
                data['friction']['comparisons'][0]['count'] = current_count
                AUDIT['apply_regression'](data, root / 'token-audit-new.md', scope, root)
                return data['friction']

            result = compare(previous)
            self.assertEqual(result['regressions'][0]['ratio'], 1.5)
            self.assertEqual(result['flags'][0]['id'], 'regression')
            self.assertFalse(compare(previous, current_count=2)['regressions'])
            old_report.write_text(completed.replace(json.dumps(scope), json.dumps(dict(scope, cwd=['other-scope']))))
            self.assertFalse(compare(previous)['regressions'])
            old_report.write_text(completed)
            for field, value in [('scope', {}), ('report', 'other.md')]:
                invalid = deepcopy(previous)
                invalid[field] = value
                self.assertFalse(compare(invalid)['regressions'])
            for field, value in [('window', {}), ('thresholds', {}), ('basis', 'row_gap')]:
                invalid = deepcopy(previous)
                invalid['friction'][field] = value
                self.assertFalse(compare(invalid)['regressions'])
            for field, value in [('count', 2), ('p50', float('nan')), ('basis', 'row_gap')]:
                invalid = deepcopy(previous)
                invalid['friction']['comparisons'][0][field] = value
                self.assertFalse(compare(invalid)['regressions'])
            old_report.write_text(header)
            self.assertFalse(compare(previous)['regressions'])
            old_report.write_text(completed)
            invalid = deepcopy(previous)
            invalid['friction']['summary']['capped'] = True
            self.assertFalse(compare(invalid)['regressions'])
            extract.write_text('{broken')
            AUDIT['apply_regression'](dict(friction=deepcopy(friction)), root / 'new.md', scope, root)


class TimelineCollectionTests(claude.StubCase):
    collect = claude.FrictionClaudeTests.collect

    def setUp(self):
        super().setUp()
        self.project = self.home / '.claude/projects/example'
        self.session = self.project / 'fixture.jsonl'

    def test_collection_reports_unconfirmed_and_no_actionable_overlap(self):
        rows = []
        for ident in range(3):
            rows += [start(str(ident), 1), end(str(ident), 121, toolUseResult=dict(durationMs=120000))]
        jsonl(self.session, rows)
        friction = self.collect()['friction']
        self.assertEqual(friction['parallel_heavy']['peak'], 3)
        self.assertEqual(friction['parallel_heavy']['status'], 'unconfirmed')
        self.assertFalse({'contention', 'parallel-heavy'} & {row['id'] for row in friction['flags']})
        self.assertNotIn('fixture-session', json.dumps(friction))

    def test_cli_regression_uses_completed_report_and_extract(self):
        for seconds in (60, 90):
            rows = []
            for ident in range(3):
                rows += [start(str(ident), 1), end(str(ident), seconds + 1,
                                                 toolUseResult=dict(durationMs=seconds * 1000))]
            jsonl(self.session, rows)
            data = json.loads(self.run_script('token-audit', '--json', '--since', '2025-01-01').stdout)
            if seconds == 60:
                self.assertFalse(data['friction']['regressions'])
        self.assertEqual(data['friction']['regressions'][0]['ratio'], 1.5)

