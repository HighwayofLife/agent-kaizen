"""Host acceptance smoke tests using isolated host directories."""
import json
import os
from pathlib import Path
import subprocess
import shutil
import datetime
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / 'tools/host-acceptance'


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(('KAIZEN_', 'CLAUDE_', 'CODEX_', 'COPILOT_', 'XDG_'))}
        self.env.update(HOME=str(self.home), CLAUDE_CONFIG_DIR=str(self.home / 'config'),
                        XDG_CACHE_HOME=str(self.home / 'cache'), CODEX_HOME=str(self.home / 'codex'),
                        COPILOT_HOME=str(self.home / 'copilot'))
        bindir = self.home / 'bin'
        bindir.mkdir()
        fake = bindir / 'codex'
        fake.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$HOME/commands"\nif [ "$*" = "plugin marketplace --help" ]; then echo remove; fi\n')
        fake.chmod(0o755)
        self.env['PATH'] = str(bindir) + os.pathsep + self.env['PATH']

    def command(self, *args):
        return subprocess.run(['python3', str(TOOL), *args], env=self.env, text=True, capture_output=True)

    def test_status_install_and_export(self):
        self.assertIn('Phase 1', self.command('status', '--host', 'codex').stdout)
        self.assertEqual(self.command('install', '--host', 'codex').returncode, 0)
        self.assertIn('Phase 2', self.command('status', '--host', 'codex').stdout)
        commands = (self.home / 'commands').read_text()
        self.assertIn(str(self.home / 'cache/agent-kaizen-acceptance/source'), commands)
        self.assertNotIn(str(ROOT), commands)
        self.assertTrue((self.home / 'config/agent-kaizen/host-trace/on').exists())
        self.command('cleanup', '--host', 'codex')
        self.assertFalse((self.home / 'config/agent-kaizen/host-trace/on').exists())

    def test_complete_install_and_live_trace(self):
        self.command('install', '--host', 'codex')
        version = json.loads((ROOT / '.claude-plugin/plugin.json').read_text())['version']
        installed = self.home / 'codex/plugins/cache/agent-kaizen-tools/agent-kaizen' / version
        shutil.copytree(ROOT, installed, ignore=shutil.ignore_patterns('.git', 'out', '__pycache__'))
        trace = self.home / 'config/agent-kaizen/host-trace/trace.jsonl'
        timestamp = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=2)).isoformat()
        events = [('SessionStart', None), ('UserPromptSubmit', None), ('PostToolUse', 'Bash')]
        def write_trace(items):
            trace.write_text(''.join(json.dumps(dict(ts=timestamp, event=e, tool=t, keys=[], env=[])) + '\n' for e, t in items))
        write_trace(events)
        result = self.command('check', '--host', 'codex', '--observe', 'skill_invoked=pass')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        write_trace(events[:2])
        result = self.command('check', '--host', 'codex', '--observe', 'skill_invoked=pass')
        self.assertEqual(result.returncode, 1)
        report = json.loads(max((ROOT / 'out/host-acceptance').glob('codex-*.json'), key=lambda p: p.stat().st_mtime_ns).read_text())
        self.assertTrue(any(r['id'] == 'hooks-live:postToolUse' and r['status'] == 'FAIL' for r in report['checks']))
        manifest = installed / '.claude-plugin/plugin.json'
        data = json.loads(manifest.read_text())
        data['version'] = '0.0.0'
        manifest.write_text(json.dumps(data))
        result = self.command('check', '--host', 'codex', '--observe', 'skill_invoked=pass')
        self.assertEqual(result.returncode, 1)

    def test_check_missing_trace_and_observation_parsing(self):
        self.command('install', '--host', 'codex')
        result = self.command('check', '--host', 'codex', '--observe', 'skill_invoked=pass', '--observe', 'notice_seen=skip:private')
        self.assertEqual(result.returncode, 1)
        report = max((ROOT / 'out/host-acceptance').glob('codex-*.json'), key=lambda p: p.stat().st_mtime_ns)
        data = json.loads(report.read_text())
        rows = {r['id']: r for r in data['checks']}
        self.assertEqual(rows['hooks-live:sessionStart']['status'], 'FAIL')
        self.assertEqual(rows['skill_invoked']['status'], 'PASS')
        self.assertNotIn(str(self.home), report.read_text())
        self.assertNotEqual(self.command('check', '--host', 'codex', '--observe', 'bad=pass').returncode, 0)
