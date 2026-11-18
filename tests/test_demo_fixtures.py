"""Contract tests for public synthetic audit fixtures."""
from datetime import datetime, timezone
import json
import runpy
from unittest import mock

from test_scripts import SCRIPTS, StubCase


class DemoFixtureTests(StubCase):
    def rows(self, path):
        return [json.loads(line) for line in path.read_text().splitlines()]

    def test_audit_and_exact_timestamps(self):
        root = self.root / 'demo'
        fixture = runpy.run_path(str(SCRIPTS / 'kaizen-demo-fixtures'))
        fixed = datetime(2025, 1, 2, 12, 0, tzinfo=timezone.utc)
        with mock.patch.dict(fixture['generate'].__globals__, datetime=mock.Mock(now=mock.Mock(return_value=fixed))):
            fixture['generate'](root)
        project = root / 'projects' / 'synthetic-demo'
        main = self.rows(project / 'synthetic-main.jsonl')
        relay = self.rows(project / 'synthetic-main/subagents/synthetic-relay.jsonl')
        self.assertEqual([r['timestamp'] for r in main],
                         ['2025-01-02T10:00:00+00:00', '2025-01-02T10:01:00+00:00',
                          '2025-01-02T10:02:00+00:00', '2025-01-02T11:02:00+00:00'])
        self.assertEqual([r['timestamp'] for r in relay],
                         ['2025-01-02T10:01:00+00:00', '2025-01-02T10:02:00+00:00',
                          '2025-01-02T10:03:00+00:00'])
        self.env['CLAUDE_CONFIG_DIR'] = str(self.root / 'isolated-claude')
        self.env['CODEX_HOME'] = str(self.root / 'isolated-codex')
        data = json.loads(self.run_script('token-audit', '--json', '--since', '2025-01-01', '--project-dir', project,
                                          '--out', self.root / 'reports').stdout)
        self.assertEqual(data['headline']['claude_calls'], 3)
        self.assertEqual(data['headline']['claude_context'], 384300)
        self.assertEqual(data['headline']['image_reads'], 1)
        self.assertEqual(data['headline']['codex_sessions'], 0)
        self.assertEqual(data['sessions'][0]['context'], 383000)
        self.assertEqual(data['sessions'][0]['peak'], 192000)
        self.assertEqual(data['sessions'][0]['cache_write'], 190000)
        self.assertEqual(data['agents']['relay'][0]['output'], 30)
        self.assertEqual(data['bash']['relay'], {'rg TODO': 1, 'git status': 1, 'ls src': 1})
        self.assertEqual(data['tool_counts'], {'Agent:relay': 1, 'Read': 1})

    def test_refuses_output_symlink(self):
        root = self.root / 'demo'
        self.run_script('kaizen-demo-fixtures', '--output', root)
        target = self.root / 'outside'
        target.write_text('unchanged')
        path = root / 'projects/synthetic-demo/synthetic-main.jsonl'
        path.unlink()
        path.symlink_to(target)
        result = self.run_script('kaizen-demo-fixtures', '--output', root, code=1)
        self.assertIn('symlink', result.stderr)
        self.assertEqual(target.read_text(), 'unchanged')

    def test_repeat_and_output_boundary(self):
        self.run_script('kaizen-demo-fixtures', '--help')
        self.run_script('kaizen-demo-fixtures', code=2)
        roots = [self.root / 'first', self.root / 'second']
        before = set(self.root.rglob('*'))
        for root in roots:
            self.run_script('kaizen-demo-fixtures', '--output', root)
        created = set(self.root.rglob('*')) - before
        self.assertTrue(all(any(path == root or root in path.parents for root in roots) for path in created))
        files = sorted(p.relative_to(roots[0]) for p in roots[0].rglob('*') if p.is_file())
        self.assertEqual(files, sorted(p.relative_to(roots[1]) for p in roots[1].rglob('*') if p.is_file()))
        self.assertEqual([str(path) for path in files], [
            'projects/synthetic-demo/synthetic-main/subagents/synthetic-relay.jsonl',
            'projects/synthetic-demo/synthetic-main/subagents/synthetic-relay.meta.json',
            'projects/synthetic-demo/synthetic-main.jsonl'])
        for path in files:
            first, second = [(root / path).read_text() for root in roots]
            self.assertNotIn(str(self.root), first)
            if path.suffix == '.jsonl':
                a, b = [[json.loads(line) for line in text.splitlines()] for text in (first, second)]
                for rows in (a, b):
                    for row in rows:
                        row.pop('timestamp')
                self.assertEqual(a, b)
            else:
                self.assertEqual(first, second)
        sentinel = roots[0] / 'keep.txt'
        sentinel.write_text('unrelated data')
        self.run_script('kaizen-demo-fixtures', '--output', roots[0])
        self.assertEqual(sentinel.read_text(), 'unrelated data')
        self.assertEqual(sorted(p.relative_to(roots[0]) for p in roots[0].rglob('*') if p.is_file()),
                         sorted(files + [sentinel.relative_to(roots[0])]))
