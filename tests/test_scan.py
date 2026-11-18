import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
SCAN = ROOT / 'scripts' / 'kaizen-scan'
FIXTURE = ROOT / 'scripts' / 'kaizen-demo-fixtures'


def snapshot(root):
    library = root / 'Library'
    caches = library / 'Caches'
    def included(p):
        if sys.platform != 'darwin':
            return True
        if p == caches or caches in p.parents:
            return False
        if p == library and p.is_dir() and set(p.iterdir()) == {caches} and caches.is_dir():
            return False
        return True

    return {str(p.relative_to(root)): (p.stat().st_mode, p.stat().st_mtime_ns,
            hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None)
            for p in root.rglob('*') if included(p)}


class ScanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = dict(os.environ, HOME=str(self.root), CLAUDE_CONFIG_DIR=str(self.root / 'claude'),
                        CODEX_HOME=str(self.root / 'codex'), COPILOT_HOME=str(self.root / 'copilot'), XDG_CONFIG_HOME=str(self.root / 'config'),
                        TMPDIR=str(self.root), PYTHONDONTWRITEBYTECODE='1')

    def run_scan(self, *args):
        return subprocess.run([str(SCAN), *args], env=self.env, text=True, capture_output=True, check=True)

    def test_empty_and_demo_leave_no_artifacts(self):
        before = snapshot(self.root)
        empty = self.run_scan()
        self.assertIn('SKIP Context average: no data (', empty.stdout)
        self.assertIn('scan again', empty.stdout)
        self.assertNotIn(str(self.root), empty.stdout + empty.stderr)
        self.assertIn('~/', empty.stderr)
        self.assertEqual(before, snapshot(self.root))
        demo = self.run_scan('--demo')
        self.assertEqual(before, snapshot(self.root))
        self.assertEqual(demo.stdout, self.run_scan('--demo').stdout)
        self.assertEqual(before, snapshot(self.root))
        for name in ('Context peak', 'Cache rewrites', 'Relay agents', 'Images'):
            self.assertIn('WARN ' + name + ':', demo.stdout)
        self.assertIn('WARN Cache rewrites: 33.3%', demo.stdout)
        self.assertIn('128,100', demo.stdout)
        self.assertEqual(demo.stdout.splitlines()[-1], '0 fail, 4 warn, 3 pass, 4 skipped')
        statuses = [line.split(' ', 1)[0] for line in demo.stdout.splitlines()
                    if line.startswith(('FAIL ', 'WARN ', 'PASS ', 'SKIP '))]
        self.assertEqual(statuses, sorted(statuses, key=('FAIL', 'WARN', 'PASS', 'SKIP').index))
        for line in demo.stdout.splitlines():
            if line.startswith(('PASS ', 'WARN ', 'SKIP ')):
                skill = line.rsplit('/agent-kaizen:', 1)[1]
                self.assertTrue((ROOT / 'skills' / skill / 'SKILL.md').is_file(), skill)

    def test_copilot_notice_and_demo_isolation(self):
        normal = self.run_scan()
        self.assertNotIn('Copilot', normal.stdout + normal.stderr)
        (Path(self.env['COPILOT_HOME']) / 'session-state').mkdir(parents=True)
        result = self.run_scan()
        self.assertIn('Audit note:', result.stderr)
        self.assertIn('Copilot sessions found but not measured', result.stderr)
        self.assertIn('Codex (Copilot sessions are not measured yet) and scan again.', result.stdout)
        demo = self.run_scan('--demo')
        self.assertNotIn('Copilot', demo.stdout + demo.stderr)

    def test_real_fixture_does_not_change_home_or_config(self):
        subprocess.run([str(FIXTURE), '--output', self.env['CLAUDE_CONFIG_DIR']],
                       env=self.env, check=True)
        (self.root / 'codex').mkdir()
        (self.root / 'config').mkdir()
        before = snapshot(self.root)
        result = self.run_scan()
        self.assertIn('WARN Cache rewrites:', result.stdout)
        self.assertEqual(before, snapshot(self.root))


if __name__ == '__main__':
    unittest.main()
