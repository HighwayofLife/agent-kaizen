"""usage-db: ingest, status, report and sql, with synthetic transcripts in temp dirs."""
import csv
import importlib.util
from importlib.machinery import SourceFileLoader
import io
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_scripts import SCRIPTS, StubCase, jsonl, write  # noqa: E402

PRICES = dict(models={
    'claude-opus-test': dict(input=1, output=2, cache_read=0.1, cache_write_5m=1.25, cache_write_1h=2),
    'claude-big-test': dict(input=1, output=2, cache_read=0.1, cache_write_5m=1.25, cache_write_1h=2,
                            over_threshold=dict(prompt_tokens=1000, input=3, output=6, cache_read=0.3,
                                                cache_write_5m=3.75, cache_write_1h=6)),
    'gpt-test-sol': dict(input=1, output=2, cached_input=0.1)}, aliases={})
SUMMARY = re.compile(r'(\d+) files seen, (\d+) read, (\d+) calls added, (\d+) warnings')


def assistant(stamp, ident, model='claude-opus-test', usage=None, **fields):
    usage = dict(input_tokens=100, output_tokens=10) if usage is None else usage
    message = dict(content=[], model=model, usage=usage)
    if ident is not None:
        message['id'] = ident
    return dict(type='assistant', timestamp=stamp, message=message, **fields)


def token_count(stamp, input_, cached, output, **extra):
    return dict(type='event_msg', timestamp=stamp, payload=dict(type='token_count', info=dict(
        total_token_usage=dict(input_tokens=input_, cached_input_tokens=cached, output_tokens=output,
                               total_tokens=input_ + output, **extra))))


class UsageDbCase(StubCase):
    def setUp(self):
        super().setUp()
        self.config = self.root / 'claude-config'
        self.codex = self.root / 'codex-config'
        self.db = self.root / 'store' / 'usage.db'
        self.cwd = str(self.root / 'PROJECT_ALPHA')
        self.env.update(CLAUDE_CONFIG_DIR=str(self.config), CODEX_HOME=str(self.codex), KAIZEN_USAGE_DB=str(self.db))
        self.config.mkdir()
        self.codex.mkdir()
        self.prices = write(self.root / 'prices.json', json.dumps(PRICES))

    def main_file(self, rows, name='main', project='alpha'):
        return jsonl(self.config / 'projects' / project / f'{name}.jsonl', rows)

    def codex_file(self, rows, name='rollout-one', day='2025/01/01', cwd=None, session_id=None):
        meta = dict(type='session_meta', timestamp='2024-12-31T00:00:00Z',
                    payload=dict(cwd=cwd or self.cwd, model='gpt-test-sol'))
        if session_id:
            meta['payload']['id'] = session_id
        return jsonl(self.codex / 'sessions' / day / f'{name}.jsonl', [meta] + rows)

    def ingest(self, *args, **kwargs):
        return self.run_script('usage-db', 'ingest', *args, **kwargs)

    def counts(self, text):
        match = SUMMARY.search(text)
        self.assertIsNotNone(match, text)
        return tuple(int(v) for v in match.groups())

    def query(self, sql, *args):
        with sqlite3.connect(self.db) as conn:
            return conn.execute(sql, args).fetchall()

    def report(self, *args):
        return json.loads(self.run_script('usage-db', 'report', '--pricing', self.prices, '--format', 'json', *args).stdout)

    def basic(self):
        self.main_file([
            dict(type='user', timestamp='2025-01-01T11:00:00Z', cwd=self.cwd, message=dict(content='SECRET_PROMPT')),
            assistant('2025-01-01T12:00:00Z', 'a', cwd=self.cwd),
            assistant('2025-01-02T12:00:00Z', 'b', cwd=self.cwd,
                      usage=dict(input_tokens=50, output_tokens=5, cache_read_input_tokens=20,
                                 cache_creation_input_tokens=30, cache_creation=dict(ephemeral_1h_input_tokens=10)))])


