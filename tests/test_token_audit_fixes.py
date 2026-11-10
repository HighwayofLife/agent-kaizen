"""Regression tests for the usage-audit review fixes (synthetic fixtures only)."""
import contextlib
import csv
from datetime import datetime, timedelta, timezone
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_scripts import SCRIPTS, StubCase, jsonl, write  # noqa: E402


def load(name):
    loader = importlib.machinery.SourceFileLoader('fix_' + name.replace('-', '_'), str(SCRIPTS / name))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module


AUDIT = load('token-audit')
PRICING = dict(models={
    'claude-fable-5': dict(input=1, output=2, cache_read=1.0),
    'claude-fable-5-1': dict(input=1, output=2, cache_read=0.25),
    'claude-opus-5-5': dict(input=4, output=20),
    'gpt-test-sol': dict(input=1000000, cached_input=0, output=1000000)},
    aliases={'claude-fable-5': 'claude-fable-5', 'claude-fable-5-1': 'claude-fable-5-1',
             'claude-opus-5-5': 'claude-opus-5-5', 'opus': 'claude-opus-5-5',
             'gpt-test-sol': 'gpt-test-sol'})


class FixCase(StubCase):
    def setUp(self):
        super().setUp()
        self.config = self.root / 'claude-config'
        self.codex = self.root / 'codex-config'
        self.config.mkdir()
        self.codex.mkdir()
        self.env.update(CLAUDE_CONFIG_DIR=str(self.config), CODEX_HOME=str(self.codex))
        self.pricing = write(self.root / 'prices.json', json.dumps(PRICING))
        self.output = self.root / 'series'

    def assistant(self, stamp, ident, model='claude-opus-5-5', usage=None, **fields):
        usage = dict(input_tokens=100, output_tokens=10) if usage is None else usage
        return dict(type='assistant', timestamp=stamp, message=dict(
            id=ident, model=model, usage=usage, content=[]), **fields)

    def now(self):
        return datetime.now(timezone.utc).isoformat()

    def audit(self, *args):
        result = self.run_script('token-audit', '--pricing', self.pricing, '--json', *args)
        return json.loads(result.stdout)

    def series(self, *args, code=0):
        return self.run_script('usage-series', '--since', '2025-01-01', '--until', '2025-01-03',
                               '--pricing', self.pricing, '--out', self.output, *args, code=code)

    def daily(self):
        with (self.output / 'daily.csv').open() as stream:
            return list(csv.DictReader(stream))

    def codex_session(self, rows, name='session', day='2025/01/01'):
        meta = dict(type='session_meta', timestamp='2024-12-30T00:00:00Z', payload=dict(model='gpt-test-sol'))
        return jsonl(self.codex / f'sessions/{day}/{name}.jsonl', [meta] + [
            dict(type='event_msg', timestamp=stamp, payload=dict(type='token_count', info=dict(
                total_token_usage=dict(input_tokens=i, cached_input_tokens=0, output_tokens=o, total_tokens=i + o))))
            for stamp, i, o in rows])


class PricingBoundaryTests(FixCase):
    def test_pricing_key_needs_a_boundary_after_the_alias(self):
        key = AUDIT.pricing_key
        self.assertIsNone(key(PRICING, 'claude-fable-5-2'))
        self.assertIsNone(key(PRICING, 'claude-opus-5-6'))
        self.assertIsNone(key(PRICING, 'claude-opus-5-5-2026'))
        self.assertIsNone(key(PRICING, 'opus-5'))
        self.assertEqual(key(PRICING, 'claude-fable-5-1'), 'claude-fable-5-1')
        self.assertEqual(key(PRICING, 'claude-fable-5'), 'claude-fable-5')
        self.assertEqual(key(PRICING, 'claude-opus-5-5-20261001'), 'claude-opus-5-5')
        self.assertEqual(key(PRICING, 'claude-opus-5-5[1m]'), 'claude-opus-5-5')
        self.assertEqual(key(PRICING, 'claude-opus-5-5-20261001[1m]'), 'claude-opus-5-5')
        self.assertEqual(key(PRICING, 'opus'), 'claude-opus-5-5')
        # A key with no alias entry follows the same rule.
        bare = dict(models={'plain-model': dict(input=1)}, aliases={})
        self.assertEqual(key(bare, 'plain-model-20260101'), 'plain-model')
        self.assertIsNone(key(bare, 'plain-model-2'))

    def test_newer_sibling_is_unpriced_in_the_audit_and_the_series(self):
        rows = [self.assistant('2025-01-01T12:00:00Z', 'a', 'claude-fable-5-2'),
                self.assistant('2025-01-01T12:00:01Z', 'b', 'claude-opus-5-5-20261001')]
        jsonl(self.config / 'projects/example/main.jsonl', rows)
        data = self.audit('--since', '2025-01-01')
        self.assertEqual(list(data['cost']['unpriced']), ['claude-fable-5-2'])
        self.assertEqual(list(data['cost']['by_model']), ['claude-opus-5-5-20261001'])
        self.series()
        first = self.daily()[0]
        self.assertEqual(float(first['unpriced_calls']), 1)
        self.assertGreater(float(first['cost_opus']), 0)


