"""Offline CLI regression tests; the only Codex executable is a temporary stub."""
import ast
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
FAKE_CODEX = '''#!/usr/bin/env python3
import json, os, pathlib, sys
args = sys.argv[1:]
record = pathlib.Path(os.environ['RECORD'])
calls = record.read_text().splitlines() if record.exists() else []
number = len(calls)
with record.open('a') as stream:
    stream.write(json.dumps(dict(args=args, prompt=sys.stdin.read(), cwd=os.getcwd())) + '\\n')
print(json.dumps({'type':'thread.started', 'thread_id':'test-thread'}))
scenario = os.environ.get('SCENARIO', '')
if scenario == 'empty' or (scenario == 'retry-empty' and number == 0):
    sys.exit(0)
if scenario == 'overloaded' or (scenario == 'retry-overloaded' and number == 0):
    print('server_overloaded')
    sys.exit(1)
text = os.environ.get('FINAL', 'Completed task')
pathlib.Path(args[args.index('-o')+1]).write_text(text)
print(json.dumps({'type':'turn.completed', 'usage':{'input_tokens':10, 'output_tokens':2}}))
if scenario == 'nonzero':
    sys.exit(1)
'''


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def executable(path, text):
    write(path, text).chmod(0o755)
    return path


def jsonl(path, rows):
    return write(path, ''.join(json.dumps(row) + '\n' for row in rows))


class StubCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.work = self.root / 'repo with spaces'
        self.work.mkdir()
        self.home = self.root / 'home'
        self.home.mkdir()
        self.bin = self.root / 'bin'
        executable(self.bin / 'codex', FAKE_CODEX)
        self.record = self.root / 'calls.jsonl'
        self.env = dict(os.environ, HOME=str(self.home), PATH=str(self.bin) + os.pathsep + os.environ['PATH'], RECORD=str(self.record), PYTHONDONTWRITEBYTECODE='1')
        for name in ('CODEX_DISPATCH_MODEL', 'CODEX_REVIEW_MODEL', 'CODEX_LOOK_MODEL', 'FINAL', 'SCENARIO', 'CODEMAP_TIMEOUT'):
            self.env.pop(name, None)
        self.brief = write(self.work / 'task.md', 'Fix the example.\n')

    def run_script(self, name, *args, code=0):
        result = subprocess.run([str(SCRIPTS / name), *map(str, args)], cwd=self.work, env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result

    def dispatch(self, *args, **kwargs):
        return self.run_script('codex-dispatch', '-C', self.work, *args, self.brief, **kwargs)

    def calls(self):
        return [json.loads(line) for line in self.record.read_text().splitlines()]

    def report(self, result):
        lines = result.stdout.splitlines()
        self.assertLessEqual(len(lines), 25)
        self.assertTrue(lines[-1].startswith('STATUS:'))
        return lines


class ScriptTests(StubCase):
    def test_help_and_invalid_arguments(self):
        for name in ('codex-dispatch', 'codex-run', 'codex-review', 'token-audit', 'dispatch-status'):
            self.run_script(name, '--help')
        for rounds in ('-1', '3'):
            self.dispatch('-r', rounds, code=2)
        self.run_script('codex-dispatch', code=2)
        self.run_script('codex-review', 'visual', code=2)
        self.run_script('token-audit', '--days', '-1', code=2)
        missing = self.root / 'missing'
        self.dispatch('-C', missing, code=2)
        self.run_script('codex-review', 'diff', '-C', missing, code=2)
        self.assertFalse(missing.exists())
        self.assertFalse(self.record.exists())

    def test_done_and_default_model_and_output(self):
        result = self.dispatch()
        self.assertEqual(self.report(result)[-1], 'STATUS: DONE')
        self.assertNotIn('-m', self.calls()[0]['args'])
        reports = list((self.work / 'out/dispatch').glob('*/report.md'))
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0].read_text(), result.stdout)
        self.assertIn(self.brief.read_text(), self.calls()[0]['prompt'])

    def test_model_env_flag_and_disable_mcp(self):
        self.env['CODEX_DISPATCH_MODEL'] = 'preferred-model'
        self.dispatch('--disable-mcp', 'alpha', '--disable-mcp', 'beta', '-m', 'override-model')
        args = self.calls()[0]['args']
        self.assertEqual(args[args.index('-m') + 1], 'override-model')
        for name in ('alpha', 'beta'):
            self.assertIn('mcp_servers.' + name + '.enabled=false', args)
        self.dispatch()
        self.assertIn('preferred-model', self.calls()[1]['args'])

    def test_checks_resume_and_rerun_all(self):
        check = executable(self.work / 'check', '''#!/usr/bin/env python3
from pathlib import Path
p = Path('check-count')
n = int(p.read_text()) if p.exists() else 0
p.write_text(str(n+1))
print('ERROR: fix example' if n == 0 else 'pass')
raise SystemExit(1 if n == 0 else 0)
''')
        result = self.dispatch('-k', './check', '-k', 'echo another >> all-checks')
        self.assertEqual(self.report(result)[-1], 'STATUS: DONE')
        self.assertEqual((self.work / 'check-count').read_text(), '2')
        self.assertEqual(len((self.work / 'all-checks').read_text().splitlines()), 2)
        calls = self.calls()
        self.assertEqual(calls[1]['args'][:3], ['exec', 'resume', 'test-thread'])
        self.assertIn('ERROR: fix example', calls[1]['prompt'])
        self.assertNotIn('-m', calls[1]['args'])
        self.assertEqual(calls[0]['cwd'], str(self.work))
        self.assertTrue(list((self.work / 'out/dispatch').glob('*/check-1-round-0.log')))

    def test_exhausted_checks_and_trimmed_resume(self):
        executable(self.work / 'check', '#!/usr/bin/env python3\nfor i in range(1000): print("ERROR: " + str(i) + "x"*3000)\nraise SystemExit(1)\n')
        result = self.dispatch('-k', './check', code=1)
        self.assertEqual(self.report(result)[-1], 'STATUS: CHECKS FAILING')
        self.assertEqual(len(self.calls()), 3)
        followup = self.calls()[1]['prompt']
        self.assertLess(len(followup.splitlines()), 65)
        self.assertLess(len(followup), 125000)
        self.assertIn('999', followup)

    def test_zero_rounds_and_initial_resume(self):
        result = self.dispatch('-r', '0', '--resume', 'existing-thread', '-k', 'exit 1', code=1)
        self.assertEqual(len(self.calls()), 1)
        self.assertEqual(self.calls()[0]['args'][1:3], ['resume', 'existing-thread'])
        self.report(result)

    def test_report_limit_many_checks_and_summary(self):
        self.env['FINAL'] = '\n'.join('Summary ' + str(i) for i in range(100))
        checks = [arg for i in range(40) for arg in ('-k', 'echo check-' + str(i))]
        lines = self.report(self.dispatch(*checks))
        self.assertIn('check-39', '\n'.join(lines))

    def test_codemap_present_absent_failure_and_timeout(self):
        self.dispatch('-p', 'none')
        self.assertNotIn('Code locations', self.calls()[-1]['prompt'])
        tool = executable(self.work / 'tools/codemap', '#!/usr/bin/env python3\nimport sys\nassert sys.argv[1] == "brief"\nprint("# Code locations\\nexample.py:4")\n')
        for preamble in ('engineer', 'planner', 'none'):
            self.dispatch('-p', preamble)
            prompt = self.calls()[-1]['prompt']
            self.assertLess(prompt.index('# Code locations'), prompt.index('Fix the example.'))
        executable(tool, '#!/usr/bin/env python3\nraise SystemExit(1)\n')
        self.dispatch()
        self.assertNotIn('# Code locations', self.calls()[-1]['prompt'])
        executable(tool, '#!/usr/bin/env python3\nimport time\ntime.sleep(2)\n')
        self.env['CODEMAP_TIMEOUT'] = '0.01'
        self.dispatch()
        self.assertNotIn('# Code locations', self.calls()[-1]['prompt'])

    def test_infrastructure_retries_and_failures(self):
        for scenario in ('retry-empty', 'retry-overloaded'):
            self.record.unlink(missing_ok=True)
            self.env['SCENARIO'] = scenario
            self.report(self.dispatch())
            self.assertEqual(len(self.calls()), 2)
        for scenario in ('empty', 'overloaded', 'nonzero'):
            self.record.unlink(missing_ok=True)
            self.env['SCENARIO'] = scenario
            self.assertEqual(self.report(self.dispatch(code=2))[-1], 'STATUS: CODEX FAILED')

    def test_review_modes_models_and_cap(self):
        image = write(self.work / 'example.png', 'stub image')
        cases = [('diff', ['--uncommitted'], 'VERDICT: NO ISSUES', 'CODEX_REVIEW_MODEL'),
                 ('plan', [self.brief], 'VERDICT: APPROVE', 'CODEX_REVIEW_MODEL'),
                 ('look', ['--question', 'What is visible?', image], 'ANSWER: example', 'CODEX_LOOK_MODEL'),
                 ('visual', ['--criteria', 'Readable', image, '--ref', image], 'VERDICT: ACCEPT', 'CODEX_LOOK_MODEL')]
        for mode, args, ending, env in cases:
            self.env['FINAL'] = '\n'.join(['Finding'] * 50 + [ending])
            result = self.run_script('codex-review', mode, *args)
            self.report(result)
            self.assertIn(ending, result.stdout)
            self.assertNotIn('-m', self.calls()[-1]['args'])
            self.env[env] = 'review-model'
            self.run_script('codex-review', mode, '--disable-mcp', 'alpha', *args)
            self.assertIn('review-model', self.calls()[-1]['args'])
            self.assertIn('mcp_servers.alpha.enabled=false', self.calls()[-1]['args'])
            self.env.pop(env)

    def test_review_retry_and_failure(self):
        self.env.update(FINAL='VERDICT: NO ISSUES', SCENARIO='retry-empty')
        self.run_script('codex-review', 'diff', '--uncommitted')
        self.assertEqual(len(self.calls()), 2)
        self.env['FINAL'] = 'No verdict'
        self.run_script('codex-review', 'diff', '--uncommitted', code=2)

    def test_status_latest_report(self):
        self.dispatch()
        result = self.run_script('dispatch-status', self.work)
        self.assertIn('STATUS: DONE', result.stdout)

    def test_python39_syntax(self):
        for path in SCRIPTS.iterdir():
            if path.is_file() and (path.suffix == '.py' or path.read_bytes().startswith(b'#!/usr/bin/env python3')):
                ast.parse(path.read_text(), filename=path.name, feature_version=(3, 9))


