"""Offline time series, privacy, and comparison CLI contracts."""
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import runpy
import sqlite3
import subprocess
from unittest import mock

from test_scripts import SCRIPTS, StubCase, jsonl, write

SERIES = runpy.run_path(str(SCRIPTS / 'usage-series'))


class SeriesTests(StubCase):
    def setUp(self):
        super().setUp()
        self.env['CLAUDE_CONFIG_DIR'] = str(self.root / 'claude-config')
        self.env['CODEX_HOME'] = str(self.root / 'codex-config')
        self.config = Path(self.env['CLAUDE_CONFIG_DIR'])
        self.codex = Path(self.env['CODEX_HOME'])
        self.secret = 'PRIVATE_FIXTURE_CONTENT'
        self.cwd = str(self.root / self.secret)
        self.output = self.root / 'series'
        self.pricing = write(self.root / 'prices.json', json.dumps(dict(models={
            'claude-opus-test': dict(input=1, output=2, cache_read=0.1, cache_write_5m=1.25),
            'gpt-test-sol': dict(input=1, output=2, cached_input=0.1)}, aliases={})))

    def row(self, day, kind='assistant', content=None, ident='one', **fields):
        message = dict(content=[] if content is None else content)
        if kind == 'assistant':
            message.update(id=ident, model='claude-opus-test', usage=dict(input_tokens=100, output_tokens=10))
        return dict(type=kind, timestamp=f'2025-01-{day:02}T12:00:00Z', cwd=fields.pop('cwd', self.cwd), message=message, **fields)

    def fixtures(self):
        tool = lambda ident, name, **inputs: dict(type='tool_use', id=ident, name=name, input=inputs)
        main = self.config / 'projects/example/main.jsonl'
        first = self.row(1, content=[tool('read', 'Read', file_path=self.secret),
            tool('range', 'Read', file_path=self.secret, limit=10),
            tool('bash', 'Bash', command='tools/example find'),
            tool('spawn', 'Agent', subagent_type='worker')])
        jsonl(main, [dict(nested=dict(timestamp='2025-01-01T12:00:00Z')), self.row(1, 'user', self.secret), first, first,
            self.row(1, 'user', [dict(type='tool_result', tool_use_id='read', content=[dict(type='image')]),
                                  dict(type='tool_result', tool_use_id='range', content=self.secret)]),
            self.row(2, 'user', '<task-notification>done</task-notification>'),
            self.row(2, ident='two')])
        agent = main.parent / 'main/subagents/a.jsonl'
        jsonl(agent, [self.row(1, ident='sub', content=[tool('sub-bash', 'Bash', command='tools/example outline')])])
        write(agent.with_suffix('.meta.json'), json.dumps(dict(agentType='worker')))
        jsonl(self.config / 'projects/else/other.jsonl', [self.row(1, ident='else', cwd='/elsewhere')])
        log = self.codex / 'sessions/2025/01/01/session.jsonl'
        rows = [dict(type='session_meta', timestamp='2024-12-31T00:00:00Z', payload=dict(cwd=self.cwd, model='gpt-test-sol'))]
        for day, amount in [(0, 100), (1, 200), (2, 300), (2, 10)]:
            timestamp = '2024-12-31T12:00:00Z' if day == 0 else f'2025-01-{day:02}T12:00:00Z'
            rows.append(dict(type='event_msg', timestamp=timestamp, payload=dict(type='token_count', info=dict(
                total_token_usage=dict(input_tokens=amount, cached_input_tokens=0, output_tokens=amount // 10)))))
        jsonl(log, rows)
        self.codex.mkdir(exist_ok=True)
        for version in (4, 5):
            with sqlite3.connect(self.codex / f'state_{version}.sqlite') as db:
                db.execute('CREATE TABLE threads (created_at INTEGER, model TEXT, cwd TEXT, tokens_used INTEGER, title TEXT, first_user_message TEXT, preview TEXT)')
                for day, cwd in [(1, self.cwd), (2, '/elsewhere')]:
                    db.execute('INSERT INTO threads VALUES (?, ?, ?, ?, ?, ?, ?)', (
                        int(datetime(2025, 1, day, tzinfo=timezone.utc).timestamp()), 'gpt-test-sol', cwd,
                        1000 * version, self.secret, self.secret, self.secret))
        return main

    def series(self, *args):
        return self.run_script('usage-series', '--since', '2025-01-01', '--until', '2025-01-03',
            '--pricing', self.pricing, '--out', self.output, *args)

    def read_daily(self):
        with (self.output / 'daily.csv').open() as stream:
            return list(csv.DictReader(stream))

    def test_daily_selection_costs_and_privacy(self):
        self.fixtures()
        self.series('--cwd', self.cwd, '--count-command', 'example=^tools/example')
        first, second, empty = self.read_daily()
        self.assertEqual([r['date'] for r in (first, second, empty)], ['2025-01-01', '2025-01-02', '2025-01-03'])
        for key, expected in dict(main_calls=1, main_avg_ctx=100, main_peak_ctx=100, main_images=1,
                                  main_reads=1, sub_calls=1, spawns_total=1, command_example=2,
                                  codex_sessions=1, codex_threads_db=1, codex_tokens_db=5000,
                                  codex_tokens_db_sol=5000, claude_context_tokens=200, claude_output_tokens=20,
                                  main_context_tokens=100, sub_context_tokens=100, unpriced_calls=0).items():
            self.assertEqual(float(first[key]), expected, key)
        self.assertAlmostEqual(float(first['cost_opus']), 0.00024)
        self.assertAlmostEqual(float(first['cost_sol']), 0.00012)
        self.assertAlmostEqual(float(first['cost_total']), 0.00036)
        self.assertEqual(float(second['wakeups']), 1)
        self.assertAlmostEqual(float(second['cost_sol']), 0.000132)
        self.assertEqual(float(empty['main_calls']), 0)
        with (self.output / 'daily-agents.csv').open() as stream:
            agents = list(csv.DictReader(stream))
        self.assertEqual(len(agents), 1)
        self.assertEqual(agents[0]['agent_type'], 'worker')
        self.assertEqual(int(agents[0]['runs']), 1)
        for path in self.output.glob('*.csv'):
            value = path.read_text()
            for private in (self.secret, self.cwd, 'main.jsonl', '/elsewhere', 'tools/example'):
                self.assertNotIn(private, value)
        self.series('--project', 'example')
        self.assertEqual(float(self.read_daily()[0]['codex_tokens_db']), 0)
        self.series('--cwd', self.cwd, '--cwd', '/elsewhere')
        self.assertEqual(float(self.read_daily()[0]['main_calls']), 2)
        self.series()
        self.assertEqual(float(self.read_daily()[1]['codex_tokens_db']), 5000)

    def test_transcript_older_than_the_window_is_skipped_by_modification_time(self):
        # A transcript cannot hold rows newer than its last write, so an old mtime means no rows in the window.
        path = jsonl(self.config / 'projects/example/stale.jsonl', [self.row(2, ident='stale')])
        os.utime(path, (1733011200, 1733011200))  # 2024-12-01
        self.series()
        self.assertEqual(float(self.read_daily()[1]['main_calls']), 0)
        os.utime(path, (1736000000, 1736000000))  # 2025-01-04
        self.series()
        self.assertEqual(float(self.read_daily()[1]['main_calls']), 1)

    def test_database_missing_columns_and_lock_copy(self):
        self.fixtures()
        path = self.codex / 'state_5.sqlite'
        args = type('Args', (), dict(since=SERIES['date']('2025-01-01'), stop=SERIES['date']('2025-01-03'), cwd=None, project=None))()
        from collections import Counter, defaultdict
        function = SERIES['scan_database']
        original = function.__globals__['database_rows']
        def locked_then_copy(candidate, options):
            if candidate == path:
                raise sqlite3.OperationalError('database is locked')
            self.assertNotEqual(candidate.parent, path.parent)
            self.assertEqual(candidate.name, path.name)
            self.assertEqual(candidate.read_bytes(), path.read_bytes())
            return original(candidate, options)
        with mock.patch.dict(os.environ, CODEX_HOME=str(self.codex)):
            with mock.patch.dict(function.__globals__, database_rows=mock.Mock(side_effect=locked_then_copy)):
                days, warnings = defaultdict(Counter), Counter()
                function(args, days, warnings)
                self.assertEqual(days['2025-01-01']['codex_tokens_db'], 5000)
                self.assertFalse(warnings)
        path.unlink()
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE threads (created_at INTEGER)')
        result = self.series()
        self.assertIn('missing required table/columns', result.stdout)
        self.assertIn('1 warnings', result.stdout)

    def test_git_author_dates_all_refs_and_deduplication(self):
        repo = self.root / 'git'
        def git(*args, **kw):
            return subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True, text=True, **kw)
        repo.mkdir()
        git('init')
        git('config', 'user.name', 'Fixture')
        git('config', 'user.email', 'fixture@example.invalid')
        for day in (1, 2):
            write(repo / 'file', 'line\n' * day)
            git('add', '.')
            env = dict(self.env, GIT_AUTHOR_DATE=f'2025-01-{day:02}T23:00:00-01:00', GIT_COMMITTER_DATE='2025-02-01T00:00:00Z')
            git('commit', '-m', 'fixture', env=env)
        git('branch', 'extra-ref')
        result = self.series('--git', repo, '--git', repo, '--git', self.root / 'missing')
        first, second, third = self.read_daily()
        self.assertEqual(float(first['commits']), 0)
        self.assertEqual(float(second['commits']), 1)
        self.assertEqual(float(third['lines_changed']), 1)
        self.assertIn('git repository unavailable', result.stdout)

    def test_unpriced_models_and_synthetic_rows(self):
        rows = []
        for ident, model, usage in (
            ('unknown', 'claude-new-test', dict(input_tokens=10, output_tokens=2)),
            ('synthetic', '<synthetic>', dict(input_tokens=0, output_tokens=0)),
            ('cached', 'claude-opus-test', dict(input_tokens=10, cache_read_input_tokens=20,
                                             cache_creation_input_tokens=30, output_tokens=4))):
            row = self.row(1, ident=ident)
            row['message'].update(model=model, usage=usage)
            rows.append(row)
        jsonl(self.config / 'projects/example/main.jsonl', rows)
        jsonl(self.codex / 'sessions/2025/01/01/session.jsonl', [
            dict(type='session_meta', timestamp='2025-01-01T00:00:00Z',
                 payload=dict(model='gpt-unpriced-test', cwd=self.cwd)),
            dict(type='event_msg', timestamp='2025-01-01T12:00:00Z',
                 payload=dict(type='token_count', info=dict(total_token_usage=dict(
                     input_tokens=10, output_tokens=5))))])
        result = self.series()
        first = self.read_daily()[0]
        self.assertEqual(float(first['main_calls']), 2)
        self.assertEqual(float(first['unpriced_calls']), 2)
        self.assertEqual(float(first['claude_context_tokens']), 70)
        self.assertEqual(float(first['claude_output_tokens']), 6)
        self.assertIn('claude-new-test', result.stdout)
        self.assertIn('gpt-unpriced-test', result.stdout)
        self.assertNotIn('<synthetic>', result.stdout)

    def test_compare_mixed_missing_days_and_token_volumes(self):
        self.output.mkdir()
        fields = ('date main_calls cost_opus cost_sol codex_tokens_db commits '
                  'claude_context_tokens claude_output_tokens unpriced_calls').split()
        with (self.output / 'daily.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for day, calls, claude, codex, commits in [(1, 100, 100, 0, 10), (2, 200, 20, 40, 2), (3, 300, 30, 60, 3)]:
                writer.writerow(dict(zip(fields, [f'2025-01-{day:02}', calls, claude, codex,
                                                  1000, commits, 2000, 100, 1])))
        data = json.loads(self.run_script('usage-compare', '--series', self.output,
            '--cutoff', '2025-01-04', '--json').stdout)
        metrics = data['before']['metrics']
        for name, expected in {'Codex cost/day': 50, 'total cost/day': 75,
                               'Codex cost/main call': 0.2, 'total cost/main call': 0.3,
                               'cost/commit': 30, 'Claude cost/day': 50,
                               'Claude cost/main call': 0.25, 'Claude tokens/day': 2100,
                               'Claude + Codex DB tokens/day': 3100, 'tokens/commit': 620}.items():
            self.assertAlmostEqual(metrics[name], expected, msg=name)
        self.assertIn('before: Codex logs missing on 2025-01-01; Codex and total cost use 2 of 3 active days', data['warnings'])
        self.assertIn('before: 3 unpriced calls; costs are incomplete', data['warnings'])
        self.assertIsNone(data['after']['metrics']['Claude tokens/day'])

    def test_clean_split_empty_side_and_untriggered_calls(self):
        main = self.config / 'projects/example/main.jsonl'
        jsonl(main, [self.row(1, 'user', self.secret), self.row(2, ident='untriggered')])
        cutoff = SERIES['date']('2025-01-02').timestamp()
        os.utime(main, (cutoff - 10, cutoff - 10))
        data = json.loads(self.run_script('usage-compare', '--clean-split',
            '--cutoff', '2025-01-02', '--before-from', '2025-01-01', '--after-to', '2025-01-02',
            '--pricing', self.pricing, '--json').stdout)
        self.assertIn('before: 0 calls in clean split window', data['warnings'])
        self.assertEqual(data['after']['metrics']['main calls/day'], 1)
        self.assertEqual(data['after']['metrics']['avg context'], 100)
        self.assertEqual(data['after']['metrics']['peak context'], 100)
        self.assertAlmostEqual(data['after']['metrics']['Claude cost/main call'], 0.00012)

    def compare_fixture(self):
        self.output.mkdir()
        fields = 'date main_calls main_avg_ctx main_peak_ctx wakeups main_images cost_opus cost_sol codex_tokens_db commits command_example'.split()
        with (self.output / 'daily.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for day, calls, ctx, cost, codex in [(1, 10, 999, 999, 0), (2, 100, 100, 10, 2), (3, 100, 200, 20, 2), (4, 200, 50, 10, 0)]:
                writer.writerow(dict(zip(fields, [f'2025-01-{day:02}', calls, ctx, ctx * 2, 2, 4, cost, codex, 1000, 2, 6])))

    def test_compare_active_days_ratios_and_missing_logs(self):
        self.compare_fixture()
        args = ('--series', self.output, '--cutoff', '2025-01-04')
        data = json.loads(self.run_script('usage-compare', *args, '--json').stdout)
        self.assertEqual(data['before']['active_days'], ['2025-01-02', '2025-01-03'])
        self.assertEqual(data['ratios']['main calls/day'], 2)
        self.assertEqual(data['ratios']['avg context'], round(1 / 3, 6))
        self.assertIsNone(data['after']['metrics']['Codex cost/day'])
        self.assertIsNone(data['after']['metrics']['total cost/day'])
        self.assertEqual(data['after']['metrics']['Claude cost/day'], 10)
        self.assertEqual(data['after']['metrics']['command_example/main call'], 0.03)
        self.assertEqual(len(data['warnings']), 3)
        table = self.run_script('usage-compare', *args).stdout
        self.assertIn('n/a (logs missing)', table)
        self.assertLessEqual(len(table.splitlines()), 40)
        limited = json.loads(self.run_script('usage-compare', *args, '--before-from', '2025-01-03', '--after-to', '2025-01-04', '--json').stdout)
        self.assertEqual(limited['before']['active_days'], ['2025-01-03'])

    def test_clean_split_excludes_late_files_and_writes_only_temporary_audits(self):
        main = self.fixtures()
        cutoff = SERIES['date']('2025-01-02').timestamp()
        for path in self.config.rglob('*.jsonl'):
            os.utime(path, (cutoff - 10, cutoff - 10))
        late = main.with_name('late.jsonl')
        jsonl(late, [self.row(1, 'user', self.secret), self.row(1, ident='late')])
        result = self.run_script('usage-compare', '--cutoff', '2025-01-02',
            '--before-from', '2025-01-01', '--after-to', '2025-01-02', '--pricing', self.pricing,
            '--cwd', self.cwd, '--clean-split', '--json')
        data = json.loads(result.stdout)
        self.assertEqual(data['before']['metrics']['main calls/day'], 1)
        self.assertEqual(data['after']['metrics']['main calls/day'], 1)
        self.assertFalse(list(self.config.rglob('*.md')))
        self.assertFalse(list(self.config.rglob('*.extract.json')))

    def from_db_pair(self, *args):
        """Run usage-series on transcripts and from the database; return both daily/agents tables."""
        self.env['KAIZEN_USAGE_DB'] = str(self.root / 'store' / 'usage.db')
        self.run_script('usage-db', 'ingest', '--quiet')
        tables = []
        for flags in ((), ('--from-db',)):
            self.output = self.root / ('series-db' if flags else 'series')
            self.series(*args, *flags)
            with (self.output / 'daily-agents.csv').open() as stream:
                tables.append([self.read_daily(), list(csv.DictReader(stream))])
        return tables

    def assert_same_except_not_stored(self, transcripts, stored):
        not_stored = set(SERIES['NOT_STORED']) | {'codex_tokens_db_' + f for f in SERIES['CODEX']} | {'command_example'}
        self.assertEqual(len(transcripts[0]), len(stored[0]))
        seen = set()
        for left, right in zip(transcripts[0], stored[0]):
            self.assertEqual(left.keys(), right.keys())
            for key in left:
                if key in not_stored:
                    self.assertEqual(right[key], 'n/a', key)
                    seen.add(key)
                else:
                    self.assertEqual(left[key], right[key], (left['date'], key))
        for left, right in zip(transcripts[1], stored[1]):
            self.assertEqual(right.pop('runs'), 'n/a')
            left.pop('runs')
            self.assertEqual(left, right)
        return seen

    def test_from_db_equals_transcripts_where_both_have_data(self):
        self.fixtures()
        transcripts, stored = self.from_db_pair('--count-command', 'example=^tools/example')
        seen = self.assert_same_except_not_stored(transcripts, stored)
        self.assertIn('command_example', seen)
        self.assertIn('wakeups', seen)
        # The fixture exercises Claude main and sub-agent calls, Codex deltas, and real costs.
        row = {r['date']: r for r in transcripts[0]}['2025-01-01']
        self.assertGreater(float(row['cost_total']), 0)
        self.assertEqual(row['sub_calls'], '1')
        self.assertEqual(row['codex_sessions'], '1')
        self.assertEqual(len(transcripts[1]), 1)

    def test_from_db_equals_transcripts_for_a_selection(self):
        self.fixtures()
        # Claude names a project folder after the working directory; make the fixture do the same.
        slug = lambda path: ''.join(c if c.isalnum() else '-' for c in path)
        (self.config / 'projects/example').rename(self.config / 'projects' / slug(self.cwd))
        (self.config / 'projects/else').rename(self.config / 'projects' / slug('/elsewhere'))
        for flag in (('--cwd', self.cwd), ('--project', 'PRIVATE-FIXTURE'), ('--project', 'nothing-like-this')):
            transcripts, stored = self.from_db_pair(*flag)
            self.assert_same_except_not_stored(transcripts, stored)
        self.assertEqual({r['main_calls'] for r in transcripts[0]}, {'0'})
        transcripts, stored = self.from_db_pair('--project', 'PRIVATE-FIXTURE')
        self.assertEqual({r['main_calls'] for r in stored[0]}, {'1', '0'})

    def test_from_db_reports_a_window_whose_transcripts_are_gone(self):
        self.fixtures()
        self.env['KAIZEN_USAGE_DB'] = str(self.root / 'store' / 'usage.db')
        self.run_script('usage-db', 'ingest', '--quiet')
        for path in list(self.config.rglob('*.jsonl')) + list(self.codex.rglob('*.jsonl')):
            path.unlink()
        self.series()
        self.assertEqual(sum(float(r['cost_total']) for r in self.read_daily()), 0)
        self.series('--from-db')
        self.assertGreater(sum(float(r['cost_total']) for r in self.read_daily()), 0)
        self.assertEqual(self.read_daily()[0]['main_calls'], '2')

    def test_from_db_without_a_database_is_one_line(self):
        self.env['KAIZEN_USAGE_DB'] = str(self.root / 'absent' / 'usage.db')
        result = self.run_script('usage-series', '--out', self.output, '--from-db', code=1)
        self.assertEqual(result.stderr.count('\n'), 1)
        self.assertIn('usage-series: no database at', result.stderr)
        self.assertFalse((self.root / 'absent').exists())
        self.assertIn('--from-db', self.run_script('usage-series', '--help').stdout)
        self.assertIn('n/a', self.run_script('usage-series', '--help').stdout)
        self.assertIn(' '.join('Calls without an id that share the same second and usage are counted once in the database.'.split()),
                      ' '.join(self.run_script('usage-series', '--help').stdout.split()))

    def compare_transcripts(self):
        """Two main files and two sub-agent files on either side of the cutoff; none spans it."""
        def call(day, ident, **usage):
            row = self.row(day, ident=ident)
            row['message']['usage'] = dict(input_tokens=100, output_tokens=10, **usage)
            return row
        early, late = self.config / 'projects/example/early.jsonl', self.config / 'projects/example/late.jsonl'
        jsonl(early, [self.row(1, 'user', self.secret), call(1, 'e1'), call(2, 'e2', cache_read_input_tokens=900),
                      call(2, 'e3', cache_creation_input_tokens=50)])
        jsonl(early.parent / 'early/subagents/s.jsonl', [call(2, 's1', cache_read_input_tokens=400)])
        write((early.parent / 'early/subagents/s.meta.json'), json.dumps(dict(agentType='worker')))
        jsonl(late, [self.row(3, 'user', self.secret), call(3, 'l1', cache_read_input_tokens=2000), call(4, 'l2'),
                     self.row(4, 'user', '<task-notification>done</task-notification>'), call(4, 'l3'),
                     self.row(4, 'user', [dict(type='tool_result', tool_use_id='x', content=[dict(type='image')])])])
        jsonl(late.parent / 'late/subagents/s.jsonl', [call(4, 's2')])
        stamp = SERIES['date']('2025-01-03').timestamp() - 10
        for path in (early, early.parent / 'early/subagents/s.jsonl'):
            os.utime(path, (stamp, stamp))
        return ('--cutoff', '2025-01-03', '--before-from', '2025-01-01', '--after-to', '2025-01-04',
                '--pricing', self.pricing)

    def test_compare_from_db_equals_clean_split_where_both_have_data(self):
        args = self.compare_transcripts()
        self.env['KAIZEN_USAGE_DB'] = str(self.root / 'store' / 'usage.db')
        self.run_script('usage-db', 'ingest', '--quiet')
        want = json.loads(self.run_script('usage-compare', '--clean-split', *args, '--json').stdout)
        got = json.loads(self.run_script('usage-compare', '--clean-split', '--from-db', *args, '--json').stdout)
        self.assertGreater(want['before']['metrics']['Claude cost/day'], 0)
        for side in ('before', 'after'):
            for name, value in want[side]['metrics'].items():
                if name in ('wake-ups/day', 'images/day'):
                    self.assertIsNone(got[side]['metrics'][name], name)
                    self.assertGreater(want['after']['metrics'][name], 0)
                else:
                    self.assertAlmostEqual(got[side]['metrics'][name], value, places=12, msg=(side, name))
            self.assertEqual(got[side]['window_days'], want[side]['window_days'])
        # The table a person reads is identical on every metric that is stored.
        shown = lambda *flags: [l for l in self.run_script('usage-compare', '--clean-split', *flags, *args).stdout.splitlines()
                                if not l.startswith(('wake-ups/day', 'images/day', 'Warning'))]
        self.assertEqual(shown(), shown('--from-db'))
        table = self.run_script('usage-compare', '--clean-split', '--from-db', *args).stdout
        self.assertRegex(table, r'wake-ups/day\s+n/a\s+n/a')
        self.assertRegex(table, r'images/day\s+n/a\s+n/a')

    def test_compare_from_db_reads_a_window_whose_transcripts_are_gone(self):
        args = self.compare_transcripts()
        self.env['KAIZEN_USAGE_DB'] = str(self.root / 'store' / 'usage.db')
        self.run_script('usage-db', 'ingest', '--quiet')
        for path in self.config.rglob('*.jsonl'):
            path.unlink()
        gone = json.loads(self.run_script('usage-compare', '--clean-split', *args, '--json').stdout)
        self.assertEqual(gone['after']['metrics']['main calls/day'], 0)
        kept = json.loads(self.run_script('usage-compare', '--clean-split', '--from-db', *args, '--json').stdout)
        self.assertEqual(kept['after']['metrics']['main calls/day'], 1.5)

    def test_compare_from_db_errors_and_help(self):
        args = self.compare_transcripts()
        self.env['KAIZEN_USAGE_DB'] = str(self.root / 'absent' / 'usage.db')
        result = self.run_script('usage-compare', '--clean-split', '--from-db', *args, code=1)
        self.assertEqual(result.stderr.count('\n'), 1)
        self.assertIn('usage-compare: no database at', result.stderr)
        self.assertFalse((self.root / 'absent').exists())
        self.assertIn('--clean-split', self.run_script('usage-compare', '--from-db', '--cutoff', '2025-01-03',
                                                       '--series', self.output, code=2).stderr)
        help_text = self.run_script('usage-compare', '--help').stdout
        self.assertIn('--from-db', help_text)
        self.assertIn('n/a', help_text)
        self.assertIn('Calls without an id that share the same second and usage are counted once in the database.',
                      ' '.join(help_text.split()))

    def test_help_and_invalid_arguments(self):
        for name in ('usage-series', 'usage-compare'):
            self.assertIn('usage:', self.run_script(name, '--help').stdout)
        self.run_script('usage-compare', '--cutoff', '2025-01-02', code=2)
        self.run_script('usage-series', '--out', self.output, '--count-command', 'bad', code=2)
        self.run_script('usage-series', '--out', self.output, '--since', '2025-01-03', '--until', '2025-01-01', code=2)