class UniverseTests(FixCase):
    """The tool-universe rescan runs only when a main session lacks tool definitions."""

    def fixture(self, known):
        target = self.root / 'project'
        rows = [dict(type='user', timestamp=self.now(), uuid='p1', cwd=str(target), sessionId='s',
                     message=dict(content='private prompt'))]
        if known:
            rows.insert(0, dict(type='api-request-shape', timestamp=self.now(), sessionId='s',
                                shape=dict(tools=[dict(name='Read')])))
        rows.append(self.assistant(self.now(), 'm1', 'claude-opus-5-5', cwd=str(target), sessionId='s'))
        jsonl(self.config / 'projects/selected/s.jsonl', rows)
        stamp = self.now()
        other = self.config / 'projects/elsewhere/o.jsonl'
        write(other, ''.join([
            '{"type":"assistant","timestamp":"%s","message":{"id":"g1","content":[{"type":"tool_use","id":"t1",'
            '"name":"mcp__ghost__query","input":{}}]}}\n' % stamp,
            '{"type":"assistant","timestamp":"%s","message":{"id":"g2","content":[{"type":"tool_use","name":'
            '"mcp__flipped__query","id":"t2","input":{"text":"a \\"quote\\""}}]}}\n' % stamp,
            '{"type":"assistant","timestamp":"%s","message":{"id":"g3","content":[{"type":"text","text":'
            '"mentions \\"type\\":\\"tool_use\\" mcp__textonly__query only"}]}}\n' % stamp,
            '{"type":"assistant","timestamp":"2000-01-01T00:00:00Z","message":{"id":"g4","content":[{"type":"tool_use",'
            '"id":"t4","name":"mcp__stale__query","input":{}}]}}\n']))
        return target

    def run_inprocess(self, target):
        output, seen = io.StringIO(), []
        real = json.loads

        def spy(value, *args, **kwargs):
            seen.append(value if isinstance(value, str) else bytes(value).decode('utf-8', 'replace'))
            return real(value, *args, **kwargs)

        argv = ['token-audit', '--cwd', str(target), '--prune-sessions', '1', '--pricing', str(self.pricing),
                '--out', str(self.root / 'reports'), '--extract-out', str(self.root / 'extracts'), '--json']
        with mock.patch.dict(os.environ, self.env), mock.patch.object(sys, 'argv', argv), \
                mock.patch.object(json, 'loads', spy), contextlib.redirect_stdout(output):
            self.assertEqual(AUDIT.main(), 0)
        return json.loads(output.getvalue()), seen

    def test_known_sessions_do_not_rescan_other_transcripts(self):
        data, seen = self.run_inprocess(self.fixture(known=True))
        self.assertFalse([line for line in seen if 'mcp__ghost' in line or 'mcp__flipped' in line])
        self.assertEqual(data['unused_tools'], [])

    def test_unknown_session_reads_names_without_decoding_whole_lines(self):
        data, seen = self.run_inprocess(self.fixture(known=False))
        self.assertEqual({row['candidate'] for row in data['unused_tools']}, {'ghost', 'flipped'})
        # The common key order is read with a pattern; only an odd order falls back to json.loads.
        self.assertFalse([line for line in seen if 'mcp__ghost' in line])
        self.assertFalse([line for line in seen if 'mcp__textonly' in line])


