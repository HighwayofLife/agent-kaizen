"""Offline signal coverage with synthetic transcript rows."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from test_friction_claude import AUDIT, OPTIONS, SINCE, FrictionClaudeTests, start, end
from test_friction_codex import call, result, row
from test_schedule_security import SecurityCase
from test_scripts import jsonl


class SignedTranscriptTests(SecurityCase):
    def test_extract_store_rejects_custom_mode_and_symlink_ancestor(self):
        from unittest.mock import patch
        data = dict(since='2025-01-01', agent_usage={})
        custom = self.root / 'custom'
        custom.mkdir(mode=0o755)
        custom.chmod(0o755)
        self.assertIsNone(AUDIT['write_extract'](data, self.root / 'report.md', custom, {}))
        self.assertEqual(custom.stat().st_mode & 0o777, 0o755)
        link = self.root / 'link'
        link.symlink_to(custom, target_is_directory=True)
        self.assertIsNone(AUDIT['write_extract'](data, self.root / 'report.md', link / 'extracts', {}))
        default = self.cfg / 'audits/extracts'
        default.mkdir(parents=True, mode=0o755)
        default.chmod(0o755)
        with patch.dict(__import__('os').environ, CLAUDE_CONFIG_DIR=str(self.cfg)):
            self.assertIsNotNone(AUDIT['write_extract'](data, self.root / 'report.md', default, {}))
        self.assertEqual(default.stat().st_mode & 0o777, 0o700)

    def test_extract_missing_unix_flags_does_not_abort(self):
        from unittest.mock import patch
        import os
        with patch.object(os, 'O_DIRECTORY', create=True):
            del os.O_DIRECTORY
            self.assertIsNone(AUDIT['write_extract'](dict(since='2025-01-01', agent_usage={}),
                                                     self.root / 'report.md', self.root / 'extracts', {}))

    def test_nonregular_transcripts_never_block_fallback(self):
        import os
        import subprocess
        import sys
        for path in (self.cfg / 'projects/fixture/pipe.jsonl', self.cx / 'sessions/2025/01/01/pipe.jsonl'):
            path.parent.mkdir(parents=True, exist_ok=True)
            os.mkfifo(path)
        for flags in ([], ['--no-friction']):
            result = subprocess.run([sys.executable, str(Path(AUDIT['__file__'])), '--json', *flags],
                                    cwd=self.work, env=self.env, capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            if not flags:
                self.assertEqual(json.loads(result.stdout)['warnings']['unsafe permission transcript'], 2)

    def test_report_writes_utf8_with_legacy_locale(self):
        import subprocess
        import sys
        wrapper = """import pathlib, runpy, sys
original = pathlib.Path.write_text
def checked(self, data, *args, **kwargs):
    if self.suffix == '.md' and kwargs.get('encoding') != 'utf-8':
        raise AssertionError('report encoding must be UTF-8')
    return original(self, data, *args, **kwargs)
