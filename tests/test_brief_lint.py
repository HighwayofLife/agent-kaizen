import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/brief-lint'
BASE = '## Goal and why\nGoal\n## Scope\nScope\n## Acceptance criteria\nDone\n## Verify\n```sh\ntrue\n```\n'


class BriefLintTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        (self.repo / 'scripts').mkdir()
        self.brief = self.repo / 'brief.md'

    def run_lint(self, text=BASE, *args):
        self.brief.write_text(text)
        return subprocess.run([sys.executable, str(SCRIPT), '--repo', str(self.repo),
                               *map(str, args), str(self.brief)], text=True, capture_output=True)

    def test_sections_and_config(self):
        for heading, key in [('Goal and why', 'goal'), ('Scope', 'scope'),
                             ('Acceptance criteria', 'acceptance'), ('Verify', 'verify')]:
            result = self.run_lint(BASE.replace('## ' + heading, '## unrelated'))
            self.assertEqual(result.returncode, 1)
            self.assertIn('missing section: ' + key, result.stdout)
        self.assertIn('empty section: goal', self.run_lint(BASE.replace('Goal\n', '')).stdout)
        self.assertEqual(self.run_lint(BASE.replace('Goal and why', 'GOAL').replace('Verify', 'VERIFICATION')).returncode, 0)
        config = self.repo / 'sections.json'
        config.write_text('{"goal": ["purpose"]}')
        self.assertEqual(self.run_lint(BASE.replace('Goal and why', 'Purpose'), '--sections', config).returncode, 0)
        self.assertEqual(self.run_lint(BASE, '--sections', config).returncode, 1)
        for content in ('{', '[]', '{"unknown": []}', '{"goal": "x"}'):
            config.write_text(content)
            self.assertEqual(self.run_lint(BASE, '--sections', config).returncode, 2)
        self.assertEqual(self.run_lint(BASE, '--sections', self.repo / 'missing').returncode, 2)
        self.assertEqual(subprocess.run([sys.executable, str(SCRIPT), str(self.repo / 'missing')], capture_output=True).returncode, 2)

    def test_paths_and_declarations(self):
        text = BASE + '\n`scripts/new-tool` and `scripts/new-tool:12-14`\n'
        self.assertIn('path not found: scripts/new-tool', self.run_lint(text).stdout)
        for declaration in ('Creates: `scripts/new-tool`', '**Creates:** `scripts/new-tool`',
                            '`scripts/new-tool` (new)', '`scripts/new-tool` (external)'):
            self.assertEqual(self.run_lint(text.replace('Scope\n', 'Scope\n' + declaration + '\n')).returncode, 0)
        (self.repo / 'scripts' / 'exists.py').touch()
        ignored = '`scripts/exists.py:1,3` `n/a` `keep/revert` `out/x` `~/x` `/tmp/x` `https://a/b` `scripts/*.py` `<a/b>` prose missing/file.py'
        self.assertEqual(self.run_lint(BASE + ignored).returncode, 0)
        self.assertEqual(self.run_lint(BASE + '\n```\n`scripts/missing.py`\n```').returncode, 0)
        feature = '''# 01: Flow event writer
## Goal and why
Add an append-only event log.
## Context
Default file `out/packet-events.jsonl` (external).
## Scope / do not touch
Creates: `scripts/packet-event`, `tests/test_packet_event.py`, `docs/flow.md`.
Edit only those.
## Steps
Write `docs/flow.md` first and `scripts/packet-event` next.
## Acceptance criteria
A valid call appends one line.
## Verification
```sh
python3 -m unittest discover -s tests
```
'''
        self.assertEqual(self.run_lint(feature).returncode, 0)

    def test_commands_and_no_execution(self):
        (self.repo / 'scripts' / 'x').touch()
        commands = "python3 -m unittest\nscripts/x --help\nFOO=1 python3 -c 'x'\ncd dir && missing-tool\n<exact commands>\n$(cmd)\n'bad\n"
        result = self.run_lint(BASE.replace('true\n', commands))
        self.assertEqual(result.returncode, 1)
        self.assertIn('command not found: missing-tool', result.stdout)
        self.assertEqual(result.stdout.count('warning: cannot check command:'), 3)
        marker = self.repo / 'marker'
        self.run_lint(BASE.replace('true\n', 'touch ' + str(marker) + '\n'))
        self.assertFalse(marker.exists())

    def test_size_json_and_multiple(self):
        for text, warning in [(BASE + '\n' * (200 - len(BASE.splitlines())), False),
                              (BASE + '\n' * (201 - len(BASE.splitlines())), True),
                              (BASE + 'x' * (12288 - len(BASE.encode())), False),
                              (BASE + 'x' * (12289 - len(BASE.encode())), True)]:
            result = self.run_lint(text, '--json')
            self.assertEqual(result.returncode, 0)
            self.assertEqual(bool(json.loads(result.stdout)['files'][0]['warnings']), warning)
        other = self.repo / 'other.md'
        other.write_text('nothing')
        result = self.run_lint(BASE, '--json', other)
        data = json.loads(result.stdout)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(data['status'], 'errors')
        self.assertEqual(len(data['files']), 2)
        self.assertEqual(set(data['files'][0]), {'path', 'errors', 'warnings'})


if __name__ == '__main__':
    unittest.main()
