import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/packet-report'
FIXTURE = ROOT / 'tests/fixtures/packets.jsonl'


class PacketReportTests(unittest.TestCase):
    def run_report(self, *args, config=None):
        env = dict(os.environ, CLAUDE_CONFIG_DIR=str(config or '/nonexistent'))
        return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], cwd=ROOT,
                              env=env, text=True, capture_output=True)

    def test_fixture_proposals_and_keys(self):
        result = self.run_report('--packets', FIXTURE, '--json')
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(set(data), {'groups', 'area_groups', 'totals', 'fix_origins', 'proposals', 'escalations', 'dispatch_models_coverage', 'unknown_models', 'data_coverage', 'landed_failing', 'review_economics', 'rule', 'disclaimer'})
        self.assertTrue(any(p['model'] == 'sonnet' and p['direction'] == 'UP' for p in data['proposals']))
        self.assertIn({'model': 'opus', 'effort': 'high', 'direction': 'DOWN'}, data['proposals'])
        self.assertIn('too few', self.run_report('--packets', FIXTURE, '--since', '2026-02-01').stdout)
        self.assertIsNone(data['groups'][0]['median_wall_s'])

    def economics_report(self, fix_changes=None, extra=(), flags=()):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'rows'
            rows = [dict(ts='2026-01-02T00:00:00Z', id=str(i), model='gpt-6.1-terra',
                         effort='high', status='CODEX FAILED', merge_sha='abc') for i in range(8)]
            fix = dict(ts='2026-01-01T00:00:00Z', id='fix', model='terra', effort='high',
                       fix_origin='review', fixes=['0'], lines=0, tokens_in=1, tokens_out=0,
                       review_severities=[])
            if fix_changes is not None:
                for key, value in fix_changes.items():
                    if value == 'DELETE':
                        fix.pop(key, None)
                    else:
                        fix[key] = value
            rows.extend([fix, *extra])
            path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
            args = ('--packets', path, '--ladder', 'terra high', '--since', '2026-01-02', *flags)
            result = self.run_report(*args, '--json')
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout), self.run_report(*args).stdout

    def test_hold_complete_and_alias_outside_filter(self):
        data, output = self.economics_report()
        proposal = data['proposals'][0]
        self.assertEqual(proposal['direction'], 'HOLD')
        self.assertTrue(proposal['fix_evidence']['small'])
        self.assertIn(proposal['reason'], output)
        self.assertIn('100 lines, 4000000 tokens', output)
        self.assertLess(output.index('Review economics'), output.index('Calibration proposals'))

    def assert_blocked(self, changes, reason):
        data, _ = self.economics_report(changes)
        self.assertEqual(data['proposals'][0]['direction'], 'UP')
        self.assertIn(reason, data['proposals'][0]['hold_blocked'])

    def test_zero_input_blocks_hold(self):
        self.assert_blocked({'tokens_in': 0}, 'unknown evidence: fix')

    def test_missing_lines_blocks_hold(self):
        self.assert_blocked({'lines': 'DELETE'}, 'unknown evidence: fix')

    def test_missing_output_blocks_hold(self):
        self.assert_blocked({'tokens_out': 'DELETE'}, 'unknown evidence: fix')

    def test_threshold_blocks_hold(self):
        self.assert_blocked({'lines': 100}, 'fix not small: fix')
        self.assert_blocked({'tokens_in': 4000000}, 'fix not small: fix')

    def test_no_attributed_fix_blocks_hold(self):
        self.assert_blocked({'fixes': []}, 'no attributed fixes')

    def test_custom_thresholds_and_invalid_flags(self):
        data, _ = self.economics_report({'lines': 100, 'tokens_in': 4000000},
                                        flags=('--small-fix-lines', '101', '--small-fix-tokens', '4000001'))
        self.assertEqual(data['proposals'][0]['direction'], 'HOLD')
        for flag in ('--small-fix-lines', '--small-fix-tokens'):
            for value in ('-1', 'bad'):
                self.assertEqual(self.run_report(flag, value).returncode, 2)

    def test_review_economics_and_severity(self):
        base = dict(ts='2026-01-02T00:00:00Z', model='sol', effort='low', fix_origin='review')
        extra = [dict(base, id='f1', fixes=['fix', 'f1', 'missing'], review_severities=[]),
                 dict(base, id='f2', fixes=['fix', 'f1'], review_severities=['MUST-FIX', 'NIT']),
                 dict(base, id='f3', fixes=[], review_severities=None),
                 dict(base, id='f4', fixes=[])]
        data, _ = self.economics_report(extra=extra)
        econ = data['review_economics']
        self.assertEqual((econ['landed'], econ['fix_packets'], econ['fix_per_landed']), (8, 4, .5))
        self.assertEqual(econ['fix_of_fix'], dict(count=2, rate=.5, unknown_references=1))
        self.assertEqual(econ['no_must_fix'], dict(count=1, ids=['f1']))
        self.assertEqual(econ['severity_coverage'], dict(known=2, unknown=2, unknown_ids=['f3', 'f4']))
        empty = json.loads(self.run_report('--packets', '/nonexistent', '--json').stdout)['review_economics']
        self.assertIsNone(empty['fix_per_landed'])
        self.assertIsNone(empty['fix_of_fix']['rate'])

    def test_dates_and_fixes(self):
        result = self.run_report('--packets', FIXTURE, '--since', '2026-01-01', '--until', '2026-01-02', '--json')
        data = json.loads(result.stdout)
        self.assertEqual(data['totals']['packets'], 2)
        self.assertEqual(next(g for g in data['groups'] if g['model'] == 'sonnet')['fix_rate'], 1)

    def test_malformed_missing_invalid_and_self_fix(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'rows'
            path.write_text(json.dumps(dict(ts='2026-01-01T00:00:00Z', id='a', model='haiku', effort='low', fixes=['a'])) + '\n{broken\n')
            result = self.run_report('--packets', path, '--json')
            self.assertEqual(json.loads(result.stdout)['groups'][0]['fix_rate'], 0)
            self.assertIn('skipped 1 malformed rows', result.stderr)
            self.assertIn('No packet data yet', self.run_report('--packets', path.parent / 'missing').stdout)
            self.assertEqual(self.run_report('--since', 'bad').returncode, 2)
            self.assertEqual(self.run_report('--packets', path.parent).returncode, 2)

    def test_until_markdown_normalization_and_audit_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'packets.jsonl'
            rows = [dict(ts='2026-01-01T00:00:00Z', id=str(i), model='gpt-6.1-terra',
                         effort='high', status='DONE') for i in range(8)]
            rows.append(dict(ts='2026-01-02T00:00:00Z', id='audit', model='other',
                             effort='high', fixes=['0'], fix_origin='final-audit'))
            path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
            result = self.run_report('--packets', path, '--until', '2026-01-02',
                                     '--ladder', 'terra high', '--json')
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(data['totals']['packets'], 8)
            self.assertEqual(data['groups'][0]['model'], 'terra')
            self.assertEqual(data['groups'][0]['fix_rate'], 1 / 8)
            self.assertFalse(any(p['direction'] == 'DOWN' for p in data['proposals']))
            rendered = self.run_report('--packets', path, '--markdown')
            self.assertEqual(rendered.returncode, 0, rendered.stderr)
            self.assertIn('| model effort / area | n |', rendered.stdout)
            self.assertIn('| --- | ---:', rendered.stdout)

    def test_escalations_and_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'packets.jsonl'
            base = dict(ts='2026-01-01T00:00:00Z', model='sol', effort='high')
            terra = dict(model='terra', effort='high', rounds=1)
            sol = dict(model='sol', effort='high', rounds=0)
            histories = [[terra, sol], [terra, terra], None, 'invalid',
                         [dict(model='terra', effort='high', rounds=True)], []]
            rows = [dict(base, id=str(i), dispatch_models=history)
                    for i, history in enumerate(histories)]
            rows.append(dict(base, id='missing'))
            path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
            result = self.run_report('--packets', path, '--json')
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(data['escalations'], {'count': 1, 'pairs': {'terra->sol': 1}})
            self.assertEqual(data['dispatch_models_coverage'], {'n_with': 2, 'n_total': 7})
            self.assertEqual(data['totals']['packets'], 7)
            for option in ((), ('--markdown',)):
                output = self.run_report('--packets', path, *option).stdout
                self.assertIn('Escalations', output)
                self.assertIn('terra->sol: 1', output)
                self.assertIn('2/7', output)

    def test_escalation_path_names_and_float_rounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'packets.jsonl'
            base = dict(ts='2026-01-01T00:00:00Z', model='terra', effort='high')

            def step(model, rounds=0):
                return dict(model=model, effort='high', rounds=rounds)

            histories = [[step('terra'), step('sol'), step('terra')],
                         [step('gpt-6.1-terra'), step('sol')],
                         [step('terra', 1.0), step('sol')],
                         [step('terra', 1.5), step('sol')],
                         [step('terra', float('nan')), step('sol')]]
            rows = [dict(base, id=str(i), dispatch_models=h) for i, h in enumerate(histories)]
            path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
            data = json.loads(self.run_report('--packets', path, '--ladder', 'terra high,sol high', '--json').stdout)
            self.assertEqual(data['escalations'], {'count': 3, 'pairs': {
                'terra->sol': 2, 'terra->sol->terra': 1}})
            self.assertEqual(data['dispatch_models_coverage'], {'n_with': 3, 'n_total': 5})

    def test_effort_only_escalation_is_counted_and_labelled(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'packets.jsonl'
            base = dict(ts='2026-01-01T00:00:00Z', model='terra', effort='medium')

            def step(model, effort):
                return dict(model=model, effort=effort, rounds=0)

            histories = [[step('terra', 'medium'), step('terra', 'high')],
                         [step('terra', 'medium'), step('terra', 'high')],
                         [step('terra', 'high'), step('sol', 'high')],
                         [step('terra', 'medium'), step('sol', 'high')],
                         [step('terra', 'high'), step('terra', 'high')]]
            rows = [dict(base, id=str(i), dispatch_models=h) for i, h in enumerate(histories)]
            path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
            data = json.loads(self.run_report('--packets', path, '--json').stdout)
            self.assertEqual(data['escalations'], {'count': 4, 'pairs': {
                'terra:medium->terra:high': 2, 'terra:medium->sol:high': 1, 'terra->sol': 1}})
            self.assertIn('terra:medium->terra:high: 2', self.run_report('--packets', path).stdout)

    def test_data_quality_aliases_and_filters(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'packets.jsonl'
            base = dict(ts='2026-01-01T00:00:00Z', effort='high')
            rows = [dict(base, id='a', model='gpt-6.1-terra', tokens_in=0,
                         tokens_out=0, cost=0, status='CHECKS FAILING', merge_sha='abc',
                         dispatch_models=[dict(model='gpt-6.1-terra', effort='high', rounds=0),
                                          dict(model='gpt-6.2-sol', effort='high', rounds=1)]),
                    dict(base, id='b', model='gpt-6.2-sol', tokens_in=None,
                         tokens_out=True, cost=-1, status='CHECKS FAILING'),
                    dict(base, id='c', model='claude-sonnet-4-5', tokens_in=4,
                         tokens_out=2, cost=1, status='DONE', merge_sha='abc'),
                    dict(base, id='d', model='unknown', tokens_in='4', tokens_out=-1, cost='1'),
                    dict(base, id='e', model='other', tokens_in=True),
                    dict(base, id='f', model='terra-sol'),
                    dict(base, id='g', model='UNKNOWN', ts='2026-01-02T00:00:00Z')]
            path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
            for ladder in ('terra,sol,sonnet', 'opus'):
                args = ('--packets', path, '--ladder', ladder, '--until', '2026-01-02')
                result = self.run_report(*args, '--json')
                self.assertEqual(result.returncode, 0, result.stderr)
                data = json.loads(result.stdout)
                self.assertEqual({g['model'] for g in data['groups']},
                                 {'terra', 'sol', 'sonnet', 'unknown', 'other', 'terra-sol'})
                self.assertEqual(data['escalations']['pairs'], {'terra->sol': 1})
                self.assertEqual(data['unknown_models'], {'count': 1, 'ids': ['d']})
                self.assertEqual(data['landed_failing'], {'count': 1, 'ids': ['a']})
                self.assertEqual(data['data_coverage']['tokens_in'],
                                 dict(known=1, zero=1, missing=4, zero_ids=['a'],
                                      missing_ids=['b', 'd', 'e', 'f']))
                self.assertEqual(data['data_coverage']['tokens_out']['known'], 2)
                self.assertEqual(data['data_coverage']['cost']['missing'], 4)
                for option in ((), ('--markdown',)):
                    output = self.run_report(*args, *option).stdout
                    self.assertLess(output.index('Data quality'), output.index('Calibration proposals'))
                    self.assertIn('Landed with failing checks: 1; ids: a', output)
            data = json.loads(self.run_report('--packets', path, '--since', '2026-01-02', '--json').stdout)
            self.assertEqual(data['unknown_models']['ids'], ['g'])
            self.assertEqual(data['data_coverage']['rows'], 1)
            self.assertEqual(data['landed_failing']['count'], 0)

    def test_quality_ids_are_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'packets.jsonl'
            rows = [dict(ts='2026-01-01T00:00:00Z', id=str(i), model='unknown', effort='high')
                    for i in range(12)]
            path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
            output = self.run_report('--packets', path).stdout
            self.assertIn('... 2 more', output)

    def test_config_dir_expands_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / 'cfg').mkdir()
            (home / 'cfg/agent-kaizen.json').write_text(json.dumps({'calibrationLadder': 5}))
            env = dict(os.environ, HOME=str(home), CLAUDE_CONFIG_DIR='~/cfg')
            result = subprocess.run([sys.executable, str(SCRIPT), '--packets', str(FIXTURE)],
                                    cwd=ROOT, env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 2, result.stdout)
            self.assertIn('ladder must be', result.stderr)

    def test_unreadable_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'packets.jsonl'
            path.write_text('{}\n')
            path.chmod(0)
            if os.access(path, os.R_OK):
                self.skipTest('current user can read chmod 000 files')
            result = self.run_report('--packets', path)
            self.assertEqual(result.returncode, 2)
            self.assertTrue(result.stderr)

    def test_ladder_config_override_and_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'agent-kaizen.json').write_text(json.dumps({'calibrationLadder': ['opus high']}))
            (root / 'out').mkdir()
            (root / 'out/packets.jsonl').write_text(FIXTURE.read_text())
            data = json.loads(self.run_report('--project', root, '--json', config=root).stdout)
            self.assertEqual({p['model'] for p in data['proposals']}, {'opus'})
            data = json.loads(self.run_report('--project', root, '--json', '--ladder', 'sonnet high', config=root).stdout)
            self.assertEqual({p['model'] for p in data['proposals']}, {'sonnet'})


if __name__ == '__main__':
    unittest.main()
