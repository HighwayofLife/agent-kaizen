"""Synthetic timeline boundaries, bounded sweeps and private report comparisons."""
from copy import deepcopy
import json
import re
import hashlib
import os
from datetime import timedelta
from pathlib import Path
import random
import tempfile
import tracemalloc
import unittest
from unittest.mock import patch

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

    def test_staggered_contention_memory_is_bounded(self):
        calls = [call(i, i + 2000) for i in range(2000)]
        tracemalloc.start()
        try:
            AUDIT['heavy_timeline'](calls, THRESHOLDS, (), calls)
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
        self.assertLess(peak, 4 * 1024 * 1024)

    def test_contention_uses_binary_search_for_each_cohort(self):
        import bisect
        calls = [call(i * 100, i * 100 + 60, signature=str(i))
                 for i in range(400) for _ in range(3)]
        with patch.object(bisect, 'bisect_right', wraps=bisect.bisect_right) as search:
            AUDIT['heavy_timeline'](calls, THRESHOLDS, (), calls)
        self.assertEqual(search.call_count, 400)

    def test_contention_interval_visits_scale_with_gapped_cohorts(self):
        intersect = AUDIT['contention_intervals']

        def visits(count):
            accessed = 0

            class CountedIntervals:
                def __init__(self, intervals):
                    self.intervals = intervals

                def __len__(self):
                    return len(self.intervals)

                def __getitem__(self, index):
                    nonlocal accessed
                    accessed += 1
                    return self.intervals[index]

            def count_accesses(occupancy, intervals, ends):
                return intersect(occupancy, CountedIntervals(intervals), ends)

            calls = [call((band * count + i) * 100, (band * count + i) * 100 + 60, signature=str(i))
                     for band in range(4) for i in range(count) for _ in range(2)]
            with patch.dict(AUDIT['heavy_timeline'].__globals__, contention_intervals=count_accesses):
                AUDIT['heavy_timeline'](calls, THRESHOLDS, (), calls)
            return accessed

        small, large = visits(100), visits(400)
        self.assertGreater(small, 0)
        self.assertLess(large, 6 * small, (small, large))

    def test_contention_intersections_match_brute_force(self):
        rng = random.Random(20261118)

        for _ in range(25):
            calls = []
            for i in range(8):
                signature = str(i)
                calls.extend(call(i * 400 + j * 100, i * 400 + j * 100 + 60, signature=signature)
                             for j in range(3))
                calls.extend(call(start, start + 120, 120, signature=signature)
                             for start in rng.choices(range(3200, 4000, 40), k=5))
            rng.shuffle(calls)
            local = calls if rng.random() < 0.5 else rng.sample(calls, len(calls) - 8)
            samples = [(stamp, rng.choice((0.5, 0.9, 1.1)), 4) for stamp in range(3200, 4121, 20)]
            boundaries = sorted({stamp for item in local for stamp in item[:2]})
            reference_intervals = [(start, end) for start, end in zip(boundaries, boundaries[1:])
                                   if sum(a <= start < b for a, b, *_ in local) >= 2]

            def brute_force(occupancy, _intervals, _ends):
                return [(max(a, c), min(b, d)) for a, b in occupancy for c, d in reference_intervals
                        if max(a, c) < min(b, d)]

            analyze = AUDIT['heavy_timeline']
            actual = analyze(calls, THRESHOLDS, samples, local)
            with patch.dict(analyze.__globals__, contention_intervals=brute_force):
                self.assertEqual(actual, analyze(calls, THRESHOLDS, samples, local))

    def test_long_turn_cwds_do_not_accumulate(self):
        from test_friction_codex import row
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / '2025/01/01/rollout.jsonl'
            path.parent.mkdir(parents=True)
            with path.open('w') as stream:
                for i in range(1200):
                    stream.write(json.dumps(row('turn_context', 0, turn_id=str(i),
                                                cwd='/tmp/' + str(i) + 'x' * 10000)) + '\n')
            tracemalloc.start()
            try:
                AUDIT['collect']([], root, claude.SINCE, {}, None, claude.OPTIONS)
                peak = tracemalloc.get_traced_memory()[1]
            finally:
                tracemalloc.stop()
            self.assertLess(peak, 8 * 1024 * 1024)

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

    def test_polling_wait_and_overlap_must_belong_to_one_session(self):
        calls = [call(0, 350, poll=True), call(350, 700, poll=True, session='other'),
                 call(0, 120, 120)]
        self.assertFalse(AUDIT['polling_summary'](calls, 120)['flagged'])
        calls[1] = call(100, 800, poll=True, session='other')
        self.assertFalse(AUDIT['polling_summary'](calls, 120)['flagged'])
        calls.append(call(100, 220, 120, session='other'))
        self.assertTrue(AUDIT['polling_summary'](calls, 120)['flagged'])

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
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ):
            root = Path(directory).resolve()
            os.environ['KAIZEN_BACKUP_DIR'] = str(root / 'backups')
            secret = AUDIT['audit_machine_key'](create=True)
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

            def bind(report, value):
                raw = json.dumps(value).encode()
                report.with_suffix('.extract.json').write_bytes(raw)
                binding = dict(size=len(raw), sha256=hashlib.sha256(raw).hexdigest())
                text = re.sub(r'^<!-- token-audit-friction(?:-mac)? .*? -->\n', '', report.read_text(), flags=re.M)
                end = '<!-- token-audit-complete -->\n'
                if text.endswith(end):
                    mac = AUDIT['regression_binding_mac'](secret, report.name, binding)
                    text = (text.removesuffix(end) + '<!-- token-audit-friction ' + json.dumps(binding) + ' -->\n'
                            + '<!-- token-audit-friction-mac ' + mac + ' -->\n' + end)
                report.write_text(text)

            def compare(value, current_count=3):
                bind(old_report, value)
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
            newer = root / 'token-audit-newer.md'
            newer.write_text(header)
            os.utime(newer, (2_000_000_000, 2_000_000_000))
            self.assertEqual(compare(previous)['regressions'][0]['ratio'], 1.5)
            newer.write_text(completed.replace('token-audit-old.extract', 'token-audit-newer.extract'))
            incomparable = deepcopy(previous)
            incomparable['report'] = newer.name
            incomparable['friction']['comparisons'][0]['signature'] = 'npm test'
            bind(newer, incomparable)
            os.utime(newer, (2_000_000_000, 2_000_000_000))
            self.assertEqual(compare(previous)['regressions'][0]['ratio'], 1.5)
            extract.write_text('{broken')
            AUDIT['apply_regression'](dict(friction=deepcopy(friction)), root / 'new.md', scope, root)


