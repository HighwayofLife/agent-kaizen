"""Tests for the optional SessionStart notices."""
import datetime
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / 'hooks/session-notes.sh'


class SessionNotesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        for name in ('bash', 'jq', 'python3', 'awk', 'tail', 'timeout', 'sleep', 'mktemp', 'cat', 'rm'):
            target = shutil.which(name)
            if target:
                (self.bin / name).symlink_to(target)
        self.env = {**os.environ, 'PATH': str(self.bin),
                    'CLAUDE_CONFIG_DIR': str(self.root / 'config')}

    def run_hook(self):
        return subprocess.run(['bash', str(HOOK)], input='{}', text=True,
                              capture_output=True, cwd=self.root, env=self.env, timeout=5)

    def context(self):
        result = self.run_hook()
        self.assertEqual(result.returncode, 0, result.stderr)
        if not result.stdout:
            return ''
        output = json.loads(result.stdout)['hookSpecificOutput']
        self.assertEqual(output['hookEventName'], 'SessionStart')
        return output['additionalContext']

    def stub(self, name, body, directory=None):
        path = (directory or self.bin) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('#!/bin/bash\n' + body + '\n')
        path.chmod(0o755)

    def test_empty_and_ledger_columns(self):
        self.assertEqual(self.context(), '')
        ledger = self.root / 'docs/kaizen/LEDGER.md'
        ledger.parent.mkdir(parents=True)
        old = datetime.date.today() - datetime.timedelta(days=7)
        recent = datetime.date.today() - datetime.timedelta(days=6)
        ledger.write_text('| Item | Measured effect | Date |\n| --- | --- | --- |\n'
                          f'| a | pending | {old} |\n| b | pending | {recent} |\n'
                          f'| c | done | {old} |\n')
        self.assertIn('1 ledger rows still pending', self.context())

    def test_dispatch_sections_and_config_fallback(self):
        self.stub('dispatch-status', "printf 'RUNNING\\n  worker 1\\nOTHER\\n  ignore\\nDIRTY WORKTREES\\n  branch 2\\n'",
                  self.root / 'config/bin')
        context = self.context()
        self.assertIn('worker 1', context)
        self.assertIn('branch 2', context)
        self.assertNotIn('ignore', context)
        self.stub('dispatch-status', "printf 'RUNNING\\n\\nDIRTY WORKTREES\\n'")
        self.assertEqual(self.context(), '')

    @unittest.skipUnless(shutil.which('timeout'), 'timeout is required')
    def test_dispatch_timeout(self):
        self.stub('dispatch-status', 'while :; do :; done')
        self.env['SESSION_NOTES_TIMEOUT'] = '0.1'
        self.assertEqual(self.context(), '')

    def test_dispatch_timeout_without_timeout_commands(self):
        (self.bin / 'timeout').unlink(missing_ok=True)
        self.stub('dispatch-status', 'sleep 3')
        self.env['SESSION_NOTES_TIMEOUT'] = '0.1'
        self.assertEqual(self.context(), '')

    def test_rules_lint(self):
        for output in ('rules-lint: 0 stale-rule hit(s)', 'rules-lint: no patterns configured', ''):
            with self.subTest(output=output):
                self.stub('rules-lint', f"printf '%s\\n' '{output}'")
                self.assertEqual(self.context(), '')
        self.stub('rules-lint', "printf '%s\\n' 'rules-lint: 3 stale-rule hit(s)'")
        self.assertIn('rules-lint: 3 stale-rule hit(s)', self.context())

    def test_missing_jq(self):
        (self.bin / 'jq').unlink(missing_ok=True)
        result = self.run_hook()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '')
        self.assertIn('jq', result.stderr)


if __name__ == '__main__':
    unittest.main()
