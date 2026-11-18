"""Backtest usage-db guard with sparse, synthetic SQLite call history."""
from contextlib import closing
from datetime import date, timedelta
import json
import importlib.util
from importlib.machinery import SourceFileLoader
import io
from contextlib import redirect_stdout
import subprocess
import time
from unittest.mock import patch
import sqlite3

from test_hooks import ROOT, run_raw
from test_usage_db import PRICES, UsageDbCase


class UsageGuardTests(UsageDbCase):
    def setUp(self):
        super().setUp()
        self.db = self.config / 'kaizen-usage.db'
        self.env['KAIZEN_USAGE_DB'] = ''
        self.ingest()
        prices = {**PRICES['models'], 'claude-sonnet-test': PRICES['models']['claude-opus-test']}
        self.prices.write_text(json.dumps(dict(models=prices)))

    def call(self, index, ident, input_=10000, output=0, write=0, subagent=0, session='main',
             time='00:00:00', model='claude-opus-test', source='claude'):
        day = (date(2025, 1, 1) + timedelta(days=index * 2)).isoformat()
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute('INSERT INTO calls (source, call_id, ts, day, session, agent, model, is_subagent, '
                         'input, cache_write_5m, output) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                         (source, f'{index}-{ident}', f'{day}T{time}Z', day, session,
                          'worker' if subagent else 'main', model, subagent, input_, write, output))

    def guard(self, *args):
        return self.run_script('usage-db', 'guard', '--pricing', self.prices, *args).stdout.splitlines()

    def guard_module(self):
        loader = SourceFileLoader('guard_equivalence', str(ROOT / 'scripts/usage-db'))
        module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
        loader.exec_module(module)
        return module

    def compare_unrestricted(self, *extra):
        module = self.guard_module()
        args = module.build_parser().parse_args(['guard', '--db', str(self.db), '--pricing', str(self.prices), *extra])
        output = io.StringIO()
        original = module.guard_days
        with redirect_stdout(output), patch.object(module, 'guard_days',
                                                 side_effect=lambda conn, args, bound=None: original(conn, args)):
            module.guard(args)
        self.assertEqual(self.guard(*extra), output.getvalue().splitlines())

    def findings(self, *args):
        return [line for line in self.guard(*args) if line.startswith('REGRESSION ')]

    def test_sparse_history_and_zero_cost(self):
        for i in range(16):
            self.call(i, 'main', input_=0)
            self.call(i, 'agent', input_=0, subagent=1)
        self.assertIn('insufficient data main_avg_context (16/17 active UTC days)', self.guard())
        self.call(16, 'main', input_=0)
        lines = self.guard()
        self.assertEqual(lines, ['insufficient data agent_cost_share.worker (0/17 active UTC days)',
                                 'insufficient data full_rewrite_share (0/17 active UTC days)'])
        self.compare_unrestricted()

    def test_active_day_windows_strict_boundary_and_unscaled_mad(self):
        for i in range(31):
            context = 50000 if i < 14 else (9000 + 2000 * (i % 2) if i < 28 else 13000)
            self.call(i, 'main', input_=context)
        self.call(30, 'codex', input_=90000, source='codex', subagent=None)
        self.assertEqual(self.findings(), [])
        self.assertEqual(self.findings('--mad-multiplier', '2'),
                         ['REGRESSION main_avg_context 13000 vs 10000'])
        self.call(30, 'main-extra', input_=13600)
        before = self.db.read_bytes()
        self.assertEqual(self.findings(), ['REGRESSION main_avg_context 13100 vs 10000'])
        self.assertEqual(self.db.read_bytes(), before)

    def test_backtest_one_spike_then_sustained_drift(self):
        for i in range(17):
            self.call(i, 'main', input_=10000, output=100)
            self.call(i, 'write', input_=9000, write=1000, output=100, time='00:00:00.001')
            self.call(i, 'agent', input_=1000, output=100, subagent=1, model='claude-sonnet-test')
        self.assertEqual(self.guard(), ['No regressions'])
        self.call(16, 'outlier', input_=20000)
        self.assertEqual(self.guard(), ['No regressions'])
        for i in range(14, 17):
            for j in range(3):
                self.call(i, f'expensive-{j}', input_=10000, output=800, subagent=1)
            self.call(i, 'rewrite', input_=1000, write=9000, time='00:00:01')
        findings = self.findings()
        self.assertEqual([line.split()[1] for line in findings],
                         ['full_rewrite_share', 'agent_cost_share.worker', 'output_per_call', 'expensive_agent_calls'])
        self.assertIn('REGRESSION expensive_agent_calls 3 vs 0', findings)
        self.assertIn('REGRESSION full_rewrite_share 0.5 vs 0', findings)
        self.assertEqual(self.findings('--minimum', 'expensive_agent_calls=3'), findings[:-1])
        self.assertEqual(self.findings('--minimum', 'expensive_agent_calls=0.3'), findings[-1:] + findings[:-1])

    def test_cost_share_skips_unpriced_days_and_needs_own_history(self):
        for i in range(19):
            self.call(i, 'main')
            if i > 0:
                self.call(i, 'agent', subagent=1, model='claude-unknown' if i == 16 else 'claude-opus-test')
            if i == 18:
                self.call(i, 'unpriced-main', model='claude-unknown')
        self.assertIn('insufficient data agent_cost_share.worker (16/17 active UTC days)', self.guard())
        self.prices.unlink()
        self.assertIn('insufficient data agent_cost_share.worker (0/17 active UTC days)', self.guard())

    def test_rewrites_use_only_known_main_gaps_in_utc_order(self):
        self.call(0, 'predecessor', session='spanning')
        for i in range(1, 18):
            # Exact second precedes the fractional one. The first session call is excluded.
            self.call(i, 'first', input_=0, write=10000, session=f'session-{i}')
            self.call(i, 'second', input_=10000, write=1000, session=f'session-{i}', time='00:00:00.001')
            self.call(i, 'subagent', input_=0, write=10000, subagent=1)
        for i in range(15, 18):
            self.call(i, 'cross-day', input_=2000, write=8000, session='spanning')
        self.assertEqual(self.findings(), ['REGRESSION full_rewrite_share 0.5 vs 0'])
        self.compare_unrestricted()

    def test_bounded_rewrites_keep_only_needed_predecessors(self):
        self.call(0, 'predecessor', session='spanning')
        self.call(1, 'first-write', session='spanning', input_=0, write=10000)
        self.call(1, 'new-session', session='new', input_=0, write=10000)
        self.call(1, 'second-write', session='new', time='00:00:00.001', write=1000)
        self.call(2, 'no-write', session='another')
        self.call(2, 'later-write', session='another', time='00:00:01', write=1000)
        module = self.guard_module()
        with closing(sqlite3.connect(self.db)) as conn:
            # The first spanning write counts; a new session's first write does not.
            self.assertEqual(module.guard_rewrites(conn, 'is_subagent', '2025-01-03'),
                             {'2025-01-03': 0.5, '2025-01-05': 0.0})
            self.assertEqual(module.guard_rewrites(conn, 'is_subagent', '2025-01-05'),
                             {'2025-01-05': 0.0})

    def test_aliases_and_unknown_origin(self):
        prices = json.loads(self.prices.read_text())
        prices['aliases'] = {'opus': 'claude-opus-test', 'fable': 'claude-opus-test'}
        self.prices.write_text(json.dumps(prices))
        for i in range(17):
            self.call(i, 'main', input_=10000 if i < 14 else 13000)
            self.call(i, 'unknown', input_=10000, subagent=None)
        self.assertIn('REGRESSION main_avg_context 13000 vs 10000', self.findings())
        with sqlite3.connect(self.db) as conn:
            conn.execute("DELETE FROM calls WHERE is_subagent IS NULL")
        for i in range(14, 17):
            for j, model in enumerate(('opus', 'fable', 'opus')):
                self.call(i, f'alias-{j}', subagent=1, model=model)
        self.assertIn('REGRESSION expensive_agent_calls 3 vs 0', self.findings())

    def test_cost_share_uses_unrounded_values_even_for_small_increases(self):
        for i in range(17):
            self.call(i, 'main', input_=100000000)
            self.call(i, 'agent', input_=100000000 + (i >= 14), subagent=1)
        self.assertTrue(any('agent_cost_share' in line for line in self.findings(
            '--relative-threshold', '0', '--mad-multiplier', '0', '--minimum', 'agent_cost_share=0')))

    def test_cost_share_does_not_cross_threshold_due_to_rounding(self):
        for i in range(17):
            self.call(i, 'main', input_=66666651 if i < 14 else 60000000)
            self.call(i, 'agent', input_=33333349 if i < 14 else 40000000, subagent=1)
        self.assertFalse(any('agent_cost_share' in line for line in self.findings()))

    def test_expensive_model_uses_name_before_shared_price_key(self):
        self.prices.write_text(json.dumps(dict(models={'shared': PRICES['models']['claude-opus-test']},
                                               aliases={'claude-opus-test': 'shared',
                                                        'claude-sonnet-test': 'shared'})))
        for i in range(17):
            self.call(i, 'main', model='claude-sonnet-test')
            self.call(i, 'cheap', subagent=1, model='claude-sonnet-test')
            if i >= 14:
                for j in range(3):
                    self.call(i, f'expensive-{j}', subagent=1)
        self.assertIn('REGRESSION expensive_agent_calls 3 vs 0', self.findings())

    def test_predecessor_query_filters_unrelated_sessions(self):
        self.call(0, 'predecessor', session='spanning')
        self.call(1, 'write', session='spanning', input_=0, write=10000)
        with sqlite3.connect(self.db) as conn:
            conn.executemany(
                "INSERT INTO calls (source, call_id, ts, day, session, is_subagent) VALUES (?, ?, ?, ?, ?, 0)",
                (('claude', f'old-{i}', '2024-01-01T00:00:00Z', '2024-01-01', f'other-{i}')
                 for i in range(100000)))
            steps = [0]
            def progress():
                steps[0] += 1000
                return 0
            conn.set_progress_handler(progress, 1000)
            result = self.guard_module().guard_rewrites(conn, 'is_subagent', '2025-01-03')
        self.assertEqual(result, {'2025-01-03': 1.0})
        self.assertLess(steps[0], 1500000)

    def test_bounded_matches_unrestricted_sparse_families(self):
        for i in range(40):
            self.call(i, 'main', input_=12000 if i > 35 else 10000, source='codex', subagent=None)
            if i % 3 != 0:
                self.call(i, 'claude', session='spanning')
                self.call(i, 'write', session='spanning', time='00:00:01', write=1000)
            if i % 2 == 0:
                self.call(i, 'agent', subagent=1)
            if i < 4:
                self.call(i, 'old-agent', subagent=1)
                with sqlite3.connect(self.db) as conn:
                    conn.execute("UPDATE calls SET agent='oldworker' WHERE call_id=?", (f'{i}-old-agent',))
            if i % 7 == 0:
                self.call(i, 'unknown', model='claude-unknown')
        self.compare_unrestricted()
        self.compare_unrestricted('--minimum', 'output_per_call=0')

    def test_large_database_guard_speed(self):
        start = time.monotonic()
        def rows():
            for i in range(200000):
                day = (date(2025, 1, 1) + timedelta(days=i % 60)).isoformat()
                agent = (i // 60) % 10 == 0
                yield ('claude', str(i), day + 'T12:00:00Z', day, 'session-' + str(i % 100),
                       'worker' if agent else 'main', 'claude-opus-test', int(agent), 10000,
                       100 if (i // 60) % 100 == 1 else 0, 1000 if i % 60 >= 57 else 10)
        with sqlite3.connect(self.db) as conn:
            conn.executemany('INSERT INTO calls (source, call_id, ts, day, session, agent, model, is_subagent, '
                             'input, cache_write_5m, output) VALUES (?,?,?,?,?,?,?,?,?,?,?)', rows())
            for i in range(5):
                day = (date(2025, 3, 1) - timedelta(days=i * 75)).isoformat()
                conn.execute("INSERT INTO calls (source, call_id, ts, day, session, agent, model, is_subagent, input) "
                             "VALUES ('claude', ?, ?, ?, 'sparse', 'sparse', 'claude-opus-test', 1, 1000)",
                             (f'sparse-{i}', day + 'T12:00:00Z', day))
        if time.monotonic() - start > 20:
            self.skipTest('building the synthetic database took over 20 seconds')
        start = time.monotonic()
        result = subprocess.run([str(ROOT / 'scripts/usage-db'), 'guard', '--db', str(self.db),
                                 '--pricing', str(self.prices)], capture_output=True, text=True)
        elapsed = time.monotonic() - start
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('REGRESSION output_per_call', result.stdout)
        self.assertIn('insufficient data agent_cost_share.sparse', result.stdout)
        self.assertLess(elapsed, 1.5,  # hook deadline is 2 s
                        f'guard took {elapsed:.3f} seconds')

    def test_rejects_nonfinite_thresholds(self):
        for args in (('--relative-threshold', 'nan'), ('--mad-multiplier', '-1'),
                     ('--minimum', 'output_per_call=inf')):
            with self.subTest(args=args):
                self.run_script('usage-db', 'guard', *args, code=2)

    def test_hook_reads_the_default_database_and_emits_one_finding(self):
        (self.work / 'docs/kaizen').mkdir(parents=True)
        for i in range(17):
            self.call(i, 'main', input_=10000 if i < 14 else 13000, model='claude-opus-4')
        env = {**self.env, 'CLAUDE_PLUGIN_ROOT': str(ROOT), 'AUDIT_DIR': str(self.root / 'audits')}
        first = run_raw('audit-notice.sh', {'cwd': str(self.work)}, env)
        first.check_returncode()
        self.assertEqual(json.loads(first.stdout)['hookSpecificOutput']['additionalContext'],
                         'REGRESSION main_avg_context 13000 vs 10000')
        second = run_raw('audit-notice.sh', {'cwd': str(self.work)}, env)
        second.check_returncode()
        self.assertEqual(json.loads(second.stdout), {})
