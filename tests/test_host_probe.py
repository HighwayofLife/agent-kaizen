"""Offline checks for the isolated host probe."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

PROBE = Path(__file__).resolve().parents[1] / 'tools/host-probe'

CODEX = r'''#!/usr/bin/env python3
import json, os, pathlib, sys
args = sys.argv[1:]
with open(os.environ['RECORD'], 'a') as f:
    f.write(json.dumps({'args': args, 'cwd': os.getcwd(), 'env': dict(os.environ)}) + '\n')
if args == ['--version']:
    print('codex-cli 0.0.0-stub')
elif args[:3] == ['plugin', 'marketplace', 'add']:
    with open(os.environ['EXPORT_RECORD'], 'w') as f:
        json.dump([str(p.relative_to(args[3])) for p in pathlib.Path(args[3]).rglob('*')], f)
elif args[:2] == ['plugin', 'add']:
    pathlib.Path(os.environ['CODEX_HOME'], 'plugins/cache/agent-kaizen-tools/agent-kaizen/9.9.9').mkdir(parents=True)
elif args == ['debug', 'prompt-input']:
    mode = os.environ.get('PROMPT_MODE', '')
    if mode == 'exit': sys.exit(1)
    if mode == 'invalid': print('not json'); sys.exit()
    lines = [] if mode == 'empty' else ['- imagegen: text (file: x)']
    lines += ['- agent-kaizen:skill-%d: text (file: x)' % i for i in range(int(os.environ.get('COUNT', '0')))]
    print(json.dumps([{'text': '\n'.join(lines)}]))
elif args == ['app-server']:
    if os.environ.get('HOOK_MODE') == 'exit': sys.exit(1)
    for line in sys.stdin:
        request = json.loads(line)
        if request.get('id') == 1:
            print(json.dumps({'id': 1, 'result': {}}), flush=True)
        if request.get('id') == 2:
            if os.environ.get('HOOK_MODE') == 'error':
                print(json.dumps({'id': 2, 'error': {'code': -32603, 'message': 'failure'}}), flush=True)
                continue
            names = ['postToolUse', 'sessionStart', 'sessionStart', 'userPromptSubmit']
            if os.environ.get('HOOK_MODE') == 'one': names = names[:1]
            hooks = [{'eventName': n, 'pluginId': 'agent-kaizen@agent-kaizen-tools', 'source': 'plugin'} for n in names]
            print(json.dumps({'id': 2, 'result': {'data': [{'hooks': hooks}]}}), flush=True)
'''
COPILOT = r'''#!/usr/bin/env python3
import json, os, pathlib, sys
with open(os.environ['RECORD'], 'a') as f:
    f.write(json.dumps(sys.argv[1:]) + '\n')
if os.environ.get('SIGNIN'):
    print('Please sign in'); sys.exit(1)
if os.environ.get('MARKET_FAIL'):
    print('marketplace unavailable'); sys.exit(1)
if sys.argv[1:3] == ['plugin', 'install']:
    pathlib.Path(os.environ['COPILOT_HOME'], 'installed-plugins/agent-kaizen-tools/agent-kaizen').mkdir(parents=True)
'''


class HostProbeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # Match the probe's canonical paths (macOS aliases /var to /private/var).
        root = Path(self.temp.name).resolve()
        self.bin = root / 'bin'
        self.bin.mkdir()
        self.source = root / 'source'
        self.source.mkdir()
        self.scratch = root / 'scratch'
        self.scratch.mkdir()
        self.record = root / 'record'
        self.export_record = root / 'export-record'
        for name in ('git', 'tar', 'python3'):
            path = shutil.which(name)
            wrapper = self.bin / name
            wrapper.write_text('#!/bin/sh\nexec "{}" "$@"\n'.format(path))
            wrapper.chmod(0o755)
        subprocess.run(['git', 'init', '-q', str(self.source)], check=True)
        config = self.source / '.claude-plugin'
        config.mkdir()
        (config / 'plugin.json').write_text('{"name":"agent-kaizen","version":"9.9.9"}')
        (config / 'marketplace.json').write_text('{}')
        subprocess.run(['git', '-C', str(self.source), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(self.source), '-c', 'user.name=t', '-c', 'user.email=t@example.invalid', 'commit', '-qm', 'fixture'], check=True, env={**os.environ, 'GIT_CONFIG_GLOBAL': os.devnull})
        self.env = dict(os.environ, PATH=str(self.bin), TMPDIR=str(self.scratch), RECORD=str(self.record), EXPORT_RECORD=str(self.export_record), XDG_CONFIG_HOME='/misleading/xdg', CODEX_HOME='/misleading/codex', COPILOT_HOME='/misleading/copilot', KAIZEN_X='secret', CLAUDE_X='secret')

    def stub(self, name, content):
        path = self.bin / name
        path.write_text(content)
        path.chmod(0o755)

    def run_probe(self, *args, **env):
        return subprocess.run([sys.executable, str(PROBE), '--source', str(self.source), *args], env={**self.env, **env}, text=True, capture_output=True)

    def test_codex_and_isolation(self):
        self.stub('codex', CODEX)
        run = self.run_probe('--host', 'codex', COUNT='22')
        self.assertEqual(run.returncode, 1, run.stdout + run.stderr)
        self.assertIn('FAIL codex skills hidden: 22 listed', run.stdout)
        self.assertEqual(run.stdout.count('PASS codex'), 5)
        records = [json.loads(line) for line in self.record.read_text().splitlines()]
        for record in records:
            env = record['env']
            for key in ('HOME', 'CODEX_HOME', 'COPILOT_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME', 'XDG_STATE_HOME'):
                self.assertTrue(Path(env[key]).is_relative_to(self.scratch))
                self.assertFalse(Path(env[key]).is_relative_to(self.source))
            self.assertTrue(Path(record['cwd']).is_relative_to(self.scratch))
            self.assertFalse(any(k.startswith(('KAIZEN_', 'CLAUDE_')) for k in env))
        self.assertFalse(Path(records[0]['env']['HOME']).exists())
        self.assertEqual(self.run_probe('--host', 'codex').returncode, 0)
        self.assertEqual(self.run_probe('--host', 'codex', '--no-expect-hidden-skills', COUNT='22').returncode, 0)
        parsed = json.loads(self.run_probe('--host', 'codex', '--json', COUNT='22').stdout)
        self.assertEqual([x['status'] for x in parsed], ['PASS', 'PASS', 'PASS', 'PASS', 'FAIL', 'PASS'])

    def test_missing_and_copilot(self):
        self.assertIsNone(shutil.which('codex', path=str(self.bin)))
        run = self.run_probe()
        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.stdout.count('SKIP'), 2)
        self.stub('copilot', COPILOT)
        run = self.run_probe('--host', 'copilot', SIGNIN='1')
        self.assertEqual(run.returncode, 0)
        self.assertIn('SKIP copilot plugin install: needs sign-in', run.stdout)
        calls = [json.loads(line) for line in self.record.read_text().splitlines()]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][:3], ['plugin', 'marketplace', 'add'])
        self.record.unlink()
        run = self.run_probe('--host', 'copilot', MARKET_FAIL='1')
        self.assertEqual(run.returncode, 1)
        self.assertIn('SKIP copilot plugin install: marketplace unavailable', run.stdout)
        self.assertEqual(len(self.record.read_text().splitlines()), 1)
        run = self.run_probe('--host', 'copilot')
        self.assertEqual(run.returncode, 0, run.stdout)
        self.assertEqual(run.stdout.count('PASS'), 3)

    def test_failures_and_worktree(self):
        self.stub('codex', CODEX)
        for mode in ('exit', 'invalid'):
            run = self.run_probe('--host', 'codex', PROMPT_MODE=mode)
            self.assertEqual(run.returncode, 1)
            self.assertIn('FAIL codex skills hidden:', run.stdout)
        run = self.run_probe('--host', 'codex', PROMPT_MODE='empty')
        self.assertEqual(run.returncode, 0)
        self.assertIn('SKIP codex skills hidden:', run.stdout)
        run = self.run_probe('--host', 'codex', HOOK_MODE='exit')
        self.assertEqual(run.returncode, 1)
        self.assertIn('FAIL codex hooks discovered:', run.stdout)
        run = self.run_probe('--host', 'codex', HOOK_MODE='error')
        self.assertEqual(run.returncode, 1)
        self.assertIn('FAIL codex hooks discovered: JSON-RPC exchange failed: JSON-RPC error:', run.stdout)
        run = self.run_probe('--host', 'codex', HOOK_MODE='one')
        self.assertEqual(run.returncode, 1)
        self.assertIn('FAIL codex hooks discovered:', run.stdout)
        (self.source / 'new-file').write_text('new')
        outside = self.scratch / 'outside'
        outside.write_text('private')
        (self.source / 'external-link').symlink_to(outside)
        self.assertEqual(self.run_probe('--host', 'codex', '--worktree').returncode, 0)
        exported = json.loads(self.export_record.read_text())
        self.assertIn('new-file', exported)
        self.assertNotIn('external-link', exported)


if __name__ == '__main__':
    unittest.main()
