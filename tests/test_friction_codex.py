"""Exercise Codex pairing with synthetic rollouts only."""
from datetime import timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_friction_claude import AUDIT, OPTIONS, SINCE
from test_scripts import jsonl


def row(kind, seconds, **fields):
    return dict(type=kind, timestamp=(SINCE + timedelta(seconds=seconds)).isoformat(), payload=fields)


def call(ident, seconds=1, **fields):
    return row('response_item', seconds, type='function_call', call_id=ident, **fields,
               arguments='{"command":["bash","-lc","cargo test --lib"]}')


def result(ident, seconds=5, output='Wall time: 120.5 seconds', **fields):
    return row('response_item', seconds, type='function_call_output', call_id=ident, **fields, output=output)


class FrictionCodexTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.rollout = self.root / '2025/01/01/rollout.jsonl'
        self.work = str(self.root / 'work')
        self.meta = row('session_meta', -2, cwd=self.work, cli_version='1.2.3')

    def collect(self, **options):
        return AUDIT['collect']([], self.root, SINCE, {}, None, OPTIONS, **options)

    def test_bounded_output_single_traversal_and_accounting(self):
        start = row('response_item', 1, type='custom_tool_call', call_id='private-id',
                    input='text(await tools.exec_command({cmd:"cargo test --lib"}))')
        end = row('response_item', 5, type='custom_tool_call_output', call_id='private-id',
                  output=[dict(type='input_text', text='Script completed\nWall time 125.5 seconds\nOutput:\n'
                               + 'private-body' * 2000 + ' upper limit on inotify watches reached')])
        usage = dict(input_tokens=7, output_tokens=3, total_tokens=10)
        jsonl(self.rollout, [self.meta, row('turn_context', -1, model='example', effort='medium'),
                             start, end, start, end,
                             row('event_msg', 6, type='token_count', info=dict(total_token_usage=usage))])
        original_open = Path.open
        original_loads = json.loads

        def loads(raw, *args, **kwargs):
            if isinstance(raw, bytes):
                self.assertNotIn(b'private-body', raw)
            return original_loads(raw, *args, **kwargs)

        with patch.object(Path, 'open', autospec=True, side_effect=original_open) as opened, patch.object(json, 'loads', loads):
            on = self.collect(cwd=[self.work])
        self.assertEqual(sum(entry.args[0] == self.rollout for entry in opened.call_args_list), 1)
        off = self.collect(cwd=[self.work], friction=False)
        friction = on.pop('friction')
        self.assertEqual(on, off)
        self.assertEqual(off['codex_sessions'][0]['effort'], 'medium')
        self.assertEqual(off['codex_sessions'][0]['tokens'], 10)
        self.assertEqual(off['format_canary']['1.2.3']['records'], 5)
        self.assertEqual(friction['basis'], 'measured')
        self.assertEqual(friction['summary']['measured'], 1)
        self.assertEqual(friction['summary']['slow_calls'][0]['seconds_total'], 125.5)
        self.assertFalse(any(friction['signals'].values()))
        self.assertNotIn('private', json.dumps(friction))

    def test_missing_invalid_and_conflicting_pairs(self):
        rows = [call('old', -1), result('old'), call('left'), result('orphan'), call(None), result(None),
                call('cross-file'), call('backward', 8), result('backward', 7),
                call('reversed'), result('reversed'), result('reversed', 9),
                result('out-first', 3), call('out-first', 3),
                call('cwd', cwd=self.work), result('cwd', cwd=str(self.root / 'elsewhere')),
                call('large'), result('large'), call('truncated'), call('fake-wall'),
                result('fake-wall', output='Output:\nWall time 300 seconds'),
                call('foreign-kind'),
                row('response_item', 5, type='custom_tool_call_output', call_id='foreign-kind',
                    output='Wall time 300 seconds')]
        rows[-7]['payload']['arguments'] = json.dumps(dict(cmd='ls', note='x' * 5000))
        jsonl(self.rollout, [self.meta, *rows])
        with self.rollout.open('a') as stream:
            output = 'Wall time 120 seconds\nOutput:\n' + 'x' * 5000
            stream.write(json.dumps(result('truncated', output=output))[:-1] + '\n')
        jsonl(self.rollout.with_name('other.jsonl'), [self.meta, result('cross-file')])
        self.assertEqual(self.collect(cwd=[self.work])['friction']['summary']['samples'], 0)

    def test_overlap_legacy_and_signals_without_duration(self):
        first = row('turn_context', 0, cwd=self.work, turn_id='a')
        second = row('turn_context', 3, cwd=self.work + '/nested', turn_id='b')
        legacy = dict(type='function_call', timestamp=first['timestamp'], call_id='a',
                      arguments=dict(cmd='npm test'), turn_id='a')
        jsonl(self.rollout, [self.meta, first, legacy, second, call('b', 4, turn_id='b'),
                             result('a', output='Wall time 150 seconds', turn_id='a'),
                             result('b', output='Wall time NaN seconds\nProcess exited with code 124\n'
                                    'waiting for the lock\nupper limit on inotify watches reached'),
                             result('b', output='Wall time NaN seconds\nProcess exited with code 124\n'
                                    'waiting for the lock\nupper limit on inotify watches reached')])
        data = self.collect(cwd=[self.work])
        friction = data['friction']
        self.assertEqual(friction['summary']['measured'], 1)
        self.assertEqual(friction['summary']['slow_calls'][0]['signature'], 'npm test')
        self.assertEqual((friction['signals']['timeout_hints'], friction['signals']['lock_phrases'],
                          friction['signals']['inotify']), (1, 1, 1))
        self.assertEqual(data['unknown_types'], {'function_call': 1})
