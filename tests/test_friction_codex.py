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
        self.root = Path(temp.name).resolve()
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
        original_open = AUDIT['scan_codex'].__globals__['open_permission_transcript']
        original_loads = json.loads

        with patch.dict(AUDIT['scan_codex'].__globals__,
                        open_permission_transcript=unittest.mock.Mock(wraps=original_open)), patch.object(
                json, 'loads', wraps=original_loads) as loads:
            opened = AUDIT['scan_codex'].__globals__['open_permission_transcript']
            on = self.collect(cwd=[self.work])
        self.assertEqual(sum(b'private-body' in entry.args[0] for entry in loads.call_args_list
                             if isinstance(entry.args[0], bytes)), 2)
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

    def test_envelope_timestamp_and_numeric_output_canary(self):
        first = call('one')
        first['payload']['timestamp'] = (SINCE - timedelta(days=1)).isoformat()
        first = dict(type=first['type'], payload=first['payload'], timestamp=first['timestamp'])
        last = result('one', exit_code=0)
        jsonl(self.rollout, [self.meta, first, last])
        data = self.collect(cwd=[self.work])
        self.assertEqual(data['friction']['summary']['measured'], 1)
        self.assertEqual(data['format_canary']['1.2.3']['records'], 2)

    def test_envelope_timestamp_after_large_payload(self):
        last = result('one', output='Wall time: 10 seconds\nOutput:\n' + 'x' * 5000)
        last = dict(type=last['type'], payload=last['payload'], timestamp=last['timestamp'])
        jsonl(self.rollout, [self.meta, call('one'), last])
        data = self.collect(cwd=[self.work])
        self.assertEqual(data['friction']['summary']['measured'], 1)
        self.assertEqual(data['format_canary']['1.2.3']['records'], 2)

    def test_envelope_timestamp_skips_large_strings_with_bounded_memory(self):
        import tracemalloc
        stamp = '2025-01-01T00:00:05Z'
        record = json.dumps(dict(payload=dict(output='x' * 2_000_000), timestamp=stamp)).encode()
        tracemalloc.start()
        try:
            self.assertEqual(AUDIT['envelope_timestamp'](record), stamp)
            self.assertLess(tracemalloc.get_traced_memory()[1], 1_000_000)
        finally:
            tracemalloc.stop()

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
                                    'Stderr: waiting for the lock\nupper limit on inotify watches reached'),
                             result('b', output='Wall time NaN seconds\nProcess exited with code 124\n'
                                    'Stderr: waiting for the lock\nupper limit on inotify watches reached')])
        data = self.collect(cwd=[self.work])
        friction = data['friction']
        self.assertEqual(friction['summary']['measured'], 1)
        self.assertEqual(friction['summary']['slow_calls'][0]['signature'], 'npm test')
        self.assertEqual((friction['signals']['timeout_hints'], friction['signals']['lock_phrases'],
                          friction['signals']['inotify']), (1, 1, 1))
        self.assertEqual(data['unknown_types'], {'function_call': 1})

    def test_scalar_payloads_are_skipped_in_both_modes(self):
        malformed = [dict(call('unused'), payload=value, note='_call') for value in ('function_call', 42, None)]
        jsonl(self.rollout, [self.meta, *malformed, call('good'), result('good')])
        on = self.collect()
        self.assertEqual(on.pop('friction')['summary']['measured'], 1)
        self.assertEqual(on, self.collect(friction=False))

    def test_scope_uses_canonical_path_components(self):
        outside = str(self.root / 'elsewhere')
        Path(self.work).mkdir()
        Path(outside).mkdir()
        alias = Path(self.work) / 'alias'
        alias.symlink_to(outside, target_is_directory=True)
        for foreign in (self.work + '/../elsewhere', self.work + '-other', str(alias)):
            with self.subTest(foreign=foreign):
                jsonl(self.rollout, [self.meta, call('outside', cwd=foreign), result('outside', cwd=foreign),
                                     call('inside', cwd=self.work + '/child/..'), result('inside', cwd=self.work)])
                self.assertEqual(self.collect(cwd=[self.work])['friction']['summary']['measured'], 1)

    def test_future_header_allows_independent_in_window_turn_cwd(self):
        for header_cwd in (self.work, str(self.root / 'elsewhere')):
            with self.subTest(header_cwd=header_cwd):
                jsonl(self.rollout, [row('session_meta', 20, cwd=header_cwd),
                                     row('turn_context', -1, cwd=self.work),
                                     call('header-only'), result('header-only'),
                                     row('turn_context', 6, cwd=self.work, turn_id='current'),
                                     call('current', 7, turn_id='current'),
                                     result('current', 8, turn_id='current')])
                data = self.collect(cwd=[self.work], now=SINCE + timedelta(seconds=10))
                self.assertEqual(data['friction']['summary']['measured'], 1)

    def test_out_of_scope_future_header_does_not_exhaust_pair_limit(self):
        rows = [row('session_meta', 20, cwd=self.work)]
        rows += [call(str(i), cwd=str(self.root / 'other')) for i in range(3)]
        rows += [row('turn_context', 2, cwd=self.work), call('inside', 3), result('inside', 4)]
        jsonl(self.rollout, rows)
        with patch.dict(AUDIT['scan_codex'].__globals__, FRICTION_PAIR_LIMIT=2):
            data = self.collect(cwd=[self.work], now=SINCE + timedelta(seconds=10))
        self.assertFalse(data['friction']['summary']['capped'])
        self.assertEqual(data['friction']['summary']['measured'], 1)

    def test_rejected_id_overflow_fails_closed(self):
        outside = str(self.root / 'other')
        jsonl(self.rollout, [self.meta, call('a', cwd=outside), call('b', cwd=outside),
                             call('c', cwd=outside), call('c'), result('c')])
        with patch.dict(AUDIT['scan_codex'].__globals__, FRICTION_REJECTED_LIMIT=2):
            summary = self.collect(cwd=[self.work])['friction']['summary']
        self.assertTrue(summary['capped'])
        self.assertEqual(summary['measured'], 0)

    def test_invalid_first_observation_disqualifies_id_without_using_pair_slots(self):
        bad_args = call('reused')
        bad_args['payload']['arguments'] = '{'
        missing_timestamp = call('reused')
        del missing_timestamp['timestamp']
        for first in (bad_args, call('reused', -1), call('reused', 20),
                      dict(call('reused'), timestamp='invalid'), missing_timestamp,
                      call('reused', cwd=str(self.root / 'other')),
                      result('reused', cwd=str(self.root / 'other'))):
            with self.subTest(first=first):
                jsonl(self.rollout, [self.meta, first, call('reused', 3), result('reused', 4),
                                     call('good', 5), result('good', 6, output='Wall time: 121 seconds')])
                with patch.dict(AUDIT['scan_codex'].__globals__, FRICTION_PAIR_LIMIT=1):
                    summary = self.collect(cwd=[self.work], now=SINCE + timedelta(seconds=10))['friction']['summary']
                self.assertFalse(summary['capped'])
                self.assertEqual(summary['measured'], 1)
                self.assertEqual(summary['slow_calls'][0]['seconds_total'], 121)

    def test_future_header_does_not_rehabilitate_earlier_call_id(self):
        jsonl(self.rollout, [row('session_meta', 20, cwd=self.work),
                             call('reused'), result('reused'),
                             row('turn_context', 2, cwd=self.work),
                             call('reused', 3), result('reused', 4),
                             call('good', 5), result('good', 6, output='Wall time: 121 seconds')])
        with patch.dict(AUDIT['scan_codex'].__globals__, FRICTION_PAIR_LIMIT=1):
            summary = self.collect(cwd=[self.work], now=SINCE + timedelta(seconds=10))['friction']['summary']
        self.assertFalse(summary['capped'])
        self.assertEqual(summary['measured'], 1)
        self.assertEqual(summary['slow_calls'][0]['seconds_total'], 121)

    def test_output_requires_valid_bounded_json(self):
        prefix = 'Wall time: 150 seconds\nOutput:\n'
        jsonl(self.rollout, [self.meta, call('invalid'), call('oversized'),
                             result('oversized', output=prefix + 'x' * 70000)])
        with self.rollout.open('a') as stream:
            invalid = json.dumps(result('invalid', output=prefix + 'x' * 600))
            stream.write(invalid.replace('xxxx', r'\qxx', 1) + '\n')
        friction = self.collect()['friction']
        self.assertEqual(friction['summary']['measured'], 1)
        self.assertEqual(friction['summary']['slow_calls'][0]['seconds_total'], 150)

    def test_large_output_retains_timing_and_signals(self):
        output = 'Wall time: 121 seconds\nProcess exited with code 124\nOutput:\n' + 'x' * 20000
        jsonl(self.rollout, [self.meta, call('large'), result('large', output=output)])
        friction = self.collect()['friction']
        self.assertEqual(friction['summary']['slow_calls'][0]['seconds_total'], 121)
        self.assertEqual(friction['signals']['timeout_hints'], 1)

    def test_output_scope_fields_after_output(self):
        other = str(self.root / 'elsewhere')
        context = row('turn_context', 0, cwd=other, turn_id='old')

        def trailing(ident, output, **fields):
            event = result(ident, output=output)
            event['payload'].update(fields)
            return event

        jsonl(self.rollout, [self.meta, context, row('turn_context', 1, cwd=self.work),
                             call('good'), trailing('good', 'Wall time: 120 seconds', cwd=self.work),
                             call('foreign'), trailing('foreign', 'Wall time: 121 seconds', turn_id='old'),
                             call('large'), trailing('large', 'Wall time: 122 seconds\n' + 'x' * 70000,
                                                     cwd=other)])
        friction = self.collect(cwd=[self.work])['friction']
        self.assertEqual(friction['summary']['measured'], 1)
        self.assertEqual(friction['summary']['slow_calls'][0]['seconds_total'], 120)

    def test_lock_requires_failure_and_error_text(self):
        outputs = ['Process exited with code 0\nStderr: database is locked',
                   'Process exited with code 1\nOutput:\ndatabase is locked',
                   'Output:\nProcess exited with code 1\nStderr: database is locked',
                   'Process exited with code 1\nStderr: database is locked']
        events = [event for i, output in enumerate(outputs)
                  for event in (call(str(i)), result(str(i), output=output))]
        events += [call('status'), result('status', output='database is locked', status='error'),
                   call('stderr'), result('stderr', output='stdout', status='error', stderr='database is locked')]
        jsonl(self.rollout, [self.meta, *events])
        self.assertEqual(self.collect()['friction']['signals']['lock_phrases'], 3)

    def test_large_turn_ids_have_bounded_pending_storage_and_pair_normally(self):
        events = [self.meta]
        for i in range(40):
            turn = str(i) + 'x' * 20000
            events.extend((call(str(i)), result(str(i), turn_id=turn)))
        events.extend((call('ordinary', turn_id='turn-1'), result('ordinary', turn_id='turn-1'),
                       call('mismatch', turn_id='turn-1'), result('mismatch', turn_id='turn-2')))
        jsonl(self.rollout, events)
        original = AUDIT['finish_codex_pairs']
        def inspect(pairs, *args):
            for pair in pairs.values():
                if pair:
                    for item in pair:
                        if item:
                            if item[3]['turn_id'] is not None:
                                self.assertLessEqual(len(item[3]['turn_id']), 256)
            return original(pairs, *args)
        with patch.dict(AUDIT['collect'].__globals__, finish_codex_pairs=inspect):
            self.assertEqual(self.collect()['friction']['summary']['measured'], 41)

    def test_lock_conflicting_exit_metadata_prefers_explicit_exit_code(self):
        events = [call('zero'), result('zero', exit_code=0,
                  output='Process exited with code 1\nOutput:\ndatabase is locked'),
                  call('failure'), result('failure', exit_code=1,
                  output='Process exited with code 0\nOutput:\ndatabase is locked')]
        jsonl(self.rollout, [self.meta, *events])
        self.assertEqual(self.collect()['friction']['signals']['lock_phrases'], 1)

    def test_lock_in_combined_output_requires_nonzero_exit(self):
        for code, expected in ((0, 0), (1, 1)):
            with self.subTest(code=code):
                jsonl(self.rollout, [self.meta, call('combined'), result(
                    'combined', output=f'Process exited with code {code}\nOutput:\ndatabase is locked')])
                self.assertEqual(self.collect()['friction']['signals']['lock_phrases'], expected)
