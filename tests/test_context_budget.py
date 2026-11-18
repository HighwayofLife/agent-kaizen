import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'tools/context_budget.py'


class ContextBudgetTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.write('agents/a.md', '---\ndescription: Agent text\n---\n')
        self.write('skills/a/SKILL.md', '---\ndescription: "Hidden text"\ndisable-model-invocation: true\n---\n')
        self.write('hooks/a.sh', '#!/bin/sh\n')
        self.write('hooks/hooks.json', json.dumps({'hooks': {'SessionStart': [
            {'hooks': [{'type': 'command', 'command': 'bash "${CLAUDE_' + 'PLUGIN_ROOT}/hooks/a.sh"'}]}]}}))
        self.config = {'budget_bytes': 100, 'hooks': {'hooks/a.sh': {
            'literal_bytes': 8, 'literal_text': '12345678', 'sha256': hashlib.sha256(b'#!/bin/sh\n').hexdigest()}}}
        self.save_config()

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')

    def save_config(self):
        self.write('tools/context-budget.json', json.dumps(self.config))

    def run_check(self):
        return subprocess.run([sys.executable, str(SCRIPT), '--root', str(self.root)],
                              capture_output=True, text=True)

    def test_disabled_skill_agent_and_hook(self):
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('0 bytes (disabled)', result.stdout)
        self.assertIn('Total: 18 UTF-8 bytes; bytes/4 proxy: 4.50', result.stdout)

    def test_flagless_skill_counted_and_rejected(self):
        self.write('skills/a/SKILL.md', '---\ndescription: "Visible é"\n---\n')
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('10 bytes', result.stdout)
        self.assertIn('missing disable-model-invocation', result.stderr)

    def test_malformed_frontmatter(self):
        for text in ('description: no delimiters', '---\ndescription: "broken\n---\n',
                     '---\ndescription: x\ndescription: y\n---\n'):
            with self.subTest(text=text):
                self.write('agents/a.md', text)
                result = self.run_check()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('malformed', result.stderr)

    def test_over_budget(self):
        self.config['budget_bytes'] = 17
        self.save_config()
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('over budget by 1 bytes', result.stderr)

    def test_missing_hook_inventory(self):
        self.config['hooks'] = {}
        self.save_config()
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('missing registered-hook inventory entry', result.stderr)

    def test_changed_hook_needs_review(self):
        self.write('hooks/a.sh', '#!/bin/sh\necho changed\n')
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('hook changed; review and update inventory', result.stderr)


if __name__ == '__main__':
    unittest.main()
