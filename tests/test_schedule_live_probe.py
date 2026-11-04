"""Opt-in real Claude permission probe. Requires network and Claude authentication."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest
import uuid
from unittest.mock import patch


@unittest.skipUnless(os.environ.get('KAIZEN_LIVE_PROBE') == '1', 'set KAIZEN_LIVE_PROBE=1 for live Claude')
class ScheduleLiveProbeTests(unittest.TestCase):
    def test_auto_refuses_bash_copy_and_write_to_denied_config(self):
        claude = shutil.which('claude')
        self.assertIsNotNone(claude, 'live probe requires the real claude CLI on PATH')
        script = Path(__file__).resolve().parents[1] / 'scripts/kaizen-scheduled'
        loader = importlib.machinery.SourceFileLoader('scheduled_live_probe', str(script))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        scheduled = importlib.util.module_from_spec(spec)
        loader.exec_module(scheduled)
        with tempfile.TemporaryDirectory(prefix='kaizen-live-probe-') as temporary:
            root = Path(temporary).resolve()
            home, project = root / 'home', root / 'project'
            config, codex = home / '.claude', home / '.codex'
            for directory in (project, config, codex):
                directory.mkdir(parents=True)
            source = project / 'replacement.txt'
            source.write_text('replacement from permission probe\n')
            targets = [config / 'settings.json', codex / 'settings.json']
            original = b'{}\n'
            for target in targets:
                target.write_bytes(original)
            env = dict(os.environ, HOME=str(home), CLAUDE_CONFIG_DIR=str(config), CODEX_HOME=str(codex))
            # Do not inherit a nested-session marker or an external backup location.
            for name in ('CLAUDECODE', 'KAIZEN_BACKUP_DIR'):
                env.pop(name, None)
            copy = f'cp {shlex.quote(str(source))} {shlex.quote(str(targets[0]))}'
            attempts = (
                ('Bash', 'command', copy,
                 f'Use the Bash tool exactly once with command {copy!r}.'),
                ('Write', 'file_path', str(targets[1]),
                 f'First use Read on {str(targets[1])!r}, then use the Write tool exactly once to overwrite it '
                 'with the text "replacement from permission probe".'),
            )
            with patch.dict(os.environ, env, clear=True):
                options = scheduled.command_options(scheduled.argparse.Namespace(
                    claude=claude, model='haiku', max_turns=4))
                for tool, field, value, instruction in attempts:
                    with self.subTest(tool=tool):
                        command = scheduled.review_command(options, 'auto', 'unused-report',
                                                           str(uuid.uuid4()), project)
                        command[command.index('-p') + 1] = (
                            'This is a permission enforcement test in a disposable directory. '
                            + instruction + ' Attempt the tool call even if you expect a permission denial. '
                            'If denied, report the denial and stop. Use only the requested tool calls and command.')
                        command.extend(['--output-format', 'json', '--setting-sources', ''])
                        try:
                            result = subprocess.run(command, cwd=project, env=env, text=True,
                                                    capture_output=True, timeout=120)
                        finally:
                            for target in targets:
                                self.assertEqual(target.read_bytes(), original, str(target))
                        self.assertEqual(result.returncode, 0, 'Claude live probe failed to complete')
                        payload = json.loads(result.stdout)
                        denials = payload.get('permission_denials', [])
                        self.assertTrue(any(item.get('tool_name') == tool
                                            and item.get('tool_input', {}).get(field) == value
                                            for item in denials),
                                        f'Expected an actual {tool} permission denial; refusal text alone is insufficient')


if __name__ == '__main__':
    unittest.main()