class AuditTests(StubCase):
    # Keep fixtures small and deterministic; no real transcript data is read.
    def test_parser_warning_without_usage(self):
        now = datetime.now(timezone.utc).isoformat()
        jsonl(self.home / '.claude/projects/example/session.jsonl', [
            dict(type='assistant', timestamp=now, message=dict(content=[]))])
        result = self.run_script('token-audit', '--json')
        data = json.loads(result.stdout)
        warning = ("WARNING: transcript format may have changed; token-audit's parser needs updating "
                   "(1 files scanned, 0 usage rows)")
        self.assertTrue(data['parser_warning'])
        self.assertEqual(result.stderr.strip(), warning)
        self.assertEqual(Path(data['report_path']).read_text().splitlines()[0], warning)

    def test_codex_parser_warning_without_token_counts(self):
        now = datetime.now(timezone.utc).isoformat()
        jsonl(self.home / '.codex/sessions/2026/01/01/rollout.jsonl', [
            dict(timestamp=now, payload=dict(model='code-model'))])
        result = self.run_script('token-audit', '--json')
        data = json.loads(result.stdout)
        self.assertTrue(data['parser_warning'])
        self.assertIn('WARNING: Codex transcript format may have changed', result.stderr)
        self.assertIn('1 files scanned, 0 token_count rows', result.stderr)
        self.assertEqual(Path(data['report_path']).read_text().splitlines()[0], result.stderr.strip())

    def test_regression_flags_context_threshold(self):
        now = datetime.now(timezone.utc).isoformat()
        for context in (121, 119, 120):
            with self.subTest(context=context):
                directory = self.root / f'reports-{context}'
                old = dict(claude_calls=1, claude_context=100, claude_output=0,
                           codex_sessions=0, codex_tokens=0, image_reads=0)
                write(directory / 'token-audit-previous.md',
                      '<!-- token-audit-headline ' + json.dumps(old) + ' -->\n')
                jsonl(self.home / '.claude/projects/example/session.jsonl', [
                    dict(type='assistant', timestamp=now, message=dict(
                        id='message', usage=dict(input_tokens=context)))])
                data = json.loads(self.run_script('token-audit', '--out', directory, '--json').stdout)
                self.assertFalse(data['parser_warning'])
                report = Path(data['report_path']).read_text()
                self.assertIn('## 9. Flagged', report)
                if context > 120:
                    self.assertEqual(data['flagged'], [dict(
                        metric='claude_context', old=100, new=121, percent_change=21.0)])
                    self.assertIn('claude_context: 100 → 121 (+21.0%).', report)
                else:
                    self.assertEqual(data['flagged'], [])

    def test_no_previous_audit(self):
        data = json.loads(self.run_script('token-audit', '--json').stdout)
        self.assertFalse(data['parser_warning'])
        self.assertEqual(data['flagged'], [])
        self.assertIn('no previous audit to compare', Path(data['report_path']).read_text())

    def test_synthetic_projects_duplicates_and_codex(self):
        now = datetime.now(timezone.utc).isoformat()
        project = self.home / '.claude/projects/example'
        usage = dict(input_tokens=100, cache_read_input_tokens=20, cache_creation_input_tokens=5, output_tokens=10)
        row = dict(type='assistant', timestamp=now, message=dict(id='message-one', model='chat-model', content=[], usage=usage))
        jsonl(project / 'session.jsonl', [row, row, dict(row, timestamp='2000-01-01T00:00:00Z')])
        other = dict(row, message=dict(row['message'], id='message-two'))
        jsonl(self.home / '.claude/projects/other/session.jsonl', [row, other])
        jsonl(self.home / '.codex/sessions/2000/01/01/rollout.jsonl', [
            dict(timestamp='2000-01-01T00:00:00Z', payload={'model': 'code-model'}),
            dict(timestamp=now, payload=dict(type='token_count', info=dict(total_token_usage=dict(input_tokens=90, cached_input_tokens=20, output_tokens=10, total_tokens=100)))),
            dict(timestamp=now, payload=dict(type='token_count', info=dict(total_token_usage=dict(input_tokens=100, cached_input_tokens=25, output_tokens=20, total_tokens=120))))])
        data = json.loads(self.run_script('token-audit', '--days', '1', '--json').stdout)
        self.assertEqual(data['headline']['claude_calls'], 2)
        self.assertEqual(data['headline']['claude_context'], 250)
        self.assertFalse(data['parser_warning'])
        self.assertEqual(data['codex']['code-model']['tokens'], 120)
        self.assertEqual(data['codex']['code-model']['sessions'], 1)
        report = Path(data['report_path'])
        self.assertEqual(report.parent, self.home / '.claude/audits')
        self.assertLessEqual(len(report.read_text().split("\n## Cost (API-equivalent)")[0].splitlines()), 80)
        filtered = json.loads(self.run_script('token-audit', '--project', 'EXAMPLE', '--out', self.root / 'reports', '--json').stdout)
        self.assertEqual(filtered['headline']['claude_calls'], 1)
        self.assertEqual(Path(filtered['report_path']).parent, self.root / 'reports')
        repeated = json.loads(self.run_script('token-audit', '--project-dir', project, '--project-dir', project, '--json').stdout)
        self.assertEqual(repeated['headline']['claude_calls'], 1)

    def test_split_message_keeps_every_tool_call(self):
        now = datetime.now(timezone.utc).isoformat()
        usage = dict(input_tokens=100, output_tokens=10)
        def part(tool_id):
            return dict(type='assistant', timestamp=now, message=dict(
                id='split', model='chat-model', usage=usage,
                content=[dict(type='tool_use', id=tool_id, name='Read', input={})]))
        def result(tool_id):
            return dict(type='user', timestamp=now, message=dict(
                role='user', content=[dict(type='tool_result', tool_use_id=tool_id, content='ok')]))
        rows = [part('t1'), part('t2'), result('t1'), result('t2')]
        jsonl(self.home / '.claude/projects/example/session.jsonl', rows)
        jsonl(self.home / '.claude/projects/example/resumed.jsonl', rows)  # copied rows count once
        data = json.loads(self.run_script('token-audit', '--days', '1', '--json').stdout)
        self.assertEqual(data['headline']['claude_calls'], 1)
        self.assertEqual(data['tool_counts']['Read'], 2)

    def test_empty_malformed_and_report_path(self):
        write(self.home / '.claude/projects/example/session.jsonl', '{"timestamp":"2099-01-01T00:00:00Z", "usage": broken}\n')
        data = json.loads(self.run_script('token-audit', '--json').stdout)
        self.assertEqual(data['headline']['claude_calls'], 0)
        self.assertEqual(data['warnings']['malformed rows'], 1)
        result = self.run_script('token-audit', '--out', self.root / 'reports')
        self.assertTrue(Path(result.stdout.splitlines()[0]).is_file())

    def test_tools_agents_offsets_and_prior_audit(self):
        project = self.home / '.claude/projects/example'
        ts = '2026-01-02T02:00:00+02:00'
        usage = dict(input_tokens=10, output_tokens=2)
        def row(kind, content, ident=None):
            message = dict(content=content)
            if kind == 'assistant':
                message.update(id=ident, model='chat-model', usage=usage)
            return dict(type=kind, timestamp=ts, message=message)
        tool = dict(type='tool_use', id='read-one', name='Read', input={})
        result = dict(type='tool_result', tool_use_id='read-one', content=[dict(type='image')])
        jsonl(project / 'session.jsonl', [row('user', 'Hello'), row('assistant', [tool], 'first'),
                                        row('user', [result]), row('assistant', [], 'second')])
        agent = project / 'session/subagents/worker.jsonl'
        write(agent.with_suffix('.meta.json'), json.dumps(dict(agentType='worker')))
        jsonl(agent, [row('assistant', [dict(type='tool_use', id='bash-one', name='Bash',
                                          input=dict(command='cd repo && X=1 python3 check.py'))], 'third')])
        args = ('--since', '2026-01-02', '--json')
        data = json.loads(self.run_script('token-audit', *args).stdout)
        self.assertEqual(data['headline']['claude_calls'], 3)
        self.assertEqual(data['images'], 1)
        self.assertEqual(data['triggers']['human']['calls'], 1)
        self.assertEqual(data['triggers']['tool result']['calls'], 1)
        self.assertEqual(data['bash']['worker'], {'python3 check.py': 1})
        again = json.loads(self.run_script('token-audit', *args).stdout)
        self.assertIn('Compared with', Path(again['report_path']).read_text())
        later = json.loads(self.run_script('token-audit', '--since', '2026-01-03', '--json').stdout)
        self.assertEqual(later['headline']['claude_calls'], 0)


    def audit_rows(self, session, commands, prompts=1, metadata=None, project='example'):
        now = datetime.now(timezone.utc).isoformat()
        rows = []
        if metadata:
            rows.append(dict(type='api-request-shape', timestamp=now, shape=dict(tools=metadata)))
        for turn in range(prompts):
            rows.append(dict(type='user', timestamp=now, uuid=f'{session}-p{turn}',
                             message=dict(content='private prompt')))
            for index, (name, command, error) in enumerate(commands if turn == 0 else []):
                ident = f'{session}-{turn}-{index}'
                rows.append(dict(type='assistant', timestamp=now, message=dict(
                    id=ident, model='fixture-v1', usage=dict(input_tokens=100), content=[dict(
                        type='tool_use', id=ident, name=name, input=dict(command=command))])))
                rows.append(dict(type='user', timestamp=now, message=dict(content=[dict(
                    type='tool_result', tool_use_id=ident, is_error=error,
                    content='missing executable 123 /tmp/private-45/file' if error else 'ok')])))
        for row in rows:
            row['sessionId'] = session
        return jsonl(self.home / f'.claude/projects/{project}/{session}.jsonl', rows)

    def fixture_pricing(self):
        return write(self.root / 'prices.json', json.dumps(dict(
            source=dict(anthropic='fixture', openai='fixture', checked='2026-10-29'),
            unit='USD per million tokens', models={
                'fixture': dict(input=2, cache_write_5m=3, cache_write_1h=4, cache_read=1, output=5),
                'code': dict(input=2, cached_input=1, output=5)},
            aliases={'fix': 'code', 'fixture': 'fixture'})))

    def test_cost_cache_split_unknown_and_missing(self):
        now = datetime.now(timezone.utc).isoformat()
        rows = []
        usages = [dict(input_tokens=100, cache_creation_input_tokens=100, cache_read_input_tokens=200,
                       output_tokens=10, cache_creation=dict(ephemeral_1h_input_tokens=40,
                                                           ephemeral_5m_input_tokens=60)),
                  dict(cache_creation_input_tokens=20),
                  dict(cache_creation_input_tokens=30, cache_creation=dict(ephemeral_1h_input_tokens=30))]
        for i, usage in enumerate(usages):
            rows.append(dict(type='assistant', timestamp=now, message=dict(id=str(i), model='fixture-v1', usage=usage)))
        rows.append(dict(type='assistant', timestamp=now, message=dict(id='unknown', model='mystery', usage=dict(input_tokens=17))))
        jsonl(self.home / '.claude/projects/example/session.jsonl', rows)
        jsonl(self.home / '.codex/sessions/2026/01/01/code.jsonl', [
            dict(timestamp=now, payload=dict(model='code', type='token_count', info=dict(
                total_token_usage=dict(input_tokens=100, cached_input_tokens=20, output_tokens=10,
                                      reasoning_output_tokens=5, total_tokens=115))))])
        data = json.loads(self.run_script('token-audit', '--pricing', self.fixture_pricing(), '--json').stdout)
        self.assertAlmostEqual(data['cost']['total'], .001225)
        self.assertAlmostEqual(data['cost']['components']['cache_write'], .00052)
        self.assertAlmostEqual(data['cost']['by_agent']['codex'], .000255)
        self.assertEqual(data['cost']['unpriced']['mystery']['uncached_input'], 17)
        self.assertIn('fixture-v1', data['cost']['by_model'])  # longest alias wins
        self.assertIsNone(data['cost']['pricing_error'])
        missing = json.loads(self.run_script('token-audit', '--pricing', self.root / 'absent.json', '--json').stdout)
        self.assertEqual(missing['cost']['total'], 0)
        self.assertIn('Pricing file unavailable', Path(missing['report_path']).read_text())
        self.assertEqual(missing['cost']['unpriced']['fixture-v1']['cache_read'], 200)

    def test_stuck_turn_boundaries_and_threshold(self):
        failures = [('Bash', 'pytest tests', True)]
        self.audit_rows('three', failures * 3)
        self.audit_rows('two', failures * 2)
        path = self.audit_rows('separate', failures * 3)
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        for index in (5, 3):
            rows.insert(index, dict(type='user', timestamp=rows[0]['timestamp'],
                                   message=dict(content='next prompt')))
        jsonl(path, rows)
        data = json.loads(self.run_script('token-audit', '--pricing', self.fixture_pricing(), '--json').stdout)
        stuck = data['stuck_turns']
        self.assertEqual((stuck['flagged_turns'], stuck['turns'], stuck['tool_calls']), (1, 5, 3))
        self.assertAlmostEqual(stuck['cost'], .0006)
        signature = stuck['signatures'][0]['signature']
        self.assertIn('missing executable # <tmp>', signature)
        self.assertNotIn('private', signature)
        data = json.loads(self.run_script('token-audit', '--stuck-repeats', '2', '--json').stdout)
        self.assertEqual(data['stuck_turns']['flagged_turns'], 2)

    def test_repeated_failures_worked_instead(self):
        for session in ('one', 'two', 'three'):
            self.audit_rows(session, [('Bash', 'pytest tests', True), ('Bash', 'python -m pytest', False)])
        data = json.loads(self.run_script('token-audit', '--json').stdout)
        self.assertEqual(len(data['repeat_failures']), 1)
        fact = data['repeat_failures'][0]
        self.assertEqual((fact['sessions'], fact['occurrences']), (3, 3))
        self.assertEqual(fact['worked_instead'], 'python -m pytest')
        data = json.loads(self.run_script('token-audit', '--fact-sessions', '4', '--json').stdout)
        self.assertEqual(data['repeat_failures'], [])

    def test_unused_configured_servers_and_required_tools(self):
        write(self.home / '.claude.json', json.dumps(dict(mcpServers={'idle': {}, 'busy': {}})))
        for session in ('one', 'two'):
            self.audit_rows(session, [('mcp__busy__query', '', False)], prompts=5)
        self.audit_rows('elsewhere', [('Read', '', False), ('Bash', 'true', False),
                                    ('OptionalTool', '', False)], project='other')
        data = json.loads(self.run_script('token-audit', '--project', 'example', '--json').stdout)
        candidates = {r['candidate']: r for r in data['unused_tools']}
        self.assertEqual(set(candidates), {'idle', 'OptionalTool'})
        self.assertEqual((candidates['idle']['sessions'], candidates['idle']['prompts']), (2, 10))
        self.assertEqual(candidates['idle']['loading'], 'unknown')
        self.assertIn('invalidates the prompt cache', Path(data['report_path']).read_text())

    def test_recorded_tool_universe_and_loading(self):
        required = ['Read', 'Edit', 'Write', 'Bash', 'Grep', 'Glob', 'Agent', 'Task', 'ToolSearch', 'Skill']
        for i in range(5):
            self.audit_rows(str(i), [('mcp__busy__query', '', False)], metadata=[
                *[dict(name=name) for name in required], dict(name='FullTool'),
                dict(name='mcp__idle__query', defer_loading=True)])
        data = json.loads(self.run_script('token-audit', '--json').stdout)
        candidates = {r['candidate']: r for r in data['unused_tools']}
        self.assertEqual(set(candidates), {'FullTool'})
        self.assertEqual(candidates['FullTool']['loading'], 'loaded in full')
        self.assertEqual(data['deferred_tools_unused'], 1)
        self.assertIn('1 deferred tools unused (names only, ~negligible per turn)', Path(data['report_path']).read_text())

    def test_bash_exit_status_and_deferred_attachment(self):
        path = self.audit_rows('exit', [('Bash', 'npx tsc', True)] * 3)
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        for row in rows:
            for block in row.get('message', {}).get('content', []) if isinstance(row.get('message', {}).get('content'), list) else []:
                if block['type'] == 'tool_result':
                    block['content'] = 'Exit code: 2\nprivate details'
        rows.insert(0, dict(type='attachment', timestamp='2000-01-01T00:00:00Z', attachment=dict(
            type='deferred_tools_delta', addedNames=['mcp__old__query'])))
        jsonl(path, rows)
        data = json.loads(self.run_script('token-audit', '--prune-sessions', '1', '--json').stdout)
        self.assertEqual(data['stuck_turns']['flagged_turns'], 1)
        self.assertEqual(data['unused_tools'], [])
        self.assertEqual(data['deferred_tools_unused'], 1)
        self.assertIn('private details', data['stuck_turns']['signatures'][0]['signature'])
        self.assertIn('[exit 2]', data['stuck_turns']['signatures'][0]['signature'])


    def test_subagent_stuck_turn_resumed_in_window(self):
        path = self.audit_rows('parent', [('Bash', 'pytest tests', True)] * 3)
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows[0]['timestamp'] = '2000-01-01T00:00:00Z'
        agent = path.parent / 'parent/subagents/worker.jsonl'
        jsonl(agent, rows)
        write(agent.with_suffix('.meta.json'), json.dumps(dict(agentType='worker')))
        path.unlink()
        data = json.loads(self.run_script('token-audit', '--json').stdout)
        self.assertEqual(data['stuck_turns']['flagged_turns'], 1)
        self.assertEqual(data['stuck_turns']['signatures'][0]['agent'], 'worker')
        self.assertEqual(data['stuck_turns']['turns'], 1)

    def test_codex_reasoning_subset_not_double_counted_and_exact_price(self):
        now = datetime.now(timezone.utc).isoformat()
        pricing = self.fixture_pricing()
        value = json.loads(pricing.read_text())
        value['aliases']['code'] = 'fixture'
        pricing.write_text(json.dumps(value))
        jsonl(self.home / '.codex/sessions/2026/01/01/code.jsonl', [
            dict(timestamp=now, payload=dict(model='code', type='token_count', info=dict(
                total_token_usage=dict(input_tokens=100, cached_input_tokens=20, output_tokens=10,
                                      reasoning_output_tokens=5, total_tokens=110))))])
        data = json.loads(self.run_script('token-audit', '--pricing', pricing, '--json').stdout)
        self.assertAlmostEqual(data['cost']['total'], .00023)
        self.assertAlmostEqual(data['cost']['components']['output'], .00005)


    def test_error_matching_uses_full_line_but_report_limits_output(self):
        path = self.audit_rows('long', [('Bash', 'pytest tests', True)] * 3)
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        for index, row in enumerate(rows):
            content = row.get('message', {}).get('content')
            if isinstance(content, list) and content[0]['type'] == 'tool_result':
                content[0]['content'] = 'word ' * 30 + chr(65 + index)
        jsonl(path, rows)
        data = json.loads(self.run_script('token-audit', '--json').stdout)
        self.assertEqual(data['stuck_turns']['flagged_turns'], 0)
        data = json.loads(self.run_script('token-audit', '--stuck-repeats', '1', '--json').stdout)
        for row in data['stuck_turns']['signatures']:
            self.assertEqual(len(row['signature'].split(': ', 1)[1]), 120)
        self.assertEqual(data['stuck_turns']['signatures'][0]['turns'], 1)


    def replace_audit_errors(self, path, texts):
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        errors = iter(texts)
        for row in rows:
            content = row.get('message', {}).get('content')
            if isinstance(content, list) and content[0]['type'] == 'tool_result':
                content[0]['content'] = next(errors)
        jsonl(path, rows)

    def test_exit_headers_preserve_error_and_code(self):
        path = self.audit_rows('errors', [('Bash', 'grep -n pattern missing', True)] * 4)
        self.replace_audit_errors(path, ['Exit code 2\n\ngrep: missing file',
                                        'Exit code: 2\ngrep: permission denied',
                                        'Exit code 3\ngrep: missing file',
                                        'Exit code 2\ngrep: missing file'])
        data = json.loads(self.run_script('token-audit', '--fact-sessions', '1', '--json').stdout)
        self.assertEqual(data['stuck_turns']['flagged_turns'], 0)
        signatures = {row['signature'] for row in data['repeat_failures']}
        self.assertEqual(len(signatures), 3)
        self.assertIn('Bash grep -n [exit 2]: grep: missing file', signatures)
        self.assertIn('Bash grep -n [exit 3]: grep: missing file', signatures)
        self.assertFalse(any('Exit code #' in sig for sig in signatures))

    def test_benign_shell_exits_are_not_failures(self):
        commands = [(name, code) for name, code in (
            ('grep -n needle', 1), ('rg needle', 1), ('test -e file', 1), ('[ -e file ]', 1),
            ('diff first second', 1), ('cmp first second', 1), ('sed -n 1p', 141),
            ('wc -l', -13), ('head -10', 141)) for _ in range(3)]
        path = self.audit_rows('benign', [('Bash', command, True) for command, _ in commands])
        self.replace_audit_errors(path, [f'Exit code {code}\nexpected status' for _, code in commands])
        data = json.loads(self.run_script('token-audit', '--fact-sessions', '1', '--json').stdout)
        self.assertEqual(data['repeat_failures'], [])
        self.assertEqual(data['stuck_turns']['flagged_turns'], 0)
        # Other sed/head failures remain actionable.
        path = self.audit_rows('real', [('Bash', 'sed -n 1p', True)] * 3)
        self.replace_audit_errors(path, ['Exit code 2\nsed: invalid expression'] * 3)
        data = json.loads(self.run_script('token-audit', '--json').stdout)
        self.assertEqual(data['stuck_turns']['flagged_turns'], 1)

    def test_worked_instead_requires_nearby_plausible_fix(self):
        positive = [('pytest tests', 'python -m pytest'), ('tsc --noEmit', 'npx tsc'),
                    ('pytest tests', 'uv run pytest'), ('tsc --noEmit', './node_modules/.bin/tsc'),
                    ('pytest tests', 'poetry run pytest'), ('pytest tests', 'MODE=local pytest tests'),
                    ('MODE=old pytest tests', 'MODE=new pytest tests'),
                    ('cd old && pytest tests', 'cd new && pytest tests')]
        negative = [('grep -c pattern', 'grep -E pattern'), ('git add file', 'git commit -m fix'),
                    ('for f in files', 'for id in ids'), ('cat >> file', 'cat file'),
                    ('while true', 'while false'), ('if test -e a', 'if test -e b')]
        for index, (failure, success) in enumerate(positive + negative):
            self.audit_rows(str(index), [('Bash', failure, True), ('Bash', success, False)], project=f'case{index}')
        # A matching variant four tool calls later, or in another turn, is not evidence.
        self.audit_rows('late', [('Bash', 'pytest tests', True)] + [('Read', '', False)] * 3 +
                        [('Bash', 'python -m pytest', False)], project='late')
        path = self.audit_rows('turn', [('Bash', 'pytest tests', True), ('Bash', 'python -m pytest', False)], project='turn')
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows.insert(3, dict(type='user', timestamp=rows[0]['timestamp'], message=dict(content='new turn')))
        jsonl(path, rows)
        data = json.loads(self.run_script('token-audit', '--fact-sessions', '1', '--json').stdout)
        facts = {row['project']: row for row in data['repeat_failures']}
        for index in range(len(positive)):
            self.assertTrue(facts[f'case{index}']['worked_instead'], index)
        for index in range(len(positive), len(positive) + len(negative)):
            self.assertEqual(facts[f'case{index}']['worked_instead'], '', index)
        self.assertEqual(facts['late']['worked_instead'], '')
        self.assertEqual(facts['turn']['worked_instead'], '')

    def test_mcp_alias_collapsing_and_deferred_exclusion(self):
        write(self.home / '.claude.json', json.dumps(dict(mcpServers={'claude.ai Krisp': {}, 'Full Server': {}})))
        for session in ('one', 'two'):
            self.audit_rows(session, [('mcp__claude_ai_Krisp__search', '', False)], prompts=5, metadata=[
                dict(name='mcp__claude_ai_Krisp__search'), dict(name='mcp__Full_Server__first'),
                dict(name='mcp__Full_Server__second'), dict(name='mcp__Deferred__first', defer_loading=True),
                dict(name='mcp__Deferred__second', defer_loading=True)])
        data = json.loads(self.run_script('token-audit', '--json').stdout)
        self.assertEqual(len(data['unused_tools']), 1)
        row = data['unused_tools'][0]
        self.assertEqual((row['candidate'], row['kind'], row['tools']), ('full_server', 'MCP server', 2))
        self.assertEqual(data['deferred_tools_unused'], 2)
        self.assertEqual((row['sessions'], row['prompts']), (2, 10))
        self.assertIn('2 tools', Path(data['report_path']).read_text())

    def test_pruning_counts_only_main_sessions_and_prompts(self):
        self.audit_rows('main', [], metadata=[dict(name='mcp__idle__query')])
        for index in range(5):
            path = self.audit_rows(f'worker{index}', [], prompts=10, metadata=[dict(name='mcp__idle__query')])
            target = path.parent / f'main/subagents/worker{index}.jsonl'
            target.parent.mkdir(parents=True, exist_ok=True)
            path.rename(target)
        data = json.loads(self.run_script('token-audit', '--json').stdout)
        self.assertEqual(data['unused_tools'], [])

    def test_pruning_sort_and_report_cap(self):
        metadata = [dict(name=f'Optional{index}') for index in range(30)] + [dict(name='mcp__full__query')]
        for session in ('one', 'two'):
            self.audit_rows(session, [], prompts=5, metadata=metadata)
        data = json.loads(self.run_script('token-audit', '--json').stdout)
        self.assertEqual(len(data['unused_tools']), 31)
        self.assertEqual(data['unused_tools'][0]['candidate'], 'full')
        section = Path(data['report_path']).read_text().split('## Unused tools and MCP servers')[1]
        self.assertEqual(sum(' | built-in tool | ' in line or ' | MCP server | ' in line for line in section.splitlines()), 25)
        self.assertIn('+6 more', section)

    def test_threshold_prices_and_zero_token_unpriced(self):
        pricing = self.fixture_pricing()
        value = json.loads(pricing.read_text())
        value['models']['fixture']['over_threshold'] = dict(prompt_tokens=100, input=10, cache_read=3,
            cache_write_5m=15, cache_write_1h=20, output=25)
        pricing.write_text(json.dumps(value))
        now = datetime.now(timezone.utc).isoformat()
        usages = [dict(input_tokens=20, cache_read_input_tokens=59, cache_creation_input_tokens=20, output_tokens=10),
                  dict(input_tokens=20, cache_read_input_tokens=60, cache_creation_input_tokens=20, output_tokens=10,
                       cache_creation=dict(ephemeral_1h_input_tokens=10, ephemeral_5m_input_tokens=10))]
        rows = [dict(type='assistant', timestamp=now, message=dict(id=str(i), model='fixture-v1', usage=usage))
                for i, usage in enumerate(usages)]
        rows.append(dict(type='assistant', timestamp=now, message=dict(id='synthetic', model='<synthetic>', usage=dict(input_tokens=0))))
        jsonl(self.home / '.claude/projects/example/session.jsonl', rows)
        data = json.loads(self.run_script('token-audit', '--pricing', pricing, '--json').stdout)
        self.assertAlmostEqual(data['cost']['total'], .000209 + .00098)
        self.assertEqual(data['cost']['unpriced'], {})
        self.assertIn('pre-window cumulative usage is not seeded', Path(data['report_path']).read_text())

    def test_failure_redaction_in_errors_targets_and_hints(self):
        secrets = ['sk-' + 'secret' * 6, 'ghp_' + 'value' * 8, 'xoxb-' + 'token' * 8,
                   'AKIA' + 'B' * 16, 'ab12' * 12, 'SGVsbG9v' * 8]
        path = self.audit_rows('redact', [('Read', '', True)] * 3)
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        for row in rows:
            content = row.get('message', {}).get('content')
            if isinstance(content, list):
                if content[0]['type'] == 'tool_use':
                    content[0]['input'] = dict(file_path='/workspace/' + secrets[0])
                else:
                    content[0]['content'] = 'Error: ' + ' '.join(secrets)
        jsonl(path, rows)
        data = self.run_script('token-audit', '--fact-sessions', '1', '--json').stdout
        for secret in secrets:
            self.assertNotIn(secret, data)
        report = Path(json.loads(data)['report_path']).read_text()
        for secret in secrets:
            self.assertNotIn(secret, report)
        self.assertIn('[redacted]', report)

    def test_skips_unused_record_types_and_pre_window_user_json(self):
        path = self.audit_rows('window', [('Bash', 'pytest', True)] * 3)
        text = path.read_text()
        old_user = '{"type":"user","timestamp":"2000-01-01T00:00:00Z","message": broken}\n'
        ignored = '{"type":"progress","timestamp":"2099-01-01T00:00:00Z","data": broken}\n'
        path.write_text(old_user + ignored + text)
        data = json.loads(self.run_script('token-audit', '--json').stdout)
        self.assertEqual(data['warnings'], {})
        self.assertEqual(data['stuck_turns']['flagged_turns'], 1)


    def test_message_type_after_large_content_is_not_skipped(self):
        now = datetime.now(timezone.utc).isoformat()
        rows = [dict(timestamp=now, message=dict(content='prompt'), type='user')]
        for index in range(3):
            rows.append(dict(timestamp=now, message=dict(content=[dict(type='text', text='padding ' * 300),
                dict(type='tool_use', id=str(index), name='Bash', input=dict(command='pytest tests'))],
                id=f'message{index}', model='fixture-v1', usage=dict(input_tokens=100)), type='assistant'))
            rows.append(dict(timestamp=now, message=dict(content=[dict(type='tool_result', tool_use_id=str(index),
                is_error=True, content='Exit code 2\npytest: missing module')]), type='user'))
        jsonl(self.home / '.claude/projects/example/session.jsonl', rows)
        data = json.loads(self.run_script('token-audit', '--json').stdout)
        self.assertEqual(data['headline']['claude_calls'], 3)
        self.assertEqual(data['stuck_turns']['signatures'][0]['signature'], 'Bash pytest tests [exit 2]: pytest: missing module')


    def test_used_server_in_copied_rows_is_not_a_candidate(self):
        write(self.home / '.claude.json', json.dumps(dict(mcpServers={'claude.ai Krisp': {}})))
        path = self.audit_rows('copied', [('mcp__claude_ai_Krisp__search', '', False)], prompts=5, project='a')
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        for session in ('one', 'two'):
            copied = [dict(row, sessionId=session, uuid=f'{session}-{index}') for index, row in enumerate(rows)]
            jsonl(self.home / f'.claude/projects/z/{session}.jsonl', copied)
        data = json.loads(self.run_script('token-audit', '--json').stdout)
        self.assertEqual(data['unused_tools'], [])


    def test_report_money_cost_order_and_shares_preserve_json_precision(self):
        now = datetime.now(timezone.utc).isoformat()
        project = self.home / '.claude/projects/example'
        jsonl(project / 'main.jsonl', [dict(type='assistant', timestamp=now, message=dict(
            id='main-cost', model='code', usage=dict(input_tokens=1000000, output_tokens=200000)))])
        agent = project / 'main/subagents/worker.jsonl'
        jsonl(agent, [dict(type='assistant', timestamp=now, message=dict(id='worker-cost', model='fixture-v1',
            usage=dict(input_tokens=1000000000, output_tokens=123456)))])
        write(agent.with_suffix('.meta.json'), json.dumps(dict(agentType='z-worker')))
        pricing = self.fixture_pricing()
        data = json.loads(self.run_script('token-audit', '--pricing', pricing, '--json').stdout)
        self.assertAlmostEqual(data['cost']['total'], 2003.61728)
        self.assertAlmostEqual(data['cost']['by_agent']['z-worker'], 2000.61728)
        text = Path(data['report_path']).read_text()
        self.assertIn('Total API-equivalent cost: $2,003.62', text)
        agent_rows = text.split('Agent | API-equivalent $ | Share\n')[1].split('Model | API-equivalent $ | Share')[0]
        self.assertEqual(agent_rows.strip().splitlines()[1:], ['z-worker | $2,000.62 | 99.9%', 'main | $3.00 | 0.1%'])
        model_rows = text.split('Model | API-equivalent $ | Share\n')[1].split('Component |')[0]
        self.assertEqual(model_rows.strip().splitlines()[1:], ['fixture-v1 | $2,000.62 | 99.9%', 'code | $3.00 | 0.1%'])
        self.assertIn('uncached_input | $2,002.00 |', text)
        self.assertIn('output | $1.62 |', text)
        self.assertIn('API-equivalent cost $0.00 (0.0% of cost)', text)
        headline = self.run_script('token-audit', '--pricing', pricing).stdout
        self.assertIn('API-equivalent cost $2,003.62 (', headline)
        self.assertNotIn('2003.61728', text + headline)

    def test_stuck_table_groups_turns_before_top_ten(self):
        path = self.audit_rows('session', [('Bash', 'pytest tests', True)] * 3)
        original = [json.loads(line) for line in path.read_text().splitlines()]
        rows = []
        for turn in range(12):
            for source in original:
                row = json.loads(json.dumps(source))
                if row.get('uuid'):
                    row['uuid'] += f'-{turn}'
                message = row['message']
                if message.get('id'):
                    message['id'] += f'-{turn}'
                if isinstance(message['content'], list):
                    for block in message['content']:
                        for key in ('id', 'tool_use_id'):
                            if key in block:
                                block[key] += f'-{turn}'
                rows.append(row)
        jsonl(path, rows)
        self.audit_rows('other', [('Bash', 'npm test', True)] * 3)
        data = json.loads(self.run_script('token-audit', '--json').stdout)
        stuck = data['stuck_turns']
        self.assertEqual(stuck['flagged_turns'], 13)
        self.assertEqual(len(stuck['signatures']), 2)
        self.assertEqual((stuck['signatures'][0]['repeats'], stuck['signatures'][0]['turns']), (36, 12))
        self.assertEqual((stuck['signatures'][1]['repeats'], stuck['signatures'][1]['turns']), (3, 1))
        table = Path(data['report_path']).read_text().split('## Stuck turns')[1].split('## Repeated failures')[0]
        self.assertIn('Project | Agent | Repeats | Turns | Session | Signature', table)
        self.assertIn(' | 36 | 12 | session | Bash pytest tests:', table)
        self.assertEqual(sum(' | main | ' in line for line in table.splitlines()), 2)

    def test_pruning_report_loading_tools_and_project_plural(self):
        for session in ('one', 'two'):
            path = self.audit_rows(session, [], prompts=5, metadata=[dict(name='OptionalTool'),
                dict(name='mcp__idle__query', defer_loading=True)])
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            rows.insert(1, dict(type='api-request-shape', timestamp=rows[0]['timestamp'],
                               shape=dict(tools=[dict(name='mcp__idle__query')])))
            rows.insert(2, dict(type='attachment', timestamp=rows[0]['timestamp'],
                               attachment=dict(type='mcp_instructions_delta', addedNames=['idle'])))
            jsonl(path, rows)
        data = json.loads(self.run_script('token-audit', '--json').stdout)
        text = Path(data['report_path']).read_text().split('## Unused tools and MCP servers')[1]
        self.assertIn('idle | MCP server | 2 | 10 | 1 tools | full + instructions', text)
        self.assertIn('OptionalTool | built-in tool | 2 | 10 | — | full', text)
        self.assertNotIn('deferred, loaded in full', text)
        self.assertIn('Pruning candidates: 2 across 1 project\n', self.run_script('token-audit').stdout)
        self.assertIn('Pruning candidates: 0 across 0 projects\n', self.run_script('token-audit', '--project', 'absent').stdout)


    def test_redaction_precedes_head_hint_and_error_truncation(self):
        for index, secret in enumerate(('ab12cd34' * 5, 'QmFzZTY0' * 5)):
            command = 'pytest --token=' + secret
            hint = 'MODE=local pytest ' + 'opt.' * 12 + secret
            path = self.audit_rows(f'leak{index}', [('Bash', command, True)] * 3 + [('Bash', hint, False)],
                                   project=f'case{index}')
            self.replace_audit_errors(path, ['Exit code 2\n' + 'err. ' * 20 + secret] * 3 + ['ok'])
        result = self.run_script('token-audit', '--fact-sessions', '1', '--json').stdout
        data = json.loads(result)
        report = Path(data['report_path']).read_text()
        for secret in ('ab12cd34' * 5, 'QmFzZTY0' * 5):
            head_fragment = ('pytest --token=' + secret)[:40].split('=')[1]
            hint_fragment = ('pytest ' + 'opt.' * 12 + secret)[:80].rsplit('.', 1)[1]
            for fragment in (head_fragment, hint_fragment):
                self.assertTrue(0 < len(fragment) < 32)
                self.assertNotIn(fragment, result + report)
            self.assertNotIn(secret, result + report)
        self.assertEqual(len(data['repeat_failures']), 2)
        for fact in data['repeat_failures']:
            self.assertIn('[redacted]', fact['signature'])
            self.assertIn('[redacted]', fact['worked_instead'])
        self.assertEqual(data['stuck_turns']['flagged_turns'], 2)

    def test_success_output_exit_codes_are_not_failures(self):
        path = self.audit_rows('success', [('Bash', 'cat README.md', False)] * 3)
        self.replace_audit_errors(path, ['Exit code 2\nExample: Exit code 2\nExit code 2'] * 3)
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        for row in rows:
            if row['type'] == 'user' and isinstance(row['message']['content'], list):
                row['toolUseResult'] = dict(exitCode=2)
        jsonl(path, rows)
        data = json.loads(self.run_script('token-audit', '--fact-sessions', '1', '--json').stdout)
        self.assertEqual(data['stuck_turns']['flagged_turns'], 0)
        self.assertEqual(data['stuck_turns']['signatures'], [])
        self.assertEqual(data['repeat_failures'], [])

    def test_error_exit_code_is_read_only_from_first_line(self):
        path = self.audit_rows('error', [('Bash', 'grep -n needle missing', True)] * 3)
        self.replace_audit_errors(path, ['grep: missing file\nExample text: Exit code 1'] * 3)
        data = json.loads(self.run_script('token-audit', '--json').stdout)
        self.assertEqual(data['stuck_turns']['flagged_turns'], 1)
        self.assertNotIn('[exit', data['stuck_turns']['signatures'][0]['signature'])
        self.assertIn('grep: missing file', data['stuck_turns']['signatures'][0]['signature'])
