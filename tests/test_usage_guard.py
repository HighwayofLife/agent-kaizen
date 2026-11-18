"""Backtest usage-db guard with sparse, synthetic SQLite call history."""
from contextlib import closing
from datetime import date, timedelta
import json
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
