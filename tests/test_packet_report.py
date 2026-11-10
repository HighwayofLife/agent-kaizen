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
        self.assertEqual(set(data), {'groups', 'area_groups', 'totals', 'fix_origins', 'proposals', 'escalations', 'dispatch_models_coverage', 'rule', 'disclaimer'})
        self.assertIn({'model': 'sonnet', 'effort': 'high', 'direction': 'UP'}, data['proposals'])
        self.assertIn({'model': 'opus', 'effort': 'high', 'direction': 'DOWN'}, data['proposals'])
        self.assertIn('too few', self.run_report('--packets', FIXTURE, '--since', '2026-02-01').stdout)
        self.assertIsNone(data['groups'][0]['median_wall_s'])

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