class UsageSeriesWindowTests(FixCase):
    def test_old_mtime_files_are_skipped_but_recent_ones_count(self):
        old = jsonl(self.config / 'projects/example/old.jsonl', [self.assistant('2025-01-01T12:00:00Z', 'old')])
        jsonl(self.config / 'projects/example/new.jsonl', [self.assistant('2025-01-01T12:00:00Z', 'new')])
        os.utime(old, (1, 1))
        old_agent = jsonl(self.config / 'projects/example/old/subagents/a.jsonl',
                          [self.assistant('2025-01-01T12:00:00Z', 'old-sub')])
        os.utime(old_agent, (1, 1))
        old_codex = self.codex_session([('2025-01-01T12:00:00Z', 100, 10)], name='old')
        os.utime(old_codex, (1, 1))
        self.codex_session([('2025-01-01T12:00:00Z', 7, 0)], name='new', day='2025/01/02')
        self.series()
        first = self.daily()[0]
        self.assertEqual(float(first['main_calls']), 1)
        self.assertEqual(float(first['sub_calls']), 0)
        self.assertEqual(float(first['codex_sessions']), 1)

    def test_clean_split_skips_only_files_that_cannot_hold_window_rows(self):
        cutoff = datetime(2025, 1, 3, tzinfo=timezone.utc).timestamp()
        start = datetime(2025, 1, 2, tzinfo=timezone.utc).timestamp()

        def session(name, stamp, mtime):
            path = jsonl(self.config / f'projects/example/{name}.jsonl', [self.assistant(stamp, name)])
            os.utime(path, (mtime, mtime))

        session('before', '2025-01-02T12:00:00Z', cutoff - 10)
        session('ancient', '2025-01-02T12:00:00Z', start - 10)  # mtime before the window: cannot hold its rows
        session('straddle', '2025-01-02T13:00:00Z', cutoff + 10)  # modified after the cutoff: before side excludes it
        session('after', '2025-01-03T12:00:00Z', cutoff + 10)
        data = json.loads(self.run_script(
            'usage-compare', '--clean-split', '--cutoff', '2025-01-03', '--before-from', '2025-01-02',
            '--after-to', '2025-01-03', '--pricing', self.pricing, '--json').stdout)
        self.assertEqual(data['before']['metrics']['main calls/day'], 1)
        self.assertEqual(data['after']['metrics']['main calls/day'], 1)  # 'after' only; 'straddle' row is before the cutoff


