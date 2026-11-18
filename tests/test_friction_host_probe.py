import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/host-probe'
loader = importlib.machinery.SourceFileLoader('friction_host_probe', str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
probe_module = importlib.util.module_from_spec(spec)
loader.exec_module(probe_module)


class HostProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.project = self.root / 'project'
        self.project.mkdir()
        self.catalog = ROOT / 'scripts/friction-catalog.json'

    def probe(self, platform='linux'):
        return probe_module.Probe(self.project, platform, self.root / 'proc', self.catalog)

    def cli(self, out, *args):
        return subprocess.run([sys.executable, str(SCRIPT), '--project', str(self.project),
                               '--out', str(out), *args], capture_output=True, text=True)

    def test_private_unique_atomic_reports(self):
        out = self.root / 'audit'
        first = self.cli(out, '--json')
        second = self.cli(out)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        report = json.loads(first.stdout)
        self.assertEqual(report['v'], 1)
        self.assertIn('generated_at', report)
        self.assertEqual(report['worktrees'], [])
        self.assertEqual(report['regenerable_dirs'], [])
        files = list(out.glob('host-probe-*.json'))
        self.assertEqual(len(files), 2)
        self.assertFalse(list(out.glob('.host-probe-*')))
        if os.name == 'posix':
            self.assertTrue(all(p.stat().st_mode & 0o077 == 0 for p in files))

    def test_output_refusal(self):
        target = self.root / 'target'
        target.mkdir()
        link = self.root / 'link'
        link.symlink_to(target, target_is_directory=True)
        self.assertNotEqual(self.cli(link).returncode, 0)
        self.assertEqual(list(target.iterdir()), [])
        file_path = self.root / 'file'
        file_path.write_text('occupied')
        self.assertNotEqual(self.cli(file_path / 'child').returncode, 0)

    def test_linux_findings_and_unavailable(self):
        probe = self.probe()
        with mock.patch.object(probe, 'command', side_effect=['mds\n', 'a\0b\0']), \
             mock.patch.object(probe, 'read_proc', return_value=1), \
             mock.patch.object(probe_module.shutil, 'disk_usage', return_value=mock.Mock(total=100, free=5)):
            report = probe.run()
        self.assertEqual({f['id'] for f in report['findings']}, {'inotify', 'low-disk'})
        self.assertTrue(all(isinstance(v, (int, float)) for f in report['findings'] for v in f['evidence'].values()))
        probe = self.probe()
        with mock.patch.object(probe, 'command', return_value=None):
            report = probe.run()
        self.assertIsNone(report['facts']['processes'])
        self.assertIsNone(report['facts']['inotify_max_user_watches'])
        self.assertIn('proc_unavailable', report['warnings'])

    def test_windows_catalogue_only_and_informational(self):
        probe = self.probe('windows')
        with mock.patch.object(probe, 'command', return_value='"MsMpEng.exe","1"\n"private.exe","2"\n'):
            report = probe.run()
        self.assertEqual(report['facts']['processes']['defender']['count'], 1)
        self.assertTrue(report['facts']['processes']['defender']['informational'])
        self.assertNotIn('private.exe', json.dumps(report))
        self.assertIn('inotify_unavailable', report['warnings'])

    def test_bounded_commands_and_budget(self):
        probe = self.probe()
        self.assertIsNone(probe.command([sys.executable, '-c', 'print("x" * 1100000)']))
        self.assertIn('command_output', probe.warnings)
        probe.deadline = time.monotonic() + 0.1
        self.assertIsNone(probe.command([sys.executable, '-c', 'import time; time.sleep(10)']))
        self.assertIn('timeout', probe.warnings)
        probe.deadline = 0
        self.assertIsNone(probe.command(['missing']))
        self.assertIn('budget', probe.warnings)

    def test_missing_catalog_and_copied_install(self):
        probe = probe_module.Probe(self.project, 'unknown', self.root, self.root / 'missing')
        self.assertIn('catalogue', probe.warnings)
        install = self.root / 'install'
        install.mkdir()
        (install / 'kaizen-host-probe').write_bytes(SCRIPT.read_bytes())
        (install / 'kaizen-friction-catalog.json').write_bytes(self.catalog.read_bytes())
        result = subprocess.run([sys.executable, str(install / 'kaizen-host-probe'), '--project',
                                 str(self.project), '--out', str(self.root / 'audit'), '--json'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('catalogue', json.loads(result.stdout)['warnings'])


if __name__ == '__main__':
    unittest.main()