class IngestTests(UsageDbCase):
    def test_first_ingest_stores_calls_and_columns(self):
        self.basic()
        result = self.ingest()
        self.assertEqual(self.counts(result.stdout), (1, 1, 2, 0))
        rows = self.query('SELECT source, call_id, ts, day, project, session, agent, model, input, cache_read, '
                          'cache_write_5m, cache_write_1h, output FROM calls ORDER BY call_id')
        self.assertEqual(rows[0], ('claude', 'a', '2025-01-01T12:00:00Z', '2025-01-01', self.cwd, 'main', 'main',
                                   'claude-opus-test', 100, 0, 0, 0, 10))
        self.assertEqual(rows[1][8:], (50, 20, 20, 10, 5))

    def test_second_ingest_adds_nothing_and_reads_no_file(self):
        self.basic()
        self.codex_file([token_count('2025-01-01T12:00:00Z', 100, 0, 10)])
        self.assertEqual(self.counts(self.ingest().stdout), (2, 2, 3, 0))
        self.assertEqual(self.counts(self.ingest().stdout), (2, 0, 0, 0))
        self.assertEqual(self.query('SELECT count(*) FROM calls'), [(3,)])

    def test_quiet_prints_nothing(self):
        self.basic()
        self.assertEqual(self.ingest('--quiet').stdout, '')
        self.assertEqual(self.query('SELECT count(*) FROM calls'), [(2,)])

    def test_quiet_summarises_warnings_on_stderr_only(self):
        path = self.main_file([assistant('2025-01-01T12:00:00Z', 'a')])
        with path.open('a') as stream:
            stream.write('{"timestamp": "2025-01-01T12:01:00Z", broken\n')
        result = self.ingest('--quiet')
        self.assertEqual(result.stdout, '')
        lines = result.stderr.strip().splitlines()
        self.assertEqual(len(lines), 1, result.stderr)
        self.assertRegex(lines[0], r'^Warning: .*\(\d+\)')
        self.assertEqual(self.ingest('--quiet').stderr, '')
        self.assertIn('Warning:', self.ingest('--db', self.root / 'other.db').stdout)

    def test_appended_transcript_adds_only_new_calls(self):
        path = self.main_file([assistant('2025-01-01T12:00:00Z', 'a')])
        self.ingest()
        with path.open('a') as stream:
            stream.write(json.dumps(assistant('2025-01-01T13:00:00Z', 'b')) + '\n')
        self.assertEqual(self.counts(self.ingest().stdout), (1, 1, 1, 0))
        self.assertEqual(self.query('SELECT count(*) FROM calls'), [(2,)])

    def test_same_message_id_in_two_files_and_rows_counts_once(self):
        row = assistant('2025-01-01T12:00:00Z', 'dup')
        self.main_file([row, row])
        self.main_file([row, assistant('2025-01-01T13:00:00Z', 'other')], name='resumed')
        self.assertEqual(self.counts(self.ingest().stdout)[2], 2)
        self.assertEqual(self.query('SELECT count(*) FROM calls'), [(2,)])

    def test_missing_message_id_gets_a_stable_id(self):
        path = self.main_file([assistant('2025-01-01T12:00:00Z', None)])
        self.ingest()
        first = self.query('SELECT call_id FROM calls')
        with path.open('a') as stream:
            stream.write(json.dumps(assistant('2025-01-01T13:00:00Z', 'x')) + '\n')
        self.ingest()
        self.assertEqual(len(self.query('SELECT call_id FROM calls')), 2)
        self.assertIn(first[0], self.query('SELECT call_id FROM calls'))

    def test_synthetic_zero_usage_rows_are_not_calls(self):
        self.main_file([
            assistant('2025-01-01T12:00:00Z', 's', model='<synthetic>', usage=dict(input_tokens=0, output_tokens=0)),
            assistant('2025-01-01T12:01:00Z', 'e', usage={}),
            assistant('2025-01-01T12:02:00Z', 'real')])
        self.assertEqual(self.counts(self.ingest().stdout)[2], 1)
        self.assertEqual(self.query('SELECT call_id FROM calls'), [('real',)])

    def test_subagent_label_session_and_project(self):
        self.main_file([assistant('2025-01-01T12:00:00Z', 'm', cwd=self.cwd)], name='sess')
        sub = self.config / 'projects/alpha/sess/subagents/a1.jsonl'
        jsonl(sub, [assistant('2025-01-01T12:01:00Z', 's')])
        write(sub.with_suffix('.meta.json'), json.dumps(dict(agentType='worker')))
        orphan = self.config / 'projects/alpha/gone/subagents/a2.jsonl'
        jsonl(orphan, [assistant('2025-01-01T12:02:00Z', 'o')])
        write(orphan.with_suffix('.meta.json'), json.dumps(dict(agentType='bad label!')))
        self.ingest()
        rows = {r[0]: r[1:] for r in self.query('SELECT call_id, agent, session, project FROM calls')}
        self.assertEqual(rows['m'], ('main', 'sess', self.cwd))
        self.assertEqual(rows['s'], ('worker', 'sess', self.cwd))
        self.assertEqual(rows['o'], ('unknown', 'gone', 'alpha'))

    def test_codex_deltas_with_counter_reset(self):
        self.codex_file([
            token_count('2025-01-01T10:00:00Z', 100, 20, 10),
            token_count('2025-01-01T10:01:00Z', 100, 20, 10),
            token_count('2025-01-01T10:02:00Z', 250, 70, 30),
            token_count('2025-01-01T10:03:00Z', 50, 0, 5),
            token_count('2025-01-01T10:04:00Z', 80, 10, 8)])
        self.assertEqual(self.counts(self.ingest().stdout)[2], 4)
        rows = self.query('SELECT source, agent, project, model, input, cache_read, cache_write_5m, cache_write_1h, '
                          'output FROM calls ORDER BY ts')
        self.assertEqual([r[4:] for r in rows], [(80, 20, 0, 0, 10), (100, 50, 0, 0, 20),
                                                  (50, 0, 0, 0, 5), (20, 10, 0, 0, 3)])
        self.assertEqual(rows[0][:4], ('codex', 'main', self.cwd, 'gpt-test-sol'))
        ids = [r[0] for r in self.query('SELECT call_id FROM calls')]
        self.assertEqual(len(set(ids)), 4)
        self.ingest()
        self.assertEqual(self.query('SELECT count(*) FROM calls'), [(4,)])

    def test_codex_growth_adds_only_new_deltas(self):
        path = self.codex_file([token_count('2025-01-01T10:00:00Z', 100, 0, 10)])
        self.ingest()
        with path.open('a') as stream:
            stream.write(json.dumps(token_count('2025-01-01T10:05:00Z', 160, 0, 16)) + '\n')
        self.assertEqual(self.counts(self.ingest().stdout)[2], 1)
        self.assertEqual(self.query('SELECT input, output FROM calls ORDER BY ts'), [(100, 10), (60, 6)])

    def test_copied_or_moved_codex_session_is_not_counted_twice(self):
        rows = [token_count('2025-01-01T10:00:00Z', 100, 20, 10), token_count('2025-01-01T10:05:00Z', 250, 70, 30)]
        original = self.codex_file(rows, session_id='sess-1')
        self.assertEqual(self.counts(self.ingest().stdout)[2], 2)
        copy = self.codex_file(rows, name='rollout-copy', day='2025/02/09', session_id='sess-1')
        self.assertEqual(self.counts(self.ingest().stdout)[:3], (2, 1, 0))
        original.unlink()  # a move: the old name is gone, the new one was already seen
        self.assertEqual(self.counts(self.ingest().stdout)[2], 0)
        self.assertEqual(self.query('SELECT count(*), sum(input) FROM calls'), [(2, 180)])
        self.assertTrue(copy.exists())

    def test_two_codex_sessions_with_equal_counters_stay_separate(self):
        rows = [token_count('2025-01-01T10:00:00Z', 100, 20, 10)]
        self.codex_file(rows, session_id='sess-1')
        self.codex_file(rows, name='rollout-two', session_id='sess-2')
        self.ingest()
        self.assertEqual(self.query('SELECT count(*) FROM calls'), [(2,)])

    def test_codex_file_without_session_id_still_ingests(self):
        self.codex_file([token_count('2025-01-01T10:00:00Z', 100, 20, 10)])
        self.assertEqual(self.counts(self.ingest().stdout)[2], 1)

    def test_version_1_database_is_migrated_without_doubling_codex_calls(self):
        rows = [token_count('2025-01-01T10:00:00Z', 100, 20, 10), token_count('2025-01-01T10:05:00Z', 250, 70, 30)]
        self.codex_file(rows, session_id='sess-1')
        self.main_file([assistant('2025-01-01T12:00:00Z', 'a')])
        self.ingest()
        # Rewrite the store as a version 1 database: codex ids start with the file name.
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE calls SET call_id = replace(call_id, 'sess-1:', 'rollout-one:') WHERE source = 'codex'")
            conn.execute("UPDATE meta SET value = '1' WHERE key = 'schema_version'")
        copy = self.codex_file(rows, name='rollout-copy', day='2025/02/09', session_id='sess-1')
        self.ingest()
        self.assertEqual(self.query("SELECT count(*) FROM calls WHERE source = 'codex'"), [(2,)])
        self.assertEqual(self.query("SELECT value FROM meta WHERE key = 'schema_version'"), [('2',)])
        self.assertEqual(self.query("SELECT count(*) FROM calls WHERE call_id LIKE 'rollout-%'"), [(0,)])
        self.assertEqual(self.counts(self.ingest().stdout)[2], 0)
        self.assertEqual(self.query('SELECT count(*) FROM calls'), [(3,)])
        copy.unlink()

    def test_version_1_database_with_existing_duplicates_collapses_them(self):
        rows = [token_count('2025-01-01T10:00:00Z', 100, 20, 10)]
        self.codex_file(rows, session_id='sess-1')
        self.codex_file(rows, name='rollout-copy', day='2025/02/09', session_id='sess-1')
        self.ingest()
        with sqlite3.connect(self.db) as conn:
            conn.execute("DELETE FROM calls")
            for stem in ('rollout-one', 'rollout-copy'):
                conn.execute("INSERT INTO calls VALUES ('codex', ?, '2025-01-01T10:00:00Z', '2025-01-01', 'p', ?, 'main', "
                             "'gpt-test-sol', 80, 20, 0, 0, 10)", (f'{stem}:2025-01-01T10:00:00Z:110', stem))
            conn.execute("UPDATE meta SET value = '1' WHERE key = 'schema_version'")
        self.ingest()
        self.assertEqual(self.query('SELECT count(*) FROM calls'), [(1,)])

    def test_deleted_transcript_keeps_its_rows(self):
        path = self.main_file([assistant('2025-01-01T12:00:00Z', 'a')])
        self.ingest()
        path.unlink()
        self.assertEqual(self.counts(self.ingest().stdout), (0, 0, 0, 0))
        self.assertEqual(self.query('SELECT count(*) FROM calls'), [(1,)])
        self.assertEqual(self.query('SELECT count(*) FROM files'), [(1,)])

    def test_malformed_lines_are_counted_not_fatal(self):
        path = self.main_file([assistant('2025-01-01T12:00:00Z', 'a')])
        with path.open('a') as stream:
            stream.write('{"timestamp": "2025-01-01T12:01:00Z", broken\n')
            stream.write(json.dumps(assistant('not a time', 'bad')) + '\n')
            stream.write(json.dumps(assistant('2025-01-01T12:02:00Z', 'b')) + '\n')
        result = self.ingest()
        self.assertEqual(self.counts(result.stdout), (1, 1, 2, 2))
        self.assertIn('malformed rows', result.stdout)

    def test_unreadable_file_is_counted_and_retried(self):
        if os.geteuid() == 0:
            self.skipTest('root can read any file')
        path = self.main_file([assistant('2025-01-01T12:00:00Z', 'a')])
        path.chmod(0)
        try:
            result = self.ingest()
            self.assertEqual(self.counts(result.stdout), (1, 1, 0, 1))
            self.assertEqual(self.query('SELECT count(*) FROM files'), [(0,)])
        finally:
            path.chmod(0o644)
        self.assertEqual(self.counts(self.ingest().stdout), (1, 1, 1, 0))

    def test_privacy_no_message_text_in_database(self):
        self.basic()
        self.ingest()
        self.assertNotIn(b'SECRET_PROMPT', self.db.read_bytes())

    def test_database_mode_is_0600(self):
        self.basic()
        self.ingest()
        self.assertEqual(stat.S_IMODE(self.db.stat().st_mode), 0o600)

    def test_database_location_rules(self):
        self.basic()
        explicit = self.root / 'explicit.db'
        self.ingest('--db', explicit)
        self.assertTrue(explicit.exists())
        self.assertFalse(self.db.exists())
        del self.env['KAIZEN_USAGE_DB']
        self.ingest()
        self.assertTrue((self.config / 'kaizen-usage.db').exists())

    def test_newer_schema_is_refused(self):
        self.basic()
        self.ingest()
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE meta SET value = '99' WHERE key = 'schema_version'")
        for command in (('ingest',), ('status',), ('report',), ('sql', 'select 1')):
            result = self.run_script('usage-db', *command, code=2)
            self.assertIn('schema version 99', result.stderr)
        self.assertNotIn('Traceback', result.stderr)

    def test_foreign_database_is_refused(self):
        self.db.parent.mkdir(parents=True)
        with sqlite3.connect(self.db) as conn:
            conn.execute('CREATE TABLE other (x)')
        result = self.run_script('usage-db', 'ingest', code=2)
        self.assertIn('not a usage-db database', result.stderr)

    def test_foreign_database_is_refused_without_being_modified(self):
        self.db.parent.mkdir(parents=True)
        with sqlite3.connect(self.db) as conn:
            conn.execute('CREATE TABLE other (x)')
        before = self.db.read_bytes()
        self.assertEqual(self.run_script('usage-db', 'ingest', code=2).stdout, '')
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(sorted(p.name for p in self.db.parent.iterdir()), [self.db.name])
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute('PRAGMA journal_mode').fetchone()[0], 'delete')

    def test_file_that_is_not_sqlite_gives_one_line_naming_the_path(self):
        self.db.parent.mkdir(parents=True)
        self.db.write_text('this is not a database, just text ' * 20)
        before = self.db.read_bytes()
        for command in (('ingest',), ('status',), ('report',), ('sql', 'select 1')):
            result = self.run_script('usage-db', *command, code=2)
            lines = result.stderr.strip().splitlines()
            self.assertEqual(len(lines), 1, result.stderr)
            self.assertIn(str(self.db), lines[0])
            self.assertNotIn('Traceback', result.stderr)
        self.assertEqual(self.db.read_bytes(), before)


