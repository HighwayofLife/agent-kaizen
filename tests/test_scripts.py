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
        self.assertLessEqual(len(report.read_text().splitlines()), 80)
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
