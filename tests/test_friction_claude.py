"""Offline coverage for bounded Claude timing and the audit extract."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import runpy
from unittest.mock import patch

from test_scripts import SCRIPTS, StubCase, jsonl


AUDIT = runpy.run_path(str(SCRIPTS / 'token-audit'))
SINCE = datetime(2025, 1, 1, tzinfo=timezone.utc)
OPTIONS = dict(stuck_repeats=3, fact_sessions=3, prune_prompts=10,
               prune_min_sessions=2, prune_sessions=5)


def row(kind, block, seconds, session='fixture-session', **extra):
    return dict(type=kind, timestamp=(SINCE + timedelta(seconds=seconds)).isoformat(),
                sessionId=session, message=dict(content=[block]), **extra)


def start(ident, seconds, command='cargo test --lib', **extra):
    return row('assistant', dict(type='tool_use', id=ident, name='Bash',
                                 input=dict(command=command)), seconds, **extra)


def end(ident, seconds, **extra):
    return row('user', dict(type='tool_result', tool_use_id=ident, content='private fixture output'),
               seconds, **extra)


class FrictionClaudeTests(StubCase):
    def setUp(self):
        super().setUp()
        self.env.pop('COPILOT_HOME', None)
        self.project = self.home / '.claude/projects/example'
        self.session = self.project / 'fixture.jsonl'

    def audit(self, *args):
        return json.loads(self.run_script('token-audit', '--json', *args).stdout)

    def collect(self, **kwargs):
        with patch.dict('os.environ', {'CLAUDE_CONFIG_DIR': str(self.root / 'empty')}):
            return AUDIT['collect']([self.project], self.root / 'absent', SINCE, {}, None, OPTIONS, **kwargs)

    def test_scan_decodes_claude_rows_once(self):
        jsonl(self.session, [start('one', 0), end('one', 3)])
        with patch.object(json, 'loads', wraps=json.loads) as loads:
            self.assertEqual(self.collect()['friction']['summary']['samples'], 1)
        self.assertEqual(sum(b'private fixture output' in entry.args[0] for entry in loads.call_args_list
                             if isinstance(entry.args[0], bytes)), 1)

    def test_fractional_timestamp_does_not_gate_claude_usage(self):
        begin = start('one', 0)
        begin['message'].update(id='usage', usage=dict(input_tokens=10, output_tokens=5))
        for fraction in ('.1234Z', r'.12\u0033Z'):
            with self.subTest(fraction=fraction):
                raw = json.dumps(begin).replace('+00:00', fraction)
                self.session.parent.mkdir(parents=True, exist_ok=True)
                self.session.write_text(raw + '\n' + json.dumps(end('one', 3)) + '\n')
                self.assertEqual(self.collect(friction=False)['headline']['claude_calls'], 1)
                self.assertEqual(self.collect()['headline']['claude_calls'], 1)
                self.assertEqual(self.collect()['friction']['summary']['samples'], 1)

    def test_reordered_long_timestamp_with_whitespace_counts_usage(self):
        stamp = '2025-01-01T00:00:01.' + '0' * 24 + 'Z'
        begin = start('one', 0)
        del begin['timestamp']
        begin['message'].update(id='usage', usage=dict(input_tokens=10, output_tokens=5))
        raw = json.dumps(begin)[:-1] + ', "timestamp" :' + ' ' * 60 + json.dumps(stamp) + '}'
        self.session.parent.mkdir(parents=True, exist_ok=True)
        self.session.write_text(raw + '\n' + json.dumps(end('one', 3)) + '\n')
        self.assertEqual(AUDIT['envelope_timestamp'](raw.encode()), stamp)
        self.assertEqual(self.collect()['headline']['claude_calls'], 1)
        self.assertEqual(self.collect()['friction']['summary']['samples'], 1)

    def test_pairs_replays_conflicts_and_timing_basis(self):
        prompt = dict(source='user_permanent', decision='accept')
        rows = [
            start('same-id', 0), start('same-id', 2, session='other-session'),
            end('same-id', 180, session='other-session', permissionDecision=prompt,
                toolUseResult=dict(durationMs=40000)),
            end('same-id', 140), start('third', 1), end('third', 91),
            start('negative', 160), end('negative', 150, toolUseResult=dict(durationMs=2000)),
            start('old', -1), end('old', 999, toolUseResult=dict(durationMs=2000)),
            start('prompted', 1), end('prompted', 999, permissionDecision=prompt),
            start('invalid', 1), end('invalid', 999, permissionDecision=prompt,
                                     toolUseResult=dict(durationMs='not numeric')),
            start('ambiguous', 1), end('ambiguous', 999), start('ambiguous', 2),
            start('different-command', 1), end('different-command', 999),
            start('different-command', 1, 'cargo test --all'),
            start('ambiguous-result', 1), end('ambiguous-result', 999),
            end('ambiguous-result', 999, uuid='different-row'),
            start('unknown-session', 0, session=None), end('unknown-session', 999, session=None),
            start('cross-session', 0), end('cross-session', 999, session='other-session'),
            end('orphan', 999), start('unfinished', 1),
        ]
        conflicting = end('changed-result', 999)
        conflicting['message']['content'][0]['content'] = 'different private fixture output'
        rows += [start('changed-result', 1), end('changed-result', 999), conflicting]
        jsonl(self.session, rows + rows[:6])
        jsonl(self.project / 'replay.jsonl', rows[:6])
        data = self.collect()
        f = data['friction']
        self.assertEqual(f['window'], dict(kind='fixed', cutoff=SINCE.isoformat()))
        self.assertEqual(f['basis'], 'mixed')
        self.assertEqual(f['summary'], dict(samples=3, measured=1, estimated=2, capped=False, slow_calls=[
            dict(signature='cargo test', count=3, slow=1, heavy=True, seconds_total=270.0,
                 p50=90.0, p90=140.0, basis='mixed')]))
        self.assertEqual({flag['id']: flag['value'] for flag in f['flags']},
                         {'slow-calls': 1, 'heavy-calls': 90.0})
        self.assertTrue(all(set(flag) == {'id', 'subject', 'detail', 'value'} for flag in f['flags']))
        self.assertNotIn('_friction', data)
        self.assertEqual(data['warnings']['malformed rows'], 1)
        without_friction = {k: v for k, v in data.items() if k not in ('friction', 'warnings')}
        self.assertEqual({k: v for k, v in self.collect(friction=False).items() if k != 'warnings'}, without_friction)

    def test_uuidless_batch_builds_one_event_identity(self):
        batch = end('0', 3, toolUseResult=dict(timedOutAfterMs=3))
        starts = [start(str(i), 0) for i in range(20)]
        batch['message']['content'].extend(end(str(i), 3)['message']['content'][0]
                                           for i in range(1, len(starts)))
        jsonl(self.session, [*starts, batch])
        original = AUDIT['finalize_friction']

        def finalize(state, *args):
            events = [pair[1][-1] for pair in state['pairs'].values()]
            self.assertEqual(len(events), len(starts))
            self.assertTrue(all(event is events[0] for event in events))
            return original(state, *args)

        with patch.dict(AUDIT['collect'].__globals__, finalize_friction=finalize):
            self.assertEqual(self.collect()['friction']['signals']['timeouts'], 1)

    def test_multi_result_metadata_is_not_measured_and_background_is_excluded(self):
        result = end('first', 200, toolUseResult=dict(durationMs=1234))
        result['message']['content'] += end('second', 200)['message']['content']
        rows = [start('first', 0), start('second', 1), result,
                start('background', 1), end('background', 900, toolUseResult=dict(backgroundTaskId='fixture'))]
        jsonl(self.session, rows)
        with patch.dict(AUDIT['collect'].__globals__, FRICTION_PAIR_LIMIT=2):
            f = self.collect()['friction']
        self.assertEqual(f['basis'], 'row_gap')
        self.assertEqual((f['summary']['samples'], f['summary']['capped']), (2, True))

        f = self.collect()['friction']
        self.assertEqual((f['summary']['samples'], f['summary']['capped']), (2, False))
        self.assertEqual(f['summary']['slow_calls'][0]['p90'], 200)

    def test_invalid_durations_and_excluded_tools(self):
        rows = []
        for index, duration in enumerate((True, -1, float('inf'), float('nan'), None)):
            ident = f'invalid-duration-{index}'
            rows += [start(ident, 0), end(ident, 200, toolUseResult=dict(durationMs=duration),
                                        permissionDecision=dict(source='user', decision='accept'))]
        for name in ('Agent', 'Task', 'SendMessage', 'AskUserQuestion'):
            call = start(name, 0)
            call['message']['content'][0]['name'] = name
            rows += [call, end(name, 200)]
        background = start('background-input', 0)
        background['message']['content'][0]['input']['run_in_background'] = True
        rows += [background, end('background-input', 200)]
        jsonl(self.session, rows)
        self.assertEqual(self.collect()['friction']['summary']['samples'], 0)

    def test_extract_privacy_and_report_top_five(self):
        commands = [
            '/private-fixture-path/private-proprietary-bin private-command-argument',
            'cargo test private-command-argument', 'git status', 'npm run private-task-name',
            'go build', 'gradlew test', 'python3 /private-fixture-path/private-script.py',
        ]
        rows = [row('user', dict(type='text', text='private fixture prompt'), 0)]
        for number, command in enumerate(commands):
            ident = f'private-tool-{number}'
            rows.extend((start(ident, 1, command, cwd='/private-fixture-path'), end(ident, 200 + number)))
        jsonl(self.session, rows)
        data = self.audit('--since', '2025-01-01')
        extract = json.loads(Path(data['extract_path']).read_text())
        self.assertEqual(set(extract), {'v', 'scope', 'since', 'usage', 'report', 'friction'})
        self.assertEqual(extract['v'], 1)
        self.assertEqual(extract['friction']['v'], 1)
        self.assertEqual(extract['friction'], data['friction'])
        self.assertEqual(extract['usage']['agents'], data['agent_usage'])
        report = Path(data['report_path']).read_text()
        section = report.split('## Friction\n')[1]
        self.assertIn('p50 (s) | p90 (s) | Samples | Basis', section)
        self.assertEqual(sum(line.endswith('| row_gap') for line in section.splitlines()), 5)
        self.assertEqual(len(extract['friction']['summary']['slow_calls']), 7)
        for secret in ('private-fixture-path', 'private-proprietary-bin', 'private-command-argument',
                       'private-task-name', 'private-script.py', 'private fixture output',
                       'private fixture prompt', 'private-tool-', 'fixture-session'):
            self.assertNotIn(secret, json.dumps(extract['friction']) + section)

    def test_cli_windows_thresholds_and_off_global_and_scoped(self):
        jsonl(self.session, [start('fixture', 0, cwd=str(self.work)), end('fixture', 20)])
        for selector in ([], ['--cwd', str(self.work)], ['--project', 'example']):
            with self.subTest(selector=selector):
                rolling = self.audit('--days', '7', '--no-write', *selector)
                self.assertEqual(rolling['scope']['window'], '7d')
                self.assertEqual(rolling['friction']['window'], dict(kind='rolling', seconds=604800,
                                                                    policy='utc-now-floor-second'))
                self.assertIsNone(rolling['report_path'])
                self.assertIsNone(rolling['extract_path'])
                fixed = self.audit('--since', '2025-01-01', '--friction-slow-seconds', '5',
                                   '--friction-heavy-seconds', '8', *selector)
                self.assertEqual(fixed['scope']['window'], 'since:2025-01-01')
                self.assertEqual(fixed['friction']['window'], dict(kind='fixed', cutoff=SINCE.isoformat()))
                self.assertEqual(fixed['friction']['thresholds'], dict(slow_call_seconds=5, heavy_seconds=8))
                self.assertEqual(fixed['friction']['summary']['samples'], 1)
                off = self.audit('--since', '2025-01-01', '--no-friction', *selector)
                for key in ('scope', 'since', 'headline', 'format_canary', 'agent_usage'):
                    self.assertEqual(fixed[key], off[key])
                self.assertNotIn('friction', off)
                self.assertNotIn('friction', json.loads(Path(off['extract_path']).read_text()))
                self.assertNotIn('## Friction', Path(off['report_path']).read_text())
                for flag in ('--friction-slow-seconds', '--friction-heavy-seconds'):
                    invalid = self.run_script('token-audit', flag, '0', *selector, code=2)
                    self.assertIn('friction thresholds must be positive', invalid.stderr)

    def test_empty_input_and_copilot_notice_keep_stdout_compatible(self):
        (self.home / '.copilot/session-state').mkdir(parents=True)
        result = self.run_script('token-audit', '--days', '0', '--no-write')
        self.assertIn('Copilot sessions found but not measured', result.stderr)
        self.assertNotIn('Friction', result.stdout)
        self.assertEqual(result.stdout, self.run_script('token-audit', '--days', '0',
                                                        '--no-write', '--no-friction').stdout)
        f = self.audit('--days', '0', '--no-write')['friction']
        self.assertEqual((f['basis'], f['summary']['samples'], f['flags']), ('none', 0, []))
        empty = self.audit('--days', '0')
        self.assertNotIn('friction', json.loads(Path(empty['extract_path']).read_text()))