class TimelineCollectionTests(claude.StubCase):
    collect = claude.FrictionClaudeTests.collect

    def setUp(self):
        super().setUp()
        self.env['KAIZEN_BACKUP_DIR'] = str(self.root / 'backups')
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

    def test_rejected_transcript_cannot_create_regression_baseline(self):
        rows = []
        for ident in range(3):
            rows += [start(str(ident), 1), end(str(ident), 61, toolUseResult=dict(durationMs=60000))]
        jsonl(self.session, rows)
        rejected = self.project / 'unsafe.jsonl'
        jsonl(rejected, rows)
        rejected.chmod(0o666)
        args = ('token-audit', '--json', '--since', '2025-01-01')
        first = json.loads(self.run_script(*args).stdout)
        self.assertNotIn('token-audit-friction-mac', Path(first['report_path']).read_text())
        self.assertEqual(first['friction']['comparisons'][0]['count'], 3)
        rejected.unlink()
        rows = []
        for ident in range(3):
            rows += [start(str(ident), 1), end(str(ident), 91, toolUseResult=dict(durationMs=90000))]
        jsonl(self.session, rows)
        second = json.loads(self.run_script(*args).stdout)
        self.assertFalse(second['friction']['regressions'])

    def test_cli_regression_rejects_replaced_report_and_extract(self):
        rows = []
        for ident in range(3):
            rows += [start(str(ident), 1), end(str(ident), 91, toolUseResult=dict(durationMs=90000))]
        jsonl(self.session, rows)
        args = ('token-audit', '--json', '--since', '2025-01-01')
        data = json.loads(self.run_script(*args).stdout)
        report = Path(data['report_path'])
        extract = Path(data['extract_path'])
        replaced = json.loads(extract.read_bytes())
        replaced['friction']['comparisons'][0]['p50'] = 60
        raw = json.dumps(replaced).encode()
        extract.write_bytes(raw)
        binding = json.dumps(dict(size=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
        report.write_text(re.sub(r'^<!-- token-audit-friction .*? -->$',
                                 '<!-- token-audit-friction ' + binding + ' -->', report.read_text(), flags=re.M))

        result = json.loads(self.run_script(*args, '--no-write').stdout)
        self.assertFalse(result['friction']['regressions'])

