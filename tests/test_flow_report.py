import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/flow-report'
KEYS = {'packets', 'events', 'malformed_lines', 'anomalies', 'open_final_states',
        'lead_times', 'states', 'queue_touch', 'top_waits', 'wip', 'max_wip'}


def event(ident, state, second, offset='Z'):
    return {'id': ident, 'state': state, 'ts': f'2026-01-01T00:00:{second:02d}{offset}'}


class FlowReportTests(unittest.TestCase):
    def report(self, events, raw=()):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'events.jsonl'
            path.write_text(''.join(json.dumps(e) + '\n' for e in events) + ''.join(x + '\n' for x in raw))
            result = subprocess.run([sys.executable, str(SCRIPT), '--events', str(path), '--json'],
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)

    def test_out_of_order(self):
        result = self.report([event('a', 'landed', 20), event('a', 'queued', 0), event('a', 'checks', 5)])
        self.assertEqual(result['lead_times'][0]['seconds'], 20)
        self.assertEqual(result['states']['checks']['total_s'], 15)

    def test_identical_timestamps_stable(self):
        result = self.report([event('b', 'queued', 0), event('a', 'queued', 0),
                              event('a', 'checks', 0), event('a', 'landed', 0),
                              event('b', 'landed', 0), event('a', 'review', 0)])
        self.assertEqual(result['states']['queued']['count'], 2)
        self.assertEqual(result['anomalies'][0]['state'], 'review')
        self.assertEqual(result['wip'], [{'ts': '2026-01-01T00:00:00Z', 'wip': 0}])

    def test_repeated_states(self):
        r = self.report([event('a', 'round-1', 0), event('a', 'round-2', 4), event('a', 'landed', 9)])
        self.assertEqual(r['states']['round'], {'count': 2, 'total_s': 9, 'p50_s': 4, 'p90_s': 5})

    def test_after_terminal_excluded(self):
        r = self.report([event('a', 'queued', 0), event('a', 'failed', 3), event('a', 'checks', 8)])
        self.assertEqual(r['events'], 3)
        self.assertEqual(r['anomalies'], [{'id': 'a', 'ts': '2026-01-01T00:00:08Z',
                                          'state': 'checks', 'reason': 'after terminal event'}])
        self.assertEqual(r['lead_times'][0]['seconds'], 3)
        self.assertEqual(r['queue_touch']['touch_s'], 0)

    def test_incomplete(self):
        r = self.report([event('a', 'queued', 0), event('a', 'checks', 3)])
        self.assertEqual(r['lead_times'][0], {'id': 'a', 'seconds': None, 'complete': False})
        self.assertEqual(r['open_final_states'], 1)
        self.assertEqual(set(r['states']), {'queued'})

    def test_interleaved_packets(self):
        r = self.report([event('a', 'queued', 0), event('b', 'dispatched', 1),
                         event('a', 'checks', 3), event('b', 'failed', 5), event('a', 'landed', 7)])
        self.assertEqual([x['seconds'] for x in r['lead_times']], [7, 4])
        self.assertEqual(r['max_wip'], 2)

    def test_percentiles(self):
        for n, p50, p90 in [(1, 1, 1), (2, 1, 2), (10, 5, 9)]:
            with self.subTest(n=n):
                events = [e for i in range(1, n + 1) for e in
                          (event(str(i), 'checks', 0), event(str(i), 'landed', i))]
                state = self.report(events)['states']['checks']
                self.assertEqual((state['p50_s'], state['p90_s']), (p50, p90))

    def test_shares_and_zero_denominator(self):
        r = self.report([event('a', 'queued', 0), event('a', 'checks', 2), event('a', 'landed', 8)])
        self.assertEqual(r['queue_touch'], {'wait_s': 2, 'touch_s': 6, 'wait_share': .25,
                                            'touch_share': .75, 'intervals': 2})
        q = self.report([event('a', 'queued', 0), event('a', 'landed', 0)])['queue_touch']
        self.assertIsNone(q['wait_share'])
        self.assertIsNone(q['touch_share'])
        self.assertEqual(q['intervals'], 1)

    def test_top_ten_and_ties(self):
        events = [e for i in reversed(range(12)) for e in
                  (event(f'{i:02}', 'slot-wait', 0), event(f'{i:02}', 'landed', 5))]
        self.assertEqual([x['id'] for x in self.report(events)['top_waits']],
                         [f'{i:02}' for i in range(10)])
        events = [event('z', 'queued', 1), event('z', 'landed', 6),
                  event('a', 'queued', 0), event('a', 'landed', 5)]
        self.assertEqual([x['id'] for x in self.report(events)['top_waits']], ['a', 'z'])

    def test_wip_rules(self):
        r = self.report([event('a', 'queued', 0), event('a', 'checks', 1),
                         event('b', 'queued', 2), event('b', 'landed', 2),
                         event('c', 'failed', 3), event('a', 'landed', 4)])
        self.assertEqual([x['wip'] for x in r['wip']], [1, 1, 1, 1, 0])
        self.assertEqual(r['max_wip'], 1)

    def test_malformed(self):
        raw = ['{', '{}', json.dumps(event('a', 'unknown', 0)),
               json.dumps(event('a', 'round-0', 0)),
               json.dumps({'id': 'a', 'state': 'queued', 'ts': '2026-01-01T00:00:00'}), '[]']
        r = self.report([event('ok', 'landed', 0)], raw)
        self.assertEqual(r['malformed_lines'], 6)
        self.assertEqual(r['packets'], 1)

    def test_offsets(self):
        r = self.report([{'id': 'a', 'state': 'queued', 'ts': '2026-01-01T02:00:00+02:00'},
                         event('a', 'landed', 5)])
        self.assertEqual(r['lead_times'][0]['seconds'], 5)
        self.assertEqual(r['top_waits'][0]['start'], '2026-01-01T00:00:00Z')

    def test_empty(self):
        r = self.report([])
        self.assertEqual((r['packets'], r['events'], r['max_wip']), (0, 0, 0))
        with tempfile.NamedTemporaryFile() as f:
            result = subprocess.run([sys.executable, str(SCRIPT), '--events', f.name], text=True, capture_output=True)
            self.assertIn('no events', result.stdout)
            self.assertEqual(result.returncode, 0)

    def test_missing_file(self):
        result = subprocess.run([sys.executable, str(SCRIPT), '--events', '/nonexistent/flow-events'], capture_output=True)
        self.assertEqual(result.returncode, 2)

    def test_json_keys(self):
        self.assertEqual(set(self.report([])), KEYS)


if __name__ == '__main__':
    unittest.main()
