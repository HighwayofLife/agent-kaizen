"""codex-run and codex-review failure handling, exercised with a scripted fake Codex."""
import json
import os
import time

try:
    from tests.test_scripts import StubCase, executable, write
except ModuleNotFoundError:
    from test_scripts import StubCase, executable, write

# PLAN is a JSON list with one entry per call (the last entry repeats):
# {"stdout": [line or event], "stderr": [line], "final": text or null, "rc": int, "sleep": seconds}
PLAN_CODEX = '''#!/usr/bin/env python3
import json, os, pathlib, sys, time
args = sys.argv[1:]
record = pathlib.Path(os.environ['RECORD'])
n = len(record.read_text().splitlines()) if record.exists() else 0
with record.open('a') as stream:
    stream.write(json.dumps(dict(args=args, prompt=sys.stdin.read())) + '\\n')
step = json.loads(os.environ['PLAN'])
step = step[min(n, len(step) - 1)]
if os.environ.get('PIDFILE'):
    pathlib.Path(os.environ['PIDFILE']).write_text(str(os.getpid()))
print(json.dumps({'type': 'thread.started', 'thread_id': 'plan-thread'}), flush=True)
for line in step.get('stdout', []):
    print(line if isinstance(line, str) else json.dumps(line), flush=True)
for line in step.get('stderr', []):
    print(line, file=sys.stderr, flush=True)
time.sleep(step.get('sleep', 0))
if step.get('final') is not None:
    pathlib.Path(args[args.index('-o') + 1]).write_text(step['final'])
sys.exit(step.get('rc', 0))
'''

CAPACITY_OUTPUT = {'type': 'item.completed', 'item': {'type': 'command_execution',
                                                      'aggregated_output': 'grep: model is at capacity\nserver_overloaded'}}
MESSAGE_ITEM = {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'we mention server_overloaded here'}}


class PlanCase(StubCase):
    def setUp(self):
        super().setUp()
        executable(self.bin / 'codex', PLAN_CODEX)

    def plan(self, *steps):
        self.env['PLAN'] = json.dumps(list(steps))


