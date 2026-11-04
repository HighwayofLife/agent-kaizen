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
        self.assertEqual(set(data), {'groups', 'area_groups', 'totals', 'fix_origins', 'proposals', 'rule', 'disclaimer'})
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