pathlib.Path.write_text = checked
sys.argv = [sys.argv[1], '--json']
runpy.run_path(sys.argv[0], run_name='__main__')
"""
        result = subprocess.run([sys.executable, '-c', wrapper, str(Path(AUDIT['__file__']))],
                                cwd=self.work, env=self.env, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('≥', Path(json.loads(result.stdout)['report_path']).read_text(encoding='utf-8'))

    def test_report_compares_with_legacy_locale(self):
        import hashlib
        from unittest.mock import patch

        secret = b'fixture'
        scope = dict(v=1, window='7d')
        previous = self.root / 'token-audit-old.md'
        cohort = dict(signature='cargo test', basis='measured', count=3, p50=60)
        friction = dict(v=1, thresholds={}, window={}, basis='measured',
                        summary=dict(capped=False), comparisons=[cohort])
        name = previous.with_suffix('.extract.json').name
        raw = json.dumps(dict(v=1, scope=scope, report=previous.name, friction=friction)).encode()
        (self.root / name).write_bytes(raw)
        binding = dict(size=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        mac = AUDIT['regression_binding_mac'](secret, previous.name, binding)
        report = '\n'.join((
            'Á',
            '<!-- token-audit-headline {} -->',
            f'<!-- token-audit-scope {json.dumps(scope)} -->',
            f'<!-- token-audit-extract {json.dumps(dict(v=1, file=name))} -->',
            f'<!-- token-audit-friction {json.dumps(binding)} -->',
            f'<!-- token-audit-friction-mac {mac} -->',
            '<!-- token-audit-complete -->',
            '',
        ))
        original_open = Path.open

        def legacy_open(path, mode='r', buffering=-1, encoding=None, errors=None, newline=None):
            if 'b' not in mode and encoding in (None, 'locale'):
                encoding = 'cp1252'
            return original_open(path, mode, buffering, encoding, errors, newline)

        for encoding in ('utf-8', 'cp1252'):
            with self.subTest(encoding=encoding):
                previous.write_bytes(report.encode(encoding))
                current = dict(friction=dict(friction, comparisons=[dict(cohort, p50=90)], flags=[]))
                with patch.object(Path, 'open', legacy_open), patch.dict(
                        AUDIT['apply_regression'].__globals__, audit_machine_key=lambda: secret):
                    AUDIT['apply_regression'](current, self.root / 'token-audit-new.md', scope, self.root)
                self.assertEqual([item['ratio'] for item in current['friction'].get('regressions', [])], [1.5])

    def test_darwin_deny_acl_is_safe_but_allow_acl_is_not(self):
        import os
        import subprocess
        import sys
        if sys.platform != 'darwin':
            self.skipTest('Darwin ACL API')
        path = self.root / 'acl-test'
        path.touch()
        self.addCleanup(subprocess.run, ['chmod', '-N', str(path)], check=True)
        subprocess.run(['chmod', '+a', 'everyone deny delete', str(path)], check=True)
        with path.open('rb') as stream:
            self.assertFalse(AUDIT['has_allow_acl'](stream.fileno()))
        subprocess.run(['chmod', '+a', 'everyone allow write', str(path)], check=True)
        with path.open('rb') as stream:
            self.assertTrue(AUDIT['has_allow_acl'](stream.fileno()))

    def test_unrelated_unsafe_rollout_does_not_warn(self):
        project = self.project('selected')
        other = self.project('other')
        path = self.cx / 'sessions/2025/01/01/rollout.jsonl'
        jsonl(path, [row('session_meta', 0, cwd=str(other))])
        path.chmod(0o664)
        data = json.loads(self.run_script('token-audit', '--cwd', project, '--json').stdout)
        self.assertFalse(data['warnings'].get('unsafe permission transcript'))

    def test_unsafe_codex_rollout_cannot_authenticate_regression(self):
        project = self.project('codex-evidence')
        now = datetime.now(timezone.utc) - timedelta(minutes=1)
        rollout = self.cx / 'sessions/2025/01/01/rollout.jsonl'
        events = [dict(row('session_meta', 0, cwd=str(project)), timestamp=now.isoformat())]
        for i in range(3):
            events.extend([dict(call(str(i)), timestamp=now.isoformat()),
                           dict(result(str(i)), timestamp=(now + timedelta(seconds=5)).isoformat())])
        usage = dict(input_tokens=7, output_tokens=3, total_tokens=10)
        events.append(dict(row('event_msg', 6, type='token_count', info=dict(total_token_usage=usage)),
                           timestamp=(now + timedelta(seconds=6)).isoformat()))
        jsonl(rollout, events)
        rollout.chmod(0o664)
        data = json.loads(self.run_script('token-audit', '--cwd', project, '--json').stdout)
        self.assertEqual(data['codex_sessions'][0]['tokens'], 10)
        self.assertEqual(data['friction']['summary']['measured'], 3)
        self.assertEqual(data['warnings']['unsafe permission transcript'], 1)
        self.assertEqual(data['friction']['comparisons'], [])
        self.assertNotIn('<!-- token-audit-friction-mac ', Path(data['report_path']).read_text())
        rollout.chmod(0o644)
        data = json.loads(self.run_script('token-audit', '--cwd', project, '--json').stdout)
        self.assertEqual(data['friction']['comparisons'][0]['count'], 3)
        self.assertIn('<!-- token-audit-friction-mac ', Path(data['report_path']).read_text())

    def test_unsafe_transcripts_do_not_supply_signed_counters(self):
        project = self.project("signed-evidence")
        folder = self.cfg / "projects" / "fixture"
        safe = folder / "safe.jsonl"
        now = datetime.now(timezone.utc) - timedelta(minutes=1)

        def events(ident):
            begin = start(ident, 0, "ls", cwd=str(project))
            finish = end(ident, 1, cwd=str(project), toolUseResult=dict(durationMs=1),
                         permissionDecision=dict(source="user", decision="accept"))
            return [dict(begin, timestamp=now.isoformat()),
                    dict(finish, timestamp=(now + timedelta(seconds=1)).isoformat())]

        jsonl(safe, events("safe"))
        group_writable = folder / "group.jsonl"
        jsonl(group_writable, events("group"))
        group_writable.chmod(0o664)
        external = self.root / "external.jsonl"
        jsonl(external, events("link"))
        (folder / "link.jsonl").symlink_to(external)
        unsafe_folder = folder.with_name("unsafe-ancestor")
        jsonl(unsafe_folder / "permissions.jsonl", events("ancestor"))
        unsafe_folder.chmod(0o775)
        data = json.loads(self.run_script("token-audit", "--cwd", project, "--json").stdout)
        extract = json.loads(Path(data["extract_path"]).read_bytes())
        self.assertIn("allow_rule_mac", extract)
        self.assertEqual(extract["friction"]["permission_acceptance"][0]["accepted"], 1)
        self.assertEqual(data["warnings"]["unsafe permission transcript"], 3)
        self.assertEqual(data["friction"]["summary"]["measured"], 4)


class FrictionSignalTests(FrictionClaudeTests):
    def test_future_codex_cwd_records_do_not_scope_tool_pairs(self):
        root = self.work.resolve()
        rollout = self.root / '2025/01/01/rollout.jsonl'
        for kind in ('turn_context', 'session_meta'):
            with self.subTest(kind=kind):
                records = [row('event_msg', 0, cwd=str(root)),
                           row(kind, 20, cwd=str(root), turn_id='future'),
                           call('future', turn_id='future'), result('future', turn_id='future'),
                           row('turn_context', 2, cwd=str(root)),
                           call('current', seconds=3), result('current')]
                jsonl(rollout, records)
                data = AUDIT['collect']([], self.root, SINCE, {}, None, OPTIONS,
                                        cwd=[str(root)], now=SINCE + timedelta(seconds=10))
                self.assertEqual(data['friction']['summary']['measured'], 1)

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

    def test_timestampless_conflicting_denial_is_ambiguous(self):
        root = str(self.work.resolve())
        yes = end('conflict', 2, cwd=root, permissionDecision=dict(source='user', decision='accept'), toolUseResult=dict(durationMs=1000))
        no = end('conflict', 2, cwd=root, permissionDecision=dict(source='user', decision='reject'))
        del no['timestamp']
        no['nested'] = {'timestamp': '2020-01-01T00:00:00Z'}
        jsonl(self.session, [start('conflict', 0, 'ls', cwd=root), yes, no])
        evidence = self.collect(cwd=[root])['friction']['permission_acceptance'][0]
        self.assertEqual((evidence['accepted'], evidence['ambiguous']), (0, 1))

    def test_invalid_outer_timestamp_conflicting_denial_is_ambiguous(self):
        root = str(self.work.resolve())
        yes = end('conflict', 2, cwd=root, permissionDecision=dict(source='user', decision='accept'),
                  toolUseResult=dict(durationMs=1000))
        no = dict(nested={'timestamp': yes['timestamp']},
                  **end('conflict', 2, cwd=root, permissionDecision=dict(source='user', decision='reject')))
        for malformed in ('invalid', '0000-01-01T00:00:00Z', '2020-01-01T00:00:00.' + '0' * 24 + 'Z'):
            with self.subTest(timestamp=malformed):
                no['timestamp'] = malformed
                jsonl(self.session, [start('conflict', 0, 'ls', cwd=root), yes, no])
                evidence = self.collect(cwd=[root])['friction']['permission_acceptance'][0]
                self.assertEqual((evidence['accepted'], evidence['ambiguous']), (0, 1))

    def test_long_tool_timestamp_preserves_claude_call_accounting(self):
        begin = start('long', 2)
        begin['message'].update(id='usage', model='claude-test', usage=dict(input_tokens=10, output_tokens=5))
        for stamp in ('2025-01-01T00:00:02.' + '0' * 24 + 'Z',
                      '2025-01-01T01:00:02.000000+01:00:00.000001'):
            with self.subTest(timestamp=stamp):
                begin['timestamp'] = stamp
                jsonl(self.session, [begin, end('long', 3)])
                for friction in (True, False):
                    self.assertEqual(self.collect(friction=friction)['headline']['claude_calls'], 1)

    def test_invalid_tool_result_timestamp_warns_once(self):
        result = end('invalid', 2)
        for stamp in ('invalid', 'invalidZ', None):
            with self.subTest(timestamp=stamp):
                result.pop('timestamp', None)
                if stamp is not None:
                    result['timestamp'] = stamp
                jsonl(self.session, [start('invalid', 0), result])
                data = self.collect()
                self.assertEqual(data['warnings']['malformed rows'], 1)
                self.assertEqual(data['friction']['summary']['samples'], 0)

    def test_skipped_sample_preserves_transcript_duration(self):
        from unittest.mock import patch
        jsonl(self.session, [start('duration', 0), end('duration', 180, toolUseResult=dict(durationMs=120000))])
        samples = dict(events={}, load=[], procs=[], hours=set(), skipped_days={'2025-01-01'})
        with patch.dict(AUDIT['collect'].__globals__, read_samples=lambda *args: samples):
            summary = self.collect()['friction']['summary']
        self.assertEqual((summary['samples'], summary['measured']), (1, 1))
        self.assertEqual(summary['slow_calls'][0]['seconds_total'], 120)

    def test_prompt_only_extract_includes_wait(self):
        jsonl(self.session, [start('wait', 0), end('wait', 10, permissionDecision=dict(source='user', decision='accept'))])
        data = self.audit('--since', '2025-01-01')
        extract = json.loads(Path(data['extract_path']).read_text())
        self.assertEqual(extract['friction']['permission_waits']['count'], 1)

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

    def test_invalid_permission_timestamps_are_not_accepted(self):
        root = str(self.work.resolve())
        accept = dict(source='user', decision='accept')
        rows = [start('back', 5, 'ls', cwd=root),
                end('back', 1, cwd=root, permissionDecision=accept, toolUseResult=dict(durationMs=1))]
        for ident, stamp in [('missing', None), ('invalid', 'invalid')]:
            rows.append(start(ident, 0, 'ls', cwd=root))
            result = end(ident, 1, cwd=root, permissionDecision=accept, toolUseResult=dict(durationMs=1))
            if stamp is None:
                del result['timestamp']
            else:
                result['timestamp'] = stamp
            rows.append(result)
        jsonl(self.session, rows)
        data = self.collect(cwd=[root])
        self.assertEqual(data['friction']['permission_acceptance'][0]['accepted'], 0)
        self.assertGreaterEqual(data['warnings']['malformed rows'], 3)

    def test_batch_metadata_and_confirmed_signal_flags(self):
        batch = end('one', 3, uuid='batch', toolUseResult=dict(timedOutAfterMs=3, interrupted=True))
        batch['message']['content'].extend(end('two', 3)['message']['content'])
        batch['message']['content'][0].update(is_error=True, content='could not acquire the lock')
        usage = dict(type='system', subtype='informational', timestamp='2025-01-01T00:00:01Z',
                     sessionId='fixture-session', uuid='limit', content='Usage limit reached')
        jsonl(self.session, [start('one', 0), start('two', 0), batch, batch, usage])
        friction = self.collect()['friction']
        self.assertEqual((friction['signals']['timeouts'], friction['signals']['interrupts']), (1, 1))
        flags = {flag['id']: flag['value'] for flag in friction['flags']}
        self.assertEqual(flags, {'timeouts': 1, 'interrupts': 1, 'lock-contention': 1, 'usage-limits': 1})

    def test_bounded_replay_and_nonliteral_calls(self):
        fingerprint = AUDIT['replay_fingerprint']
        self.assertNotEqual(fingerprint('a' * 100000), fingerprint('a' * 99999 + 'b'))
        self.assertNotEqual(fingerprint([1, 23]), fingerprint([12, 3]))
        self.assertNotEqual(fingerprint('a' * 100000), fingerprint('a' * 100001))
        state = dict(cwd={str(self.work.resolve())}, permissions={}, capped=False)
        block = start('id', 0, 'echo ' + 'x' * 100000, cwd=str(self.work.resolve()))
        AUDIT['permission_observation'](state, ('s', 'id'), block, block['message']['content'][0], True, 0)
        self.assertEqual(state['permissions'], {})
