import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'check-profile'
loader = importlib.machinery.SourceFileLoader('check_profile', str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
profile = importlib.util.module_from_spec(spec)
loader.exec_module(profile)


class CheckProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.out = self.root / 'output'

    def cli(self, *args, env=None, cwd=None):
        return subprocess.run([sys.executable, str(SCRIPT), '--out', str(self.out), *map(str, args)],
                              text=True, capture_output=True, env=env, cwd=cwd, timeout=60)

    @unittest.skipIf(os.name == 'nt', 'POSIX shell fixture')
    def test_probe_slow_and_missing(self):
        fake = self.root / 'slow'
        fake.write_text('#!/bin/sh\nsleep 0.05\n')
        fake.chmod(0o755)
        env = dict(os.environ, PATH=str(self.root) + os.pathsep + os.environ['PATH'])
        result = self.cli('probe', '--programs', 'slow,missing-xyz', '--runs', '1', '--threshold-ms', '10', '--json', env=env)
        data = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0)
        self.assertTrue(data['programs'][0]['flagged'])
        self.assertEqual(data['programs'][0]['real'], os.path.realpath(fake))
        self.assertIsNone(data['programs'][1]['which'])

    def test_probe_timeout(self):
        args = profile.argparse.Namespace(programs='slow', runs=1, threshold_ms=1)
        self.out.mkdir()
        with mock.patch.object(profile.shutil, 'which', return_value='/fake'), mock.patch.object(profile.subprocess, 'run', side_effect=subprocess.TimeoutExpired('slow', 10)):
            data, _, code = profile.probe(args, self.out)
        self.assertEqual(code, 0)
        self.assertIn('error', data['programs'][0])

    @unittest.skipIf(os.name == 'nt', 'POSIX wrappers')
    def test_run_trace_junit_and_clean_output(self):
        self.out = self.root / 'output with space'
        binary = self.root / 'sample'
        binary.write_text('#!/bin/sh\necho child-output\n')
        binary.chmod(0o755)
        junit = self.root / 'junit.xml'
        junit.write_text('<testsuite><testcase classname="C" name="slow" time="0.2"/></testsuite>')
        env = dict(os.environ, PATH=str(self.root) + os.pathsep + os.environ['PATH'])
        self.out.mkdir()
        (self.out / 'trace.tsv').write_text('stale\targ\t100\n')
        result = self.cli('run', '--trace', 'sample', '--junit', junit, '--json', '--', 'sh', '-c', 'cd / && sample hello', env=env)
        data = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(data['programs'][0]['program'], 'sample')
        self.assertEqual(data['programs'][0]['top_args'][0]['argv1'], 'hello')
        self.assertEqual(data['tests'][0]['ms'], 200)
        self.assertIn('child-output', (self.out / 'run-untraced.log').read_text())
        self.assertTrue(any('overlap' in note for note in data['notes']))
        self.assertTrue(any('absolute path' in note for note in data['notes']))

    def test_windows_skip(self):
        self.out.mkdir()
        args = profile.argparse.Namespace(command=[sys.executable, '-c', 'print(1)'], trace='git', junit=None)
        with mock.patch.object(profile, 'IS_WINDOWS', True):
            data, lines, code = profile.run_command(args, self.out)
        self.assertEqual(code, 0)
        self.assertIn('tracing skipped on Windows', data['notes'])
        self.assertIn('tracing skipped on Windows', lines)

    @unittest.skipIf(os.name == 'nt', 'POSIX signals')
    def test_signal_maps_wrapper_exit(self):
        binary = self.root / 'killed'
        binary.write_text('#!/bin/sh\nkill -TERM $$\n')
        binary.chmod(0o755)
        env = dict(os.environ, PATH=str(self.root) + os.pathsep + os.environ['PATH'])
        result = self.cli('run', '--trace', 'killed', '--json', '--', 'killed', env=env)
        self.assertEqual(json.loads(result.stdout)['traced']['returncode'], 128 + signal.SIGTERM)

    def test_unittest_success_failure_and_import_path(self):
        (self.root / 'project_module.py').write_text('VALUE = 1\n')
        suite = self.root / 'suite'
        suite.mkdir()
        (suite / 'test_sample.py').write_text('import unittest\nimport project_module\nclass Sample(unittest.TestCase):\n def test_ok(self):\n  print("noise")\n  self.assertEqual(project_module.VALUE, 1)\n')
        result = self.cli('unittest', '-s', suite, '--json', cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['counts']['ok'], 1)
        (suite / 'test_sample.py').write_text('import unittest\nclass Sample(unittest.TestCase):\n def test_bad(self):\n  self.fail()\n')
        result = self.cli('unittest', '-s', suite, '--json', cwd=self.root)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(json.loads(result.stdout)['counts']['fail'], 1)

    @unittest.skipIf(os.name == 'nt', 'POSIX echo fixture')
    def test_unittest_child_output_statuses_and_fixture_error(self):
        suite = self.root / 'suite'
        suite.mkdir()
        (suite / 'test_sample.py').write_text('''import subprocess
import unittest
class Sample(unittest.TestCase):
 def test_child(self):
  subprocess.run(["echo", "CHILD-NOISE"], check=True)
 def test_subtest(self):
  with self.subTest(value=1): self.fail("bad")
 @unittest.expectedFailure
 def test_expected(self): self.fail("expected")
 @unittest.expectedFailure
 def test_unexpected(self): pass
class Broken(unittest.TestCase):
 @classmethod
 def setUpClass(cls): raise RuntimeError("fixture")
 def test_never(self): pass
''')
        result = self.cli('unittest', '-s', suite, '--json', cwd=self.root)
        self.assertEqual(result.returncode, 1, result.stderr)
        counts = json.loads(result.stdout)['counts']
        for status in ('ok', 'fail', 'error', 'expected_failure', 'unexpected_success'):
            self.assertEqual(counts[status], 1, status)
        self.assertIn('CHILD-NOISE', (self.out / 'unittest.log').read_text())

    @unittest.skipIf(os.name == 'nt', 'symlink fixture')
    def test_unittest_symlink_import_shadowing(self):
        link = self.root / 'check-profile'
        link.symlink_to(SCRIPT)
        (self.root / 'codex_common.py').write_text('VALUE = 42\n')
        suite = self.root / 'suite'
        suite.mkdir()
        (suite / 'test_shadow.py').write_text('import unittest, codex_common\nclass T(unittest.TestCase):\n def test_value(self): self.assertEqual(codex_common.VALUE, 42)\n')
        result = subprocess.run([sys.executable, str(link), '--out', str(self.out), 'unittest', '-s', str(suite), '--json'], cwd=self.root, text=True, capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['counts']['ok'], 1)

    def test_junit_stale_invalid_and_missing_trace(self):
        junit = self.root / 'junit.xml'
        junit.write_text('<testsuite/>')
        os.utime(junit, (1, 1))
        cmd = [sys.executable, '-c', 'pass']
        result = self.cli('run', '--trace', 'missing-profile-program', '--junit', junit, '--json', '--', *cmd)
        data = json.loads(result.stdout)
        self.assertTrue(any('stale JUnit file' in note for note in data['notes']))
        if os.name != 'nt':
            self.assertTrue(any('not found' in note for note in data['notes']))
        for xml in ('<invalid', '<testcase time="bad"/>'):
            junit.write_text(xml)
            result = self.cli('run', '--junit', junit, '--json', '--', *cmd)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(any('invalid JUnit file' in note for note in json.loads(result.stdout)['notes']))
            self.assertTrue((self.out / 'run.json').exists())

    @unittest.skipIf(os.name == 'nt', 'POSIX tracing')
    def test_trace_relative_path_and_markdown(self):
        binary = self.root / 'sample'
        binary.write_text('#!/bin/sh\nexit 0\n')
        binary.chmod(0o755)
        env = dict(os.environ, PATH='.' + os.pathsep + os.environ['PATH'])
        result = self.cli('run', '--trace', 'sample', '--', 'sample', env=env, cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Traced:', result.stdout)
        data = json.loads((self.out / 'run.json').read_text())
        self.assertEqual(data['programs'], [])
        self.assertTrue(any('relative PATH' in note for note in data['notes']))

    def test_hints(self):
        path = self.root / 'test_sample.py'
        path.write_text('time.sleep(1)\ntimeout=10\nurl="https://example.org"\nurl="http://localhost/path"\nsubprocess.run([])\n')
        result = self.cli('hints', path, '--json')
        data = json.loads(result.stdout)
        self.assertEqual(data['basis'], 'hypotheses')
        self.assertEqual({f['category'] for f in data['findings']}, {'sleep', 'large_timeout', 'network', 'subprocess'})
        self.assertEqual(next(f for f in data['findings'] if f['category'] == 'network')['lines'], [3])

    def test_compare_threshold_minimum_exit_and_kind(self):
        base = self.root / 'base.json'
        new = self.root / 'new.json'
        base.write_text(json.dumps({'kind': 'run', 'total_ms': 100}))
        for value, expected in [(110, 0), (140, 0), (200, 1)]:
            new.write_text(json.dumps({'kind': 'run', 'total_ms': value}))
            self.assertEqual(self.cli('compare', base, new).returncode, expected)
        self.assertEqual(self.cli('compare', base, new, '--exit-zero').returncode, 0)
        new.write_text(json.dumps({'kind': 'unittest', 'total_ms': 200}))
        self.assertEqual(self.cli('compare', base, new).returncode, 2)

    def test_compare_no_output_malformed_and_classnames(self):
        base, new = self.root / 'base.json', self.root / 'new.json'
        old = {'kind': 'run', 'tests': [{'classname': 'A', 'name': 'same', 'ms': 100}, {'classname': 'B', 'name': 'same', 'ms': 500}]}
        current = {'kind': 'run', 'tests': [{'classname': 'A', 'name': 'same', 'ms': 200}, {'classname': 'B', 'name': 'same', 'ms': 500}]}
        base.write_text(json.dumps(old))
        new.write_text(json.dumps(current))
        result = subprocess.run([sys.executable, str(SCRIPT), 'compare', str(base), str(new), '--json'], cwd=self.root, text=True, capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(json.loads(result.stdout)['regressions'][0]['item'], 'tests A.same ms')
        self.assertFalse((self.root / 'out').exists())
        for invalid in (None, {}, 'invalid'):
            current['tests'] = invalid
            new.write_text(json.dumps(current))
            result = self.cli('compare', base, new)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(len(result.stderr.splitlines()), 1)
            self.assertNotIn('Traceback', result.stderr)

    def test_compare_thresholds_independently(self):
        base, new = self.root / 'base.json', self.root / 'new.json'
        for old, current in ((1000, 1060), (10, 20)):
            base.write_text(json.dumps({'kind': 'run', 'total_ms': old}))
            new.write_text(json.dumps({'kind': 'run', 'total_ms': current}))
            self.assertEqual(self.cli('compare', base, new, '--min-delta-ms', '50', '--threshold', '20').returncode, 0)

    def test_compare_items_sorted_and_capped(self):
        base = self.root / 'base.json'
        new = self.root / 'new.json'
        old = {'kind': 'run', 'total_ms': 100,
               'tests': [{'id': str(i), 'ms': 100} for i in range(20)],
               'modules': [{'module': 'mod', 'total_ms': 100}],
               'programs': [{'program': 'git', 'total_ms': 100, 'median_ms': 100}]}
        current = {'kind': 'run', 'total_ms': 200,
                   'tests': [{'id': str(i), 'ms': 200 + i} for i in range(20)],
                   'modules': [{'module': 'mod', 'total_ms': 200}],
                   'programs': [{'program': 'git', 'total_ms': 200, 'median_ms': 200}]}
        base.write_text(json.dumps(old))
        new.write_text(json.dumps(current))
        result = self.cli('compare', base, new)
        self.assertEqual(result.returncode, 1)
        self.assertLessEqual(len(result.stdout.splitlines()), 15)
        data = json.loads((self.out / 'compare.json').read_text())
        self.assertEqual(len(data['regressions']), 24)
        self.assertEqual(data['regressions'][0]['item'], 'tests 19 ms')

    def test_compare_duplicate_and_invalid_values(self):
        base, new = self.root / 'base.json', self.root / 'new.json'
        data = {'kind': 'run', 'total_ms': 100, 'tests': [
            {'classname': 'C', 'name': 'same', 'ms': 200},
            {'classname': 'C', 'name': 'same', 'ms': 100}]}
        base.write_text(json.dumps(data))
        new.write_text(json.dumps(data))
        self.assertEqual(self.cli('compare', base, new).returncode, 0)
        for change in ({'total_ms': 'bad'}, {'tests': [{'id': [], 'ms': 1}]}):
            new.write_text(json.dumps(dict(data, **change)))
            result = self.cli('compare', base, new)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(len(result.stderr.splitlines()), 1)
        new.write_text(json.dumps(dict(data, total_ms=200)))
        result = self.cli('compare', base, new, '--exit-zero', env=dict(os.environ, PYTHONIOENCODING='cp1252'))
        self.assertEqual(result.returncode, 0)
        self.assertIn(' -> ', result.stdout)

    def test_unittest_streams_bytecode_and_subtests(self):
        suite = self.root / 'suite'
        suite.mkdir()
        (suite / 'test_streams.py').write_text('''import os, sys, unittest
class T(unittest.TestCase):
 def test_streams(self):
  sys.stdout.buffer.write(b"bytes\\n")
  os.fstat(sys.stderr.fileno())
  sys.__stdout__.write("buffered-original")
 def test_subtests(self):
  with self.subTest(n=1): self.fail("bad")
  with self.subTest(n=2): self.skipTest("skip")
''')
        result = self.cli('unittest', '-s', suite, '--json', cwd=self.root)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(json.loads(result.stdout)['counts']['fail'], 1)
        log = (self.out / 'unittest.log').read_text()
        self.assertIn('bytes', log)
        self.assertIn('buffered-original', log)
        self.assertFalse((suite / '__pycache__').exists())

    def test_hints_loopback_boundaries(self):
        path = self.root / 'test_urls.py'
        path.write_text('\n'.join('url="http://' + host + suffix + '"' for host in ('localhost', '127.0.0.1', '[::1]') for suffix in ('', '/path', ':80')) + '\nurl="http://example.org"')
        result = self.cli('hints', path, '--json')
        findings = json.loads(result.stdout)['findings']
        self.assertEqual(findings[0]['lines'], [10])

    @unittest.skipIf(os.name == 'nt', 'POSIX wrappers')
    def test_wrapper_inherited_fd_and_surrogate(self):
        helper = self.root / 'helper.py'
        helper.write_text(profile.HELPER)
        log = self.root / 'trace'
        fd = os.open(str(self.root / 'fd'), os.O_CREAT | os.O_WRONLY, 0o600)
        try:
            command = [sys.executable, str(helper), 'test', sys.executable, str(log), '-c',
                       'import os,sys; os.write(int(sys.argv[1]), b"ok")', str(fd), os.fsdecode(b'\xff')]
            result = subprocess.run(command, pass_fds=(fd,), capture_output=True)
        finally:
            os.close(fd)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / 'fd').read_bytes(), b'ok')
        binary = self.root / 'ok'
        binary.write_text('#!/bin/sh\nexit 0\n')
        binary.chmod(0o755)
        result = subprocess.run([sys.executable, str(helper), 'test', str(binary), str(log), os.fsdecode(b'\xff')])
        self.assertEqual(result.returncode, 0)
        self.assertIn('\\udcff', log.read_text())

    @unittest.skipIf(os.name == 'nt', 'POSIX tracing')
    def test_junit_before_trace_and_unique_logs(self):
        junit = self.root / 'result.xml'
        marker = self.root / 'marker'
        code = ('from pathlib import Path; p=Path(%r); m=Path(%r); '
                "p.write_text('<testsuite><testcase name=\"a\" time=\"%%s\"/></testsuite>' %% (2 if m.exists() else 1)); m.touch()" % (str(junit), str(marker)))
        for _ in range(2):
            marker.unlink(missing_ok=True)
            result = self.cli('run', '--trace', 'missing-profile-program', '--junit', junit, '--json', '--', sys.executable, '-c', code)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['tests'][0]['ms'], 1000)
        self.assertEqual(len(list(self.out.glob('trace-*.tsv'))), 2)

    @unittest.skipIf(os.name == 'nt', 'POSIX tracing')
    def test_concurrent_trace_logs_are_isolated(self):
        binary = self.root / 'sample'
        binary.write_text('#!/bin/sh\nsleep 0.15\n')
        binary.chmod(0o755)
        env = dict(os.environ, PATH=str(self.root) + os.pathsep + os.environ['PATH'])
        command = [sys.executable, str(SCRIPT), '--out', str(self.out), 'run', '--trace', 'sample', '--json', '--', 'sample']
        processes = [subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, text=True) for _ in range(2)]
        for process in processes:
            stdout, stderr = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, stderr)
            self.assertEqual(json.loads(stdout)['programs'][0]['calls'], 1)
        self.assertEqual(len(list(self.out.glob('trace-*.tsv'))), 2)

    def test_help(self):
        for command in ('probe', 'run', 'unittest', 'hints', 'compare'):
            self.assertEqual(self.cli(command, '--help').returncode, 0)


if __name__ == '__main__':
    unittest.main()