class PruneTests(UsageDbCase):
    def aged(self):
        today = datetime.now(timezone.utc).date()
        stamp = lambda days: (today - timedelta(days=days)).isoformat() + 'T12:00:00Z'
        self.main_file([assistant(stamp(40), 'old1'), assistant(stamp(35), 'old2'), assistant(stamp(30), 'edge'),
                        assistant(stamp(5), 'new')])
        self.ingest()
        return today

    def prune(self, *args, code=0):
        return self.run_script('usage-db', 'prune', *args, code=code)

    def test_dry_run_reports_rows_and_dates_and_changes_nothing(self):
        today = self.aged()
        before = self.db.read_bytes()
        out = self.prune('--older-than', '30').stdout
        self.assertIn('dry run: would delete 2 calls', out)
        self.assertIn(f'from {today - timedelta(days=40)} to {today - timedelta(days=35)}', out)
        self.assertIn('--apply', out)
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(self.query('SELECT count(*) FROM calls'), [(4,)])

    def test_apply_deletes_older_rows_only_and_vacuums(self):
        self.aged()
        out = self.prune('--older-than', '30', '--apply').stdout
        self.assertIn('deleted 2 calls', out)
        self.assertIn('vacuumed', out)
        self.assertEqual(sorted(r[0] for r in self.query('SELECT call_id FROM calls')), ['edge', 'new'])
        self.assertIn('nothing to prune', self.prune('--older-than', '30', '--apply').stdout)
        self.assertEqual(self.query('PRAGMA integrity_check'), [('ok',)])

    def test_apply_shrinks_the_file(self):
        today = datetime.now(timezone.utc).date()
        self.main_file([assistant((today - timedelta(days=400)).isoformat() + f'T12:{n // 60:02}:{n % 60:02}Z', f'm{n}')
                        for n in range(3000)] + [assistant(today.isoformat() + 'T00:00:00Z', 'keep')])
        self.ingest()
        self.run_script('usage-db', 'sql', 'PRAGMA wal_checkpoint(TRUNCATE)')
        big = self.db.stat().st_size
        out = self.prune('--older-than', '1', '--apply').stdout
        self.assertIn('deleted 3000 calls', out)
        match = re.search(r'vacuumed (\d+) -> (\d+) bytes', out)
        self.assertIsNotNone(match)
        self.assertEqual(int(match.group(1)), big)
        self.assertLess(int(match.group(2)), int(match.group(1)))
        self.assertEqual(int(match.group(2)), self.db.stat().st_size)

    def test_days_below_one_or_not_a_number_are_refused(self):
        self.aged()
        for value in ('0', '-3', 'abc', '1.5'):
            self.assertIn('--older-than', self.prune('--older-than', value, code=2).stderr)
        self.prune(code=2)
        self.assertEqual(self.query('SELECT count(*) FROM calls'), [(4,)])

    def test_missing_database_is_not_created(self):
        for extra in ((), ('--apply',)):
            result = self.prune('--older-than', '30', *extra, code=1)
            self.assertIn('no database at', result.stderr)
        self.assertFalse(self.db.exists())

    def test_nothing_is_pruned_by_ingest_or_report(self):
        self.aged()
        self.ingest()
        self.report()
        self.assertEqual(self.query('SELECT count(*) FROM calls'), [(4,)])


