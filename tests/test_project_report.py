"""Tests for the project report command."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/kaizen-project-report'
loader = importlib.machinery.SourceFileLoader('project_report', str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
report = importlib.util.module_from_spec(spec)
loader.exec_module(report)


class ProjectReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / 'project'
        (self.project / 'docs/kaizen').mkdir(parents=True)
        (self.project / 'out').mkdir()
        shutil.copy(ROOT / 'tests/fixtures/packets.jsonl', self.project / 'out/packets.jsonl')
        self.env = dict(os.environ, CLAUDE_CONFIG_DIR=str(self.root))

    def configure(self, commands):
        (self.root / 'agent-kaizen.json').write_text(json.dumps({'projectCommands': {
            str(self.project): commands}}), encoding='utf-8')

    def invoke(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), '--project', str(self.project), *args],
                              capture_output=True, text=True, env=self.env)

    def test_sections_commands_ledger_and_json(self):
        self.configure({key: [sys.executable, '-c', f'print("{value}")'] for key, value in [
            ('shadowStatus', 'shadow ok'), ('slowTests', 'slow ok'), ('speedReport', 'speed ok')]})
        (self.project / 'docs/kaizen/LEDGER.md').write_text(
            '| Date | Change | Expected effect | Metric and command | Measured effect |\n'
            '| --- | --- | --- | --- | --- |\n'
            '| 2020-01-01 | Improve tests | faster | time | pending |\n', encoding='utf-8')
        result = self.invoke('--json')
        self.assertEqual(result.returncode, 0, result.stderr)
        sections = {s['title']: s['lines'] for s in json.loads(result.stdout)['sections']}
        self.assertEqual(len(sections), 6)
        self.assertIn('shadow ok', sections['Shadow reviews'])
        self.assertIn('slow ok', sections['Slow tests'])
        self.assertIn('speed ok', sections['Speed'])
        self.assertTrue(any('2020-01-01 Improve tests' in line and 'days pending' in line
                            for line in sections['Project ledger rows pending']))
        self.assertTrue(any('Totals:' in line for line in sections['Packet outcomes']))
        self.assertTrue(sections['Calibration proposals'])

    def test_failures_and_truncation(self):
        self.configure({'shadowStatus': [sys.executable, '-c', 'import sys; sys.exit(3)'],
                        'slowTests': ['nonexistent-project-report-command'],
                        'speedReport': [sys.executable, '-c', 'print("x\\n" * 20, end="")']})
        data = json.loads(self.invoke('--json').stdout)
        sections = {s['title']: s['lines'] for s in data['sections']}
        self.assertIn('exit 3', sections['Shadow reviews'][0])
        self.assertTrue(sections['Slow tests'][0].startswith('unavailable:'))
        self.assertEqual(sections['Speed'][-1], '… 5 more lines')
        with mock.patch.object(report.subprocess, 'run', side_effect=subprocess.TimeoutExpired('cmd', 120)):
            self.assertTrue(report.run_command(['cmd'], self.project)[0].startswith('unavailable:'))

    def test_unconfigured_and_project_config_ignored(self):
        marker = self.project / 'ran'
        (self.project / 'docs/kaizen/config.json').write_text(json.dumps({'projectCommands': {
            str(self.project): {'shadowStatus': [sys.executable, '-c', f'open({str(marker)!r}, "w").close()']}}}))
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('## Packet outcomes', result.stdout)
        self.assertIn('## Calibration proposals', result.stdout)
        self.assertIn('## Project ledger rows pending', result.stdout)
        self.assertNotIn('## Shadow reviews', result.stdout)
        self.assertFalse(marker.exists())
        self.assertIn('not configured', self.invoke('--verbose').stdout)

    def test_missing_log_and_atomic_output(self):
        (self.project / 'out/packets.jsonl').unlink()
        destination = self.root / 'report.md'
        result = self.invoke('--out', str(destination))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '')
        self.assertIn('no outcome log at out/packets.jsonl', destination.read_text())
        with mock.patch.object(report.os, 'replace', wraps=os.replace) as replace:
            with mock.patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': str(self.root)}):
                with mock.patch.object(sys, 'argv', ['report', '--project', str(self.project), '--out', str(destination)]):
                    report.main()
            replace.assert_called_once()
            self.assertNotEqual(Path(replace.call_args.args[0]), destination)

    def test_output_mode_and_invalid_commands(self):
        destination = self.root / 'report.md'
        for mask in (0o022, 0o077):
            result = subprocess.run([sys.executable, str(SCRIPT), '--project', str(self.project),
                                     '--out', str(destination)], env=self.env, capture_output=True,
                                    preexec_fn=lambda: os.umask(mask))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(destination.stat().st_mode & 0o777, 0o644 & ~mask)
        for value in ([], {str(self.project): []}):
            (self.root / 'agent-kaizen.json').write_text(json.dumps({'projectCommands': value}))
            result = self.invoke()
            self.assertEqual(result.returncode, 2)
            self.assertIn('projectCommands', result.stderr)
            self.assertNotIn('Traceback', result.stderr)

    def test_unenrolled(self):
        shutil.rmtree(self.project / 'docs/kaizen')
        result = self.invoke()
        self.assertEqual(result.returncode, 2)
        self.assertIn('not an enrolled project', result.stderr)


if __name__ == '__main__':
    unittest.main()
