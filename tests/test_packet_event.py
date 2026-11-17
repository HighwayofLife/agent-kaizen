import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import runpy


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/packet-event'


class PacketEventTests(unittest.TestCase):
    def run_event(self, *args, cwd=None):
        return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)],
                              cwd=cwd, capture_output=True, text=True)

    def test_help(self):
        result = self.run_event('--help')
        self.assertEqual(result.returncode, 0)
        for value in ('queued', 'round-N', 'landed', 'failed',
                      'out/packet-events.jsonl', '0 written', '1 write failed', '2 invalid input'):
            self.assertIn(value, result.stdout)

    def test_write_and_default_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_event('packet', 'queued', '--ts', '2026-01-01T02:00:00+02:00', cwd=tmp)
            self.assertEqual(result.returncode, 0, result.stderr)
            path = Path(tmp) / 'out/packet-events.jsonl'
            self.assertEqual(json.loads(path.read_text()),
                             {'ts': '2026-01-01T00:00:00Z', 'id': 'packet', 'state': 'queued'})
            result = self.run_event('packet', 'round-12', '--ts', '2026-01-01T00:00:00.123456Z',
                                    '--detail', 'café "quoted"', '--file', path)
            self.assertEqual(result.returncode, 0, result.stderr)
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[1]['ts'], '2026-01-01T00:00:00.123456Z')
            self.assertEqual(rows[1]['detail'], 'café "quoted"')

    def test_invalid_leaves_log_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'events'
            path.write_text('existing\n')
            cases = [('', 'queued'), ('a\nb', 'queued'), ('a\rb', 'queued'),
                     ('a', 'unknown'), ('a', 'round-0'), ('a', 'round-x'),
                     ('a', 'ROUND-1'), ('a', 'queued', '--ts', '2026-01-01T00:00:00'),
                     ('a', 'queued', '--ts', 'bad'), ('a', 'queued', '--detail', 'é' * 4096)]
            for args in cases:
                with self.subTest(args=args[:2]):
                    result = self.run_event(*args, '--file', path)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertEqual(len(result.stderr.splitlines()), 1)
                    self.assertEqual(path.read_text(), 'existing\n')

    def test_nested_path_and_directory_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'new/nested/events'
            result = self.run_event('id', 'round-1', '--file', path)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(path.is_file())
            result = self.run_event('id', 'ready', '--file', tmp)
            self.assertEqual(result.returncode, 1)
            self.assertTrue(result.stderr)

    def test_short_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = runpy.run_path(str(SCRIPT))
            with mock.patch.object(sys, 'argv', [str(SCRIPT), 'id', 'ready', '--file', tmp + '/log']), \
                 mock.patch('os.write', return_value=1), \
                 mock.patch('sys.stderr') as stderr:
                self.assertEqual(module['main'](), 1)
                self.assertIn('short write', str(stderr.write.call_args_list))

    def test_concurrent_writers(self):
        worker = '''\
import subprocess, sys
script, path, worker = sys.argv[1:]
for i in range(25):
    result = subprocess.run([sys.executable, script, worker + '-' + str(i), 'queued', '--file', path])
    if result.returncode:
        sys.exit(result.returncode)
'''
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'events'
            processes = [subprocess.Popen([sys.executable, '-c', worker, str(SCRIPT), str(path), str(i)])
                         for i in range(8)]
            for process in processes:
                self.assertEqual(process.wait(), 0)
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(len(rows), 200)
            self.assertTrue(all(set(row) == {'ts', 'id', 'state'} for row in rows))
            self.assertEqual(len({(row['id'], row['state']) for row in rows}), 200)
            self.assertEqual({row['id'] for row in rows},
                             {f'{worker}-{i}' for worker in range(8) for i in range(25)})


if __name__ == '__main__':
    unittest.main()