class QueryTests(UsageDbCase):
    def test_status(self):
        missing = self.run_script('usage-db', 'status', code=1)
        self.assertIn('no database', missing.stderr)
        self.assertNotIn('Traceback', missing.stderr)
        self.run_script('usage-db', 'report', code=1)
        self.run_script('usage-db', 'sql', 'select 1', code=1)
        self.basic()
        self.codex_file([token_count('2025-01-03T10:00:00Z', 100, 0, 10)], day='2025/01/03')
        self.ingest()
        text = self.run_script('usage-db', 'status').stdout
        for expected in (str(self.db), 'schema version: 2', 'claude calls: 2', 'codex calls: 1',
                         'first day: 2025-01-01', 'last day: 2025-01-03'):
            self.assertIn(expected, text)
        self.assertRegex(text, r'last ingest: \d{4}-\d\d-\d\dT')

    def test_sql_is_read_only(self):
        self.basic()
        self.ingest()
        for statement in ("INSERT INTO calls (source, call_id, ts, day) VALUES ('x', 'y', 'z', 'w')",
                          'DELETE FROM calls', 'DROP TABLE calls', "ATTACH 'file:" + str(self.root / 'x.db') + "?mode=rwc' AS x",
                          'SELECT 1; SELECT 2', 'SELEC nonsense'):
            result = self.run_script('usage-db', 'sql', statement, code=2)
            self.assertEqual(len(result.stderr.strip().splitlines()), 1, result.stderr)
        self.assertEqual(self.query('SELECT count(*) FROM calls'), [(2,)])
        self.assertFalse((self.root / 'x.db').exists())
        out = self.run_script('usage-db', 'sql', 'SELECT call_id, input FROM calls ORDER BY call_id', '--format', 'csv').stdout
        self.assertEqual(out.splitlines(), ['call_id,input', 'a,100', 'b,50'])
        rows = json.loads(self.run_script('usage-db', 'sql', 'SELECT sum(output) AS n FROM calls', '--format', 'json').stdout)
        self.assertEqual(rows, [dict(n=15)])
        table = self.run_script('usage-db', 'sql', 'SELECT day, count(*) AS n FROM calls GROUP BY day').stdout.splitlines()
        self.assertEqual(table[0].split(), ['day', 'n'])
        self.assertEqual(len(table), 3)

    def test_sql_connection_is_read_only_at_the_file_level(self):
        # Even with the query_only pragma switched off, the file refuses writes.
        self.basic()
        self.ingest()
        loader = SourceFileLoader('usage_db_under_test', str(SCRIPTS / 'usage-db'))
        module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
        loader.exec_module(module)
        conn = module.open_read(self.db)
        self.addCleanup(conn.close)
        conn.execute('PRAGMA query_only = OFF')
        with self.assertRaisesRegex(sqlite3.OperationalError, 'readonly database'):
            conn.execute("INSERT INTO calls (source, call_id, ts, day) VALUES ('x', 'y', 'z', 'w')")
        with self.assertRaisesRegex(sqlite3.OperationalError, 'readonly database'):
            conn.execute('CREATE TABLE sneaky (x)')
        self.assertEqual(self.query('SELECT count(*) FROM calls'), [(2,)])

    def fixtures(self):
        self.main_file([
            assistant('2025-01-01T12:00:00Z', 'a', cwd=self.cwd,
                      usage=dict(input_tokens=100, output_tokens=10, cache_read_input_tokens=40)),
            assistant('2025-01-01T13:00:00Z', 'b', cwd=self.cwd, model='claude-big-test',
                      usage=dict(input_tokens=700, output_tokens=20, cache_creation_input_tokens=300,
                                 cache_creation=dict(ephemeral_1h_input_tokens=100))),
            assistant('2025-01-02T13:00:00Z', 'c', cwd=self.cwd, model='claude-big-test',
                      usage=dict(input_tokens=1500, output_tokens=20, cache_read_input_tokens=700)),
            assistant('2025-01-02T14:00:00Z', 'd', cwd=self.cwd, model='claude-mystery',
                      usage=dict(input_tokens=11, output_tokens=2)),
            assistant('2025-01-03T14:00:00Z', 'e', cwd=self.cwd)])
        sub = self.config / 'projects/alpha/main/subagents/w.jsonl'
        jsonl(sub, [assistant('2025-01-02T15:00:00Z', 'w')])
        write(sub.with_suffix('.meta.json'), json.dumps(dict(agentType='worker')))
        self.main_file([assistant('2025-01-02T12:00:00Z', 'o')], name='o', project='betafolder')
        self.codex_file([token_count('2024-12-31T12:00:00Z', 1000, 0, 100),
                         token_count('2025-01-01T12:00:00Z', 1400, 200, 150),
                         token_count('2025-01-02T12:00:00Z', 1500, 200, 160)])
        self.codex_file([token_count('2025-01-02T12:00:00Z', 100, 0, 10)], name='rollout-two', day='2025/01/02')
        self.ingest()

    def test_report_matches_usage_series_for_the_same_window(self):
        self.fixtures()
        for window in (('2025-01-01', '2025-01-03'), ('2025-01-02', '2025-01-02')):
            since, until = window
            self.run_script('usage-series', '--since', since, '--until', until, '--pricing', self.prices,
                            '--out', self.root / 'series')
            with (self.root / 'series' / 'daily.csv').open() as stream:
                series = list(csv.DictReader(stream))
            total = lambda key: sum(float(r[key]) for r in series)
            claude = self.report('--since', since, '--until', until, '--source', 'claude')['total']
            both = self.report('--since', since, '--until', until)['total']
            self.assertEqual(claude['input'] + claude['cache_read'] + claude['cache_write'], total('claude_context_tokens'))
            self.assertEqual(claude['output'], total('claude_output_tokens'))
            self.assertAlmostEqual(both['cost_usd'], total('cost_total'), places=7)
            self.assertEqual(both['unpriced_calls'], total('unpriced_calls'))
            self.assertGreater(both['cost_usd'], 0)
        # Fixture sanity: the unpriced model and the threshold model are really in the window.
        self.assertEqual(self.report('--since', '2025-01-02', '--until', '2025-01-02')['total']['unpriced_calls'], 1)

    def test_report_day_rows_and_total(self):
        self.fixtures()
        data = self.report('--source', 'claude')
        self.assertEqual([r['day'] for r in data['rows']], ['2025-01-01', '2025-01-02', '2025-01-03'])
        first = data['rows'][0]
        self.assertEqual((first['calls'], first['input'], first['cache_read'], first['cache_write'], first['output']),
                         (2, 800, 40, 300, 30))
        # a: 100*1 + 10*2 + 40*0.1; b is at the 1000-token threshold: 700*3 + 20*6 + 200*3.75 + 100*6
        self.assertAlmostEqual(first['cost_usd'], (100 + 20 + 4) / 1e6 + (2100 + 120 + 750 + 600) / 1e6, places=8)
        self.assertEqual(data['total']['calls'], sum(r['calls'] for r in data['rows']))
        self.assertNotIn('key', data['total'])

    def test_each_group_key_and_format(self):
        self.fixtures()
        expected = dict(day=4, model=4, project=2, agent=2, session=4, source=2)
        for by, count in expected.items():
            data = self.report('--by', by)
            self.assertEqual(len(data['rows']), count, by)
            self.assertEqual(sum(r['calls'] for r in data['rows']), data['total']['calls'], by)
            self.assertAlmostEqual(sum(r['cost_usd'] for r in data['rows']), data['total']['cost_usd'], places=7)
            self.assertIn(by, data['rows'][0])
            text = self.run_script('usage-db', 'report', '--pricing', self.prices, '--by', by, '--format', 'csv').stdout
            lines = list(csv.reader(io.StringIO(text)))
            self.assertEqual(lines[0], [by, 'calls', 'input', 'cache_read', 'cache_write', 'output', 'cost_usd', 'unpriced_calls'])
            self.assertEqual(len(lines), count + 2)
            self.assertEqual(lines[-1][0], 'total')
            table = self.run_script('usage-db', 'report', '--pricing', self.prices, '--by', by).stdout.splitlines()
            self.assertEqual(table[0].split(), lines[0])
            self.assertEqual(len(table), count + 2)
        by_agent = {r['agent']: r['calls'] for r in self.report('--by', 'agent')['rows']}
        self.assertEqual(by_agent, dict(main=10, worker=1))
        by_source = {r['source']: r['calls'] for r in self.report('--by', 'source')['rows']}
        self.assertEqual(by_source, dict(claude=7, codex=4))
        by_model = {r['model']: r for r in self.report('--by', 'model')['rows']}
        self.assertEqual(by_model['claude-mystery']['unpriced_calls'], 1)
        self.assertEqual(by_model['claude-mystery']['cost_usd'], 0)

    def test_report_filters(self):
        self.fixtures()
        self.assertEqual(self.report('--project', 'BetaFolder')['total']['calls'], 1)
        self.assertEqual(self.report('--project', 'project_alpha')['total']['calls'], 10)
        self.assertEqual(self.report('--source', 'codex', '--since', '2025-01-02')['total']['calls'], 2)
        self.assertEqual(self.report('--until', '2025-01-01')['total']['calls'], 4)
        self.assertEqual(self.report('--since', '2030-01-01')['total']['calls'], 0)
        self.run_script('usage-db', 'report', '--since', '2025-01-03', '--until', '2025-01-01', code=2)
        self.run_script('usage-db', 'report', '--since', 'yesterday', code=2)

    def test_repricing_applies_to_old_rows(self):
        self.fixtures()
        before = self.report('--source', 'claude')['total']['cost_usd']
        doubled = json.loads(self.prices.read_text())
        for rates in doubled['models'].values():
            for key in ('input', 'output'):
                rates[key] *= 2
        write(self.prices, json.dumps(doubled))
        self.assertGreater(self.report('--source', 'claude')['total']['cost_usd'], before)
        missing = self.run_script('usage-db', 'report', '--pricing', self.root / 'none.json', '--format', 'json')
        data = json.loads(missing.stdout)
        self.assertEqual(data['total']['cost_usd'], 0)
        self.assertEqual(data['total']['unpriced_calls'], data['total']['calls'])
        self.assertIn('Pricing file unavailable', missing.stderr)

    def test_help_for_every_command_starts_no_scan(self):
        for command in ((), ('ingest',), ('status',), ('report',), ('sql',)):
            result = self.run_script('usage-db', *command, '--help')
            self.assertIn('usage:', result.stdout)
        self.assertFalse(self.db.exists())
        self.run_script('usage-db', code=2)
        self.run_script('usage-db', 'bogus', code=2)

    def test_script_is_executable(self):
        self.assertTrue(os.access(SCRIPTS / 'usage-db', os.X_OK))
        result = subprocess.run([sys.executable, str(SCRIPTS / 'usage-db'), '--help'], env=self.env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)


if __name__ == '__main__':
    import unittest
    unittest.main()
