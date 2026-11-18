"""Offline signal coverage with synthetic transcript rows."""
import json

from test_friction_claude import FrictionClaudeTests, start, end
from test_scripts import jsonl


class FrictionSignalTests(FrictionClaudeTests):
    def test_signals_are_deduplicated_and_private(self):
        timeout = end('timeout', 5, toolUseResult={'timedOutAfterMs': 5000})
        hint = end('hint', 6)
        hint['message']['content'][0].update(is_error=True, content='Exit code: 124\nprivate fixture')
        lock = end('lock', 7, toolUseResult={'interrupted': True})
        lock['message']['content'][0].update(is_error=True, content='could not acquire the lock private fixture')
        question = start('question', 0)
        question['message']['content'][0]['name'] = 'AskUserQuestion'
        rows = [start('timeout', 0), timeout, timeout, start('hint', 0), hint,
                start('lock', 0), lock, question, end('question', 10)]
        jsonl(self.session, rows)
        data = self.collect()['friction']
        self.assertEqual(data['signals'], dict(usage_limits=0, timeouts=1, timeout_hints=1, interrupts=1,
            lock_phrases=1, user_questions=1, user_question_wait_upper_bound_seconds=10))
        self.assertNotIn('private fixture', json.dumps(data))
        self.assertNotIn('friction', self.collect(friction=False))

    def test_usage_limit_system_rows(self):
        signal = dict(type='system', subtype='informational', timestamp='2025-01-01T00:00:01Z',
                      sessionId='fixture-session', uuid='system-row', content='Usage limit reached')
        jsonl(self.session, [signal, signal])
        self.assertEqual(self.collect()['friction']['signals']['usage_limits'], 1)

    def test_scoped_permission_evidence(self):
        first, second = str(self.work.resolve()), str((self.root / 'other-worktree').resolve())
        rows = []
        def call(ident, command, decision=None, root=first, result_root=None, error=False):
            begin = start(ident, 0, command, cwd=root)
            result = end(ident, 2, cwd=result_root or root, permissionDecision=decision, toolUseResult=dict(durationMs=1000))
            result['message']['content'][0]['is_error'] = error
            rows.extend([begin, result])
            return begin, result
        accept = dict(source='user', decision='accept')
        reject = dict(source='user', decision='reject')
        a, b = call('accepted', 'ls', accept)
        rows.extend([a, b])
        call('no-host', 'ls', dict(source='model', decision='accept'))
        call('missing', 'ls', None)
        call('denied', 'ls', reject, error=True)
        call('failed-accept', 'ls', accept, error=True)
        rows.extend([start('unverified', 0, 'ls', cwd=first),
                     end('unverified', 2, cwd=first, permissionDecision=accept)])
        call('foreign', 'ls', accept, result_root=second)
        call('other', 'ls', accept, root=second)
        call('a', 'ls -a', accept)
        call('l', 'ls -l', reject)
        for number, command in enumerate(['ls -al', 'ls -a /private', 'echo ls', 'ls; pwd']):
            call('lookalike' + str(number), command, accept)
        jsonl(self.session, rows)
        data = self.collect(cwd=[first, second])['friction']['permission_acceptance']
        import hashlib
        one = hashlib.sha256(first.encode()).hexdigest()
        two = hashlib.sha256(second.encode()).hexdigest()
        by_key = {(r['cwd_id'], r['literal']): r for r in data}
        self.assertEqual(by_key[(one, 'ls')], dict(cwd_id=one, literal='ls', accepted=1, denied=1, ambiguous=5))
        self.assertEqual(by_key[(two, 'ls')]['accepted'], 1)
        self.assertEqual(by_key[(one, 'ls -a')]['accepted'], 1)
        self.assertEqual(by_key[(one, 'ls -l')]['denied'], 1)
        self.assertEqual(len(data), 4)
        self.assertNotIn(first, json.dumps(data))
        self.assertEqual(self.collect()['friction']['permission_acceptance'], [])
        self.assertNotIn('friction', self.collect(cwd=[first], friction=False))

    def test_conflicting_decisions_are_ambiguous(self):
        root = str(self.work.resolve())
        yes = end('conflict', 2, cwd=root, permissionDecision=dict(source='user', decision='accept'), toolUseResult=dict(durationMs=1000))
        no = end('conflict', 2, cwd=root, permissionDecision=dict(source='user', decision='reject'))
        jsonl(self.session, [start('conflict', 0, 'ls', cwd=root), yes, no])
        rows = self.collect(cwd=[root])['friction']['permission_acceptance']
        self.assertEqual((rows[0]['accepted'], rows[0]['denied'], rows[0]['ambiguous']), (0, 0, 1))

    def test_permission_extract_and_disabled_cli(self):
        root = str(self.work.resolve())
        jsonl(self.session, [start('id', 0, 'ls -a', cwd=root),
              end('id', 1, cwd=root, toolUseResult=dict(durationMs=1),
                  permissionDecision=dict(source='user', decision='accept'))])
        on = self.audit('--since', '2025-01-01', '--cwd', root)
        friction = json.loads(__import__('pathlib').Path(on['extract_path']).read_text())['friction']
        self.assertEqual(friction['permission_acceptance'][0]['accepted'], 1)
        for private in (root, 'fixture-session', 'private fixture output', '"id"'):
            self.assertNotIn(private, json.dumps(friction))
        off = self.audit('--since', '2025-01-01', '--cwd', root, '--no-friction')
        self.assertNotIn('friction', json.loads(__import__('pathlib').Path(off['extract_path']).read_text()))

    def test_signal_lookalikes_and_wait_bounds(self):
        not_lock = end('not-lock', 4)
        not_lock['message']['content'][0].update(is_error=True, content='locksmith acquired a lock')
        invalid = end('invalid', 3, toolUseResult=dict(timedOutAfterMs=True, interrupted='true'))
        question = start('backwards', 5)
        question['message']['content'][0]['name'] = 'AskUserQuestion'
        jsonl(self.session, [start('not-lock', 0), not_lock, start('invalid', 0), invalid,
                             question, end('backwards', 1)])
        self.assertFalse(any(self.collect()['friction']['signals'].values()))