class CodexDeltaTests(FixCase):
    def straddling(self):
        # 1,100 tokens before the window, +110 inside it.
        self.codex_session([('2024-12-31T12:00:00Z', 1000, 100), ('2025-01-02T12:00:00Z', 1090, 120)])

    def test_session_started_before_the_window_reports_in_window_tokens(self):
        self.straddling()
        data = self.audit('--since', '2025-01-01')
        self.assertEqual(data['codex']['gpt-test-sol']['tokens'], 110)
        self.assertEqual(data['codex']['gpt-test-sol']['input'], 90)
        self.assertEqual(data['codex']['gpt-test-sol']['output'], 20)
        self.assertEqual(data['codex_sessions'][0]['tokens'], 110)
        self.assertEqual(data['headline']['codex_tokens'], 110)
        self.assertEqual(data['headline']['codex_tokens_per_session'], 110)
        self.assertAlmostEqual(data['cost']['total'], 110)
        self.assertNotIn('pre-window cumulative usage is not seeded', Path(data['report_path']).read_text())
        self.series()
        self.assertAlmostEqual(float(self.daily()[1]['cost_sol']), data['cost']['total'])

    def test_session_with_only_old_usage_is_not_counted(self):
        self.codex_session([('2024-12-31T12:00:00Z', 1000, 100)])
        data = self.audit('--since', '2025-01-01')
        self.assertEqual(data['headline']['codex_sessions'], 0)
        self.assertEqual(data['cost']['total'], 0)

    def test_counter_reset_uses_the_current_value_in_both_tools(self):
        self.codex_session([('2025-01-01T10:00:00Z', 100, 0), ('2025-01-01T11:00:00Z', 500, 0),
                            ('2025-01-01T12:00:00Z', 50, 0), ('2025-01-01T13:00:00Z', 80, 0)])
        data = self.audit('--since', '2025-01-01')
        self.assertEqual(data['codex']['gpt-test-sol']['tokens'], 580)
        self.assertAlmostEqual(data['cost']['total'], 580)
        self.series()
        self.assertAlmostEqual(float(self.daily()[0]['cost_sol']), 580)

    def test_helper_is_shared(self):
        delta, current = AUDIT.codex_delta({'input_tokens': 10, 'output_tokens': 5},
                                           {'input_tokens': 14, 'output_tokens': 9, 'x': 'text'})
        self.assertEqual((delta['input_tokens'], delta['output_tokens']), (4, 4))
        self.assertNotIn('x', current)
        delta, _ = AUDIT.codex_delta({'input_tokens': 10, 'output_tokens': 5}, {'input_tokens': 3, 'output_tokens': 9})
        self.assertEqual((delta['input_tokens'], delta['output_tokens']), (3, 9))
        series = load('usage-series')
        self.assertEqual(series.AUDIT.codex_delta.__code__.co_filename, str(SCRIPTS / 'token-audit'))

    def test_series_counts_an_unpriced_codex_call_only_for_a_non_zero_delta(self):
        jsonl(self.codex / 'sessions/2025/01/01/unpriced.jsonl', [
            dict(type='session_meta', timestamp='2025-01-01T00:00:00Z', payload=dict(model='gpt-unpriced-test'))] + [
            dict(type='event_msg', timestamp=f'2025-01-01T12:00:0{n}Z', payload=dict(type='token_count', info=dict(
                total_token_usage=dict(input_tokens=amount, output_tokens=1))))
            for n, amount in enumerate((10, 10, 10, 20))])
        self.series()
        self.assertEqual(float(self.daily()[0]['unpriced_calls']), 2)


class MalformedTimestampTests(FixCase):
    def bad_rows(self):
        return [self.assistant('2025-01-01T12:00:00Z', 'good'),
                self.assistant('2025-99-99T00:00:00Z', 'bad')]

    def test_series_skips_and_counts_malformed_timestamps(self):
        jsonl(self.config / 'projects/example/main.jsonl', self.bad_rows())
        self.codex_session([('2025-01-01T12:00:00Z', 5, 0), ('2025-13-01T00:00:00Z', 9, 0)])
        result = self.series()
        self.assertNotIn('Traceback', result.stderr)
        self.assertEqual(float(self.daily()[0]['main_calls']), 1)
        self.assertIn('Warning: malformed rows (2)', result.stdout)

    def test_clean_split_skips_and_counts_malformed_timestamps(self):
        path = jsonl(self.config / 'projects/example/main.jsonl', self.bad_rows())
        stamp = datetime(2025, 1, 2, tzinfo=timezone.utc).timestamp() - 10
        os.utime(path, (stamp, stamp))
        result = self.run_script('usage-compare', '--clean-split', '--cutoff', '2025-01-02',
                                 '--before-from', '2025-01-01', '--after-to', '2025-01-02',
                                 '--pricing', self.pricing, '--json')
        data = json.loads(result.stdout)
        self.assertEqual(data['before']['metrics']['main calls/day'], 1)
        self.assertTrue(any('malformed rows' in warning for warning in data['warnings']))


class GitEncodingTests(FixCase):
    def test_non_utf8_file_name_is_survived_and_counted(self):
        repo = self.root / 'git'
        repo.mkdir()
        git = lambda *args, **kw: subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True, **kw)
        git('init')
        blob = git('hash-object', '-w', '--stdin', input=b'x\n').stdout.decode().strip()
        tree = git('mktree', input=b'100644 blob ' + blob.encode() + b'\tcaf\xe9.txt\n').stdout.decode().strip()
        env = dict(self.env, GIT_AUTHOR_NAME='a', GIT_AUTHOR_EMAIL='a@example.invalid', GIT_COMMITTER_NAME='a',
                   GIT_COMMITTER_EMAIL='a@example.invalid', GIT_AUTHOR_DATE='2025-01-02T12:00:00Z',
                   GIT_COMMITTER_DATE='2025-01-02T12:00:00Z')
        commit = git('commit-tree', tree, '-m', 'fixture', env=env).stdout.decode().strip()
        git('update-ref', 'refs/heads/main', commit)
        result = self.series('--git', repo)
        second = self.daily()[1]
        self.assertEqual(float(second['commits']), 1)
        self.assertEqual(float(second['lines_changed']), 1)
        self.assertIn('git output was not valid UTF-8', result.stdout)
        self.assertNotIn('Traceback', result.stderr)