class DispatchRunTests(PlanCase):
    def test_tool_output_with_overload_text_is_not_overload(self):
        self.plan(dict(stdout=[CAPACITY_OUTPUT, MESSAGE_ITEM], final='All done'))
        result = self.dispatch()
        self.assertEqual(self.report(result)[-1], 'STATUS: DONE')
        self.assertEqual(len(self.calls()), 1)

    def test_error_event_overload_is_retried(self):
        error = {'type': 'error', 'message': 'server_overloaded'}
        self.plan(dict(stdout=[error], rc=1), dict(stdout=[], final='Recovered'))
        self.assertEqual(self.report(self.dispatch())[-1], 'STATUS: DONE')
        self.assertEqual(len(self.calls()), 2)
        self.record.unlink()
        self.plan(dict(stdout=[error], rc=1))
        self.assertEqual(self.report(self.dispatch(code=2))[-1], 'STATUS: CODEX FAILED')
        self.assertEqual(len(self.calls()), 2)

    def test_stderr_and_plain_line_overload_is_retried(self):
        for step in (dict(stderr=['Error: model is at capacity']), dict(stdout=['server_overloaded'])):
            self.record.unlink(missing_ok=True)
            self.plan(dict(step), dict(final='Recovered'))
            self.assertEqual(self.report(self.dispatch())[-1], 'STATUS: DONE')
            self.assertEqual(len(self.calls()), 2)

    def test_failure_reason_shows_stderr_and_error_events(self):
        self.plan(dict(stderr=['starting', 'Error: unauthorized, please login'], rc=1))
        reason = [line for line in self.report(self.dispatch(code=2)) if line.startswith('Reason:')]
        self.assertEqual(len(reason), 1)
        self.assertIn('unauthorized, please login', reason[0])
        self.assertNotIn('----', reason[0])
        self.plan(dict(stdout=[{'type': 'error', 'message': 'quota exceeded'},
                               {'type': 'turn.failed', 'error': {'message': 'stream closed'}}], rc=1))
        reason = [line for line in self.report(self.dispatch(code=2)) if line.startswith('Reason:')]
        self.assertIn('quota exceeded', reason[0])
        self.assertIn('stream closed', reason[0])

    def test_failure_reason_is_bounded(self):
        self.plan(dict(stderr=[f'Error line {i} ' + 'x' * 1000 for i in range(50)], rc=1))
        reason = [line for line in self.report(self.dispatch(code=2)) if line.startswith('Reason:')][0]
        self.assertLess(len(reason), 2000)
        self.assertIn('Error line 49', reason)
        self.assertNotIn('Error line 0 ', reason)

    def test_codex_timeout_is_a_failure(self):
        pidfile = self.root / 'pid'
        self.env['PIDFILE'] = str(pidfile)
        self.plan(dict(sleep=30, final='late'))
        started = time.time()
        result = self.dispatch('--codex-timeout', '1', code=2)
        self.assertLess(time.time() - started, 15)
        lines = self.report(result)
        self.assertEqual(lines[-1], 'STATUS: CODEX FAILED')
        self.assertTrue(any(line.startswith('Reason:') and 'TIMEOUT after 1s' in line for line in lines), lines)
        time.sleep(0.3)
        with self.assertRaises(ProcessLookupError):
            os.kill(int(pidfile.read_text()), 0)

    def test_codex_timeout_from_environment_and_bad_value(self):
        self.env['CODEX_DISPATCH_CODEX_TIMEOUT'] = '1'
        self.plan(dict(sleep=30, final='late'))
        self.assertEqual(self.report(self.dispatch(code=2))[-1], 'STATUS: CODEX FAILED')
        self.env['CODEX_DISPATCH_CODEX_TIMEOUT'] = 'soon'
        self.assertIn('CODEX_DISPATCH_CODEX_TIMEOUT', self.dispatch(code=2).stderr)
        self.env.pop('CODEX_DISPATCH_CODEX_TIMEOUT')
        self.assertIn('must not be negative', self.dispatch('--check-timeout', '-1', code=2).stderr)


class ReviewRunTests(PlanCase):
    def review(self, code=0):
        return self.run_script('codex-review', 'plan', self.brief, '-C', self.work, code=code)

    def test_tool_output_with_overload_text_does_not_fail_a_review(self):
        self.plan(dict(stdout=[CAPACITY_OUTPUT, MESSAGE_ITEM], final='Looks fine\nVERDICT: APPROVE'))
        result = self.review()
        self.assertEqual(result.stdout.splitlines()[-2:], ['VERDICT: APPROVE', 'STATUS: DONE'])
        self.assertEqual(len(self.calls()), 1)

    def test_real_overload_is_retried_then_fails(self):
        error = {'type': 'error', 'message': 'server_overloaded'}
        self.plan(dict(stdout=[error], rc=1), dict(final='VERDICT: APPROVE'))
        self.assertIn('STATUS: DONE', self.review().stdout)
        self.assertEqual(len(self.calls()), 2)
        self.record.unlink()
        self.plan(dict(stdout=[error], rc=1))
        self.assertTrue(self.review(code=2).stdout.endswith('STATUS: REVIEW FAILED\n'))
        self.assertEqual(len(self.calls()), 2)

    def test_nonzero_exit_with_final_message_fails_without_overload_text(self):
        self.plan(dict(final='VERDICT: APPROVE', rc=1))
        self.assertTrue(self.review(code=2).stdout.endswith('STATUS: REVIEW FAILED\n'))
        self.assertEqual(len(self.calls()), 1)

    def test_output_directory_failure_reports_review_failed(self):
        write(self.work / 'out', 'a file, not a directory')
        result = self.review(code=2)
        self.assertTrue(result.stdout.endswith('STATUS: REVIEW FAILED\n'), result.stdout + result.stderr)
        self.assertIn('Error:', result.stdout)
        self.assertNotIn('Traceback', result.stderr)
        self.assertFalse(self.record.exists())
