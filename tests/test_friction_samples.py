"""Private synthetic samples: bounded reads, exact joins and local load evidence."""
from collections import Counter
from datetime import timedelta
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_friction_claude import AUDIT, SINCE, OPTIONS, start, end
from test_scripts import jsonl

class FrictionSamplesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        env = patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': str(self.root / 'empty')})
        env.start()
        self.addCleanup(env.stop)
        self.samples = self.root / 'samples'
        self.samples.mkdir(mode=0o700)
        self.project = self.root / 'project'
        self.warnings = Counter()

    def sample(self, tool='one', second=200, duration='130000', session='fixture-session', cpu='4', load='4'):
        return '\t'.join((str(int((SINCE.timestamp() + second) * 1000)), session, tool, duration, load, cpu)) + '\n'

    def write(self, text, day='2025-01-01'):
        path = self.samples / (day + '.tsv')
        path.write_text(text)
        path.chmod(0o600)
        return path

    def read(self, **kwargs):
        return AUDIT['read_samples'](self.samples, SINCE, self.warnings, until=SINCE + timedelta(days=2), **kwargs)

    def collect(self, **kwargs):
        jsonl(self.project / 'fixture.jsonl', self.rows)
        return AUDIT['collect']([self.project], self.root / 'absent', SINCE, {}, None, OPTIONS,
                                samples_dir=self.samples, **kwargs)

    def test_measured_join_and_prompted_wait(self):
        self.rows = [start('one', 0), end('one', 200, permissionDecision={'source': 'user_temporary'})]
        self.write(self.sample())
        f = self.collect()['friction']
        self.assertEqual(f['summary']['slow_calls'][0]['seconds_total'], 130)
        self.assertEqual(f['summary']['measured'], 1)
        self.assertEqual(f['permission_waits'], dict(count=1, seconds=70, basis='measured'))
        self.write(self.sample(duration='300000'))
        self.assertEqual(self.collect()['friction']['permission_waits']['seconds'], 0)
        self.write(self.sample(duration=''))
        f = self.collect()['friction']
        self.assertEqual(f['summary']['samples'], 0)
        self.assertEqual(f['permission_waits']['basis'], 'upper_bound')
        self.assertEqual(f['permission_waits']['seconds'], 200)

    def test_duplicates_conflicts_sessions_and_timestamp_distance(self):
        self.rows = [start('one', 0), end('one', 200)]
        for second, measured in ((196, 1), (204, 1), (190, 0), (210, 0)):
            self.write(self.sample(second=second) * 2)
            self.assertEqual(self.collect()['friction']['summary']['measured'], measured)
        for text in (self.sample() + self.sample(duration='140000'), self.sample(session='other-session')):
            self.write(text)
            self.assertEqual(self.collect()['friction']['summary']['measured'], 0)
        self.rows[-1] = end('one', 200, toolUseResult={'durationMs': 150000})
        self.write(self.sample())
        self.assertEqual(self.collect()['friction']['summary']['slow_calls'][0]['seconds_total'], 150)
        self.rows += [end('one', 201)]
        self.assertEqual(self.collect()['friction']['summary']['samples'], 0)

    def test_missing_days_retention_race_and_private_files(self):
        self.assertEqual(self.read()['events'], {})
        with patch.dict(os.environ, AUDIT_DIR=str(self.root)):
            self.assertEqual(AUDIT['default_samples_dir'](), self.samples)
        path = self.write(self.sample())
        path.chmod(0o644)
        self.assertEqual(self.read()['events'], {})
        path.chmod(0o600)
        link = self.root / 'link'
        link.symlink_to(self.samples, target_is_directory=True)
        self.assertEqual(AUDIT['read_samples'](link, SINCE, Counter())['events'], {})
        path.unlink()
        path.symlink_to(self.root / 'missing')
        self.assertEqual(self.read()['events'], {})
        path.unlink()
        self.write(self.sample())
        with patch('os.stat', side_effect=FileNotFoundError):
            self.assertEqual(self.read()['events'], {})
        self.assertEqual(self.read()['events'][('fixture-session', 'one')][1], 130)

    def test_bounds_malformed_rows_and_disabled_collection(self):
        self.rows = [start('one', 0), end('one', 200)]
        self.write('broken\n' + self.sample(load='nan') + self.sample() + self.sample(tool='unfinished').rstrip('\n'))
        self.assertEqual(len(self.read()['events']), 1)
        self.assertGreaterEqual(self.warnings['malformed samples'], 3)
        globals_ = AUDIT['read_samples'].__globals__
        with patch.dict(globals_, SAMPLE_MAX_ROWS=1):
            self.assertEqual(self.read()['events'], {})
        with patch.dict(globals_, SAMPLE_MAX_BYTES=1):
            self.assertEqual(self.read()['events'], {})
        with patch.dict(globals_, FRICTION_PAIR_LIMIT=1):
            self.write(self.sample() + self.sample(tool='other'))
            self.assertEqual(self.read()['events'], {})
        with patch.dict(globals_, read_samples=lambda *a, **k: self.fail('disabled reader invoked')):
            self.assertNotIn('friction', self.collect(friction=False))
        self.write(self.sample(), day='2024-12-31')
        self.write(self.sample(), day='2099-01-04')
        self.assertNotIn('malformed samples', self.collect()['warnings'])

    def test_load_confirmation_requires_provenance_unique_points_and_compatible_cpus(self):
        calls = [(i * 100, i * 100 + 60, 60, 'cargo test', 'measured', False, ('claude', 'fixture')) for i in range(3)]
        calls += [(400, 490 + i, 90 + i, 'cargo test', 'measured', False, ('claude', 'fixture')) for i in range(3)]
        metrics = [(450 + i, .9, 4) for i in range(3)]
        heavy = AUDIT['heavy_timeline']
        self.assertEqual(heavy(calls, {'heavy_seconds': 60}, metrics)[0][0]['status'], 'unconfirmed')
        local = set(calls)
        self.assertEqual(heavy(calls, {'heavy_seconds': 60}, metrics, local)[0][0]['status'], 'flagged')
        for points in (metrics[:2], metrics[:1] * 3, [(1, .9, 4)] * 3, metrics[:2] + [(453, .9, 8)]):
            self.assertEqual(heavy(calls, {'heavy_seconds': 60}, points, local)[0][0]['status'], 'unconfirmed')
        codex = [c[:-1] + (('codex', 'fixture'),) for c in calls]
        self.assertEqual(heavy(codex, {'heavy_seconds': 60}, metrics, local)[0][0]['status'], 'unconfirmed')
        self.assertEqual(heavy(calls, {'heavy_seconds': 60}, [(450 + i, .7, 4) for i in range(3)], local)[0][0]['status'], 'ok')

    def test_catalogue_summary_and_end_to_end_load(self):
        self.rows = [row for i in range(4) for row in (start(str(i), 0), end(str(i), 200 + i))]
        text = ''.join(self.sample(str(i), second=200 + i) for i in range(4))
        stamp = int((SINCE.timestamp() + 100) * 1000)
        self.write(text + f'P\t{stamp}\t4\t4\tmdworker_shared\tprivate-process\n' * 2)
        f = self.collect()['friction']
        self.assertEqual(f['parallel_heavy']['status'], 'flagged')
        self.assertEqual(f['host_load']['process_hits'], {'spotlight': {'hits': 1, 'per_hour': 1.0}})
        self.assertNotIn('private-process', json.dumps(f))
        self.assertTrue(any('spotlight' in line for line in AUDIT['friction_sections'](f)))
        self.write(''.join(self.sample(str(i), second=200 + i, duration='') for i in range(4)))
        self.assertEqual(self.collect()['friction']['parallel_heavy']['status'], 'unconfirmed')