class SyntheticRowTests(FixCase):
    def test_zero_usage_synthetic_rows_are_not_model_calls(self):
        now = self.now()
        rows = [self.assistant(now, 'real-1'), self.assistant(now, 'real-2'),
                self.assistant(now, 'empty', '<synthetic>', dict(input_tokens=0, output_tokens=0)),
                self.assistant(now, 'busy', '<synthetic>', dict(input_tokens=0, output_tokens=5))]
        jsonl(self.config / 'projects/example/main.jsonl', rows)
        data = self.audit()
        self.assertEqual(data['headline']['claude_calls'], 3)
        self.assertEqual(data['models']['<synthetic>']['calls'], 1)
        self.assertEqual(data['sessions'][0]['calls'], 3)


class PricingAgeTests(FixCase):
    def checked(self, value):
        prices = dict(PRICING, source=dict(checked=value)) if value is not None else dict(PRICING, source={})
        self.pricing = write(self.root / 'aged.json', json.dumps(prices))
        jsonl(self.config / 'projects/example/main.jsonl', [self.assistant(self.now(), 'a')])
        data = self.audit()
        return data, Path(data['report_path']).read_text()

    def test_old_pricing_date_warns_once_in_the_cost_section(self):
        data, text = self.checked('2020-01-02')
        lines = [line for line in text.splitlines() if 'Pricing last checked' in line]
        self.assertEqual(len(lines), 1)
        self.assertIn('2020-01-02', lines[0])
        self.assertIn('Pricing last checked 2020-01-02', data['cost']['pricing_warning'])
        self.assertLess(text.index('## Cost'), text.index('Pricing last checked'))

    def test_recent_missing_or_unparsable_dates_do_not_warn(self):
        recent = (datetime.now(timezone.utc) - timedelta(days=59)).strftime('%Y-%m-%d')
        for value in (recent, None, 'soon', 20201010, '2020-13-45'):
            data, text = self.checked(value)
            self.assertNotIn('Pricing last checked', text, value)
            self.assertIsNone(data['cost']['pricing_warning'], value)


class ArgumentTests(FixCase):
    def test_every_argument_has_help_with_its_default(self):
        body = self.run_script('token-audit', '--help').stdout.split('\n\n', 2)[2]
        help_text = {chunk.split()[0].rstrip(','): ' '.join(chunk.split())
                     for chunk in re.split(r'\n(?=  -)', body)}
        for flag, expected in (('--days', '(default: 3)'), ('--since', 'YYYY-MM-DD'), ('--out', 'default:'),
                               ('--project-dir', 'default:'), ('--stuck-repeats', '(default: 3)'),
                               ('--fact-sessions', '(default: 3)'), ('--prune-prompts', '(default: 10)'),
                               ('--prune-min-sessions', '(default: 2)'), ('--prune-sessions', '(default: 5)'),
                               ('--pricing', 'default:'), ('--cwd', 'Codex'),
                               ('--project', 'does not filter Codex sessions (--cwd does)'),
                               ('--codex', 'kept for compatibility')):
            self.assertIn(expected, help_text[flag], flag)

    def test_absurd_days_is_an_argument_error(self):
        result = self.run_script('token-audit', '--days', '99999999', code=2)
        self.assertIn('--days', result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        self.run_script('token-audit', '--days', '-1', code=2)


class LoaderTests(FixCase):
    def test_siblings_load_without_deprecation_warnings(self):
        for name in ('usage-series', 'usage-compare'):
            result = subprocess.run([sys.executable, '-W', 'error::DeprecationWarning', str(SCRIPTS / name), '--help'],
                                    capture_output=True, text=True, env=self.env)
            self.assertEqual(result.returncode, 0, result.stderr)
