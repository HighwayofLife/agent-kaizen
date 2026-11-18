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
                        COPILOT_HOME=str(self.home / 'copilot'),
                        KAIZEN_VSCODE_DATA_DIRS=str(self.home / 'vscode'))
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
        self.assertEqual(commands.splitlines(), [
            'plugin marketplace --help', 'plugin remove agent-kaizen@agent-kaizen-tools',
            'plugin marketplace remove agent-kaizen-tools',
            'plugin marketplace add ' + str(self.home / 'cache/agent-kaizen-acceptance/source'),
            'plugin add agent-kaizen@agent-kaizen-tools'])
        self.assertTrue((self.home / 'config/agent-kaizen/host-trace/on').exists())
        self.command('cleanup', '--host', 'codex')
        self.assertFalse((self.home / 'config/agent-kaizen/host-trace/on').exists())

    def test_copilot_install_order_and_failure_clears_state(self):
        fake = self.home / 'bin/copilot'
        shutil.copy(self.home / 'bin/codex', fake)
        result = self.command('install', '--host', 'copilot-cli', '--source', 'github')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.home / 'commands').read_text().splitlines(), [
            '--version', 'plugin marketplace --help', 'plugin uninstall agent-kaizen@agent-kaizen-tools',
            'plugin marketplace remove agent-kaizen-tools', 'plugin marketplace add HighwayofLife/agent-kaizen',
            'plugin install agent-kaizen@agent-kaizen-tools'])
        state = self.home / 'config/agent-kaizen/host-acceptance/copilot-cli.json'
        self.assertTrue(state.exists())
        fake.write_text('#!/bin/sh\nif [ "$1 $2 $3" = "plugin marketplace add" ]; then exit 1; fi\n')
        result = self.command('install', '--host', 'copilot-cli', '--source', 'github')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(state.exists())

    def test_copilot_shim_is_missing(self):
        fake = self.home / 'bin/copilot'
        fake.write_text('#!/bin/sh\necho "GitHub Copilot CLI was not found"\nexit 1\n')
        fake.chmod(0o755)
        result = self.command('install', '--host', 'vscode', '--source', 'github')
        self.assertEqual(result.returncode, 0)
        self.assertIn('Install GitHub Copilot CLI', result.stdout)
        result = self.command('install', '--host', 'copilot-cli', '--source', 'github')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Missing copilot CLI', result.stderr)

    def test_bad_copilot_path_and_missing_install_state(self):
        copilot = self.home / 'copilot'
        copilot.mkdir()
        (copilot / 'settings.json').write_text(json.dumps({
            'enabledPlugins': {'agent-kaizen@agent-kaizen-tools': True},
            'extraKnownMarketplaces': {'agent-kaizen-tools': {'source': {
                'source': 'directory', 'path': '~nosuchuser-xyz/mp'}}}}))
        result = self.command('check', '--host', 'copilot-cli')
        self.assertEqual(result.returncode, 1, result.stderr)
        report = max((ROOT / 'out/host-acceptance').glob('copilot-cli-*.json'), key=lambda p: p.stat().st_mtime_ns)
        rows = {r['id']: r for r in json.loads(report.read_text())['checks']}
        self.assertEqual(rows['installed']['status'], 'FAIL')
        self.assertTrue(rows['hooks-live:sessionStart']['detail'].startswith('install has not completed'))
        self.env['COPILOT_HOME'] = '~nosuchuser-xyz/mp'
        self.assertEqual(self.command('check', '--host', 'copilot-cli').returncode, 1)

    def test_vscode_newest_data_directory_wins(self):
        import runpy
        module = runpy.run_path(str(TOOL))
        first, second = self.home / 'first', self.home / 'second'
        for root, timestamp in ((first, 1000000000), (second, 2000000000)):
            manifest = root / 'agentPlugins/source/hash/.claude-plugin/plugin.json'
            manifest.parent.mkdir(parents=True)
            manifest.write_text(json.dumps({'name': 'agent-kaizen'}))
            os.utime(manifest, (timestamp, timestamp))
        from unittest.mock import patch
        with patch.dict(os.environ, {'KAIZEN_VSCODE_DATA_DIRS': os.pathsep.join(map(str, (first, second)))}):
            self.assertEqual(module['vscode_installs']()[2], second)

    def test_complete_install_and_live_trace(self):
        self.command('install', '--host', 'codex')
        version = json.loads((ROOT / '.claude-plugin/plugin.json').read_text())['version']
        installed = self.home / 'codex/plugins/cache/agent-kaizen-tools/agent-kaizen' / version
        shutil.copytree(ROOT, installed, ignore=shutil.ignore_patterns('.git', 'out', '__pycache__'))
        trace = self.home / 'config/agent-kaizen/host-trace/trace.jsonl'
        timestamp = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=2)).isoformat()
        events = [('SessionStart', None), ('UserPromptSubmit', None), ('PostToolUse', 'Bash')]
        def write_trace(items):
            trace.write_text(''.join(json.dumps(dict(ts=timestamp, host="codex", event=e, tool=t, keys=[], env=[])) + '\n' for e, t in items))
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

    def test_host_filter_sanitization_and_required_observation(self):
        self.command('install', '--host', 'codex')
        trace = self.home / 'config/agent-kaizen/host-trace/trace.jsonl'
        ts = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=2)).isoformat()
        def record(host, event, tool=None, keys=None):
            return dict(ts=ts, host=host, event=event, tool=tool, keys=keys or [], env=[])
        trace.write_text(''.join(json.dumps(x) + '\n' for x in [
            record('copilot', 'SessionStart'), record('copilot', 'UserPromptSubmit'),
            record('copilot', 'PostToolUse', 'Bash')]))
        self.command('check', '--host', 'codex', '--observe', 'skill_invoked=skip:unavailable')
        report = max((ROOT / 'out/host-acceptance').glob('codex-*.json'), key=lambda p: p.stat().st_mtime_ns)
        data = json.loads(report.read_text())
        rows = {r['id']: r for r in data['checks']}
        self.assertIn('no codex lines; seen hosts: copilot', rows['hooks-live:sessionStart']['detail'])
        self.assertEqual(rows['skill_invoked']['detail'], 'required observation skipped: unavailable')
        self.assertEqual(rows['skill_invoked']['status'], 'FAIL')
        trace.write_text(''.join(json.dumps(x) + '\n' for x in [record('codex', 'SessionStart'),
            record('codex', 'SessionStart'), record('codex', 'private value', 'secret value', ['bad key'])]))
        self.command('check', '--host', 'codex', '--observe', 'skill_invoked=pass')
        report = max((ROOT / 'out/host-acceptance').glob('codex-*.json'), key=lambda p: p.stat().st_mtime_ns)
        data = json.loads(report.read_text())
        rows = {r['id']: r for r in data['checks']}
        self.assertIn('2 sessionStart lines (multiple sessions contributed)', rows['hooks-live:sessionStart']['detail'])
        self.assertNotIn('secret value', json.dumps(data))
        self.assertIn('<other>', json.dumps(data))

    def test_manual_doctor_and_status_paths(self):
        statefile = self.home / 'config/agent-kaizen/host-acceptance/vscode.json'
        statefile.parent.mkdir(parents=True)
        statefile.write_text(json.dumps({'install': 'manual', 'installed_at': '2020-01-01T00:00:00+00:00', 'report': '/etc/passwd'}))
        self.assertIn('Phase 2', self.command('status', '--host', 'vscode').stdout)
        self.command('check', '--host', 'vscode', '--install-dir', str(ROOT), '--observe', 'skill_invoked=pass')
        report = max((ROOT / 'out/host-acceptance').glob('vscode-*.json'), key=lambda p: p.stat().st_mtime_ns)
        rows = {r['id']: r for r in json.loads(report.read_text())['checks']}
        self.assertEqual(rows['doctor']['status'], 'SKIP')
        self.assertIn('Copilot CLI location only', rows['doctor']['detail'])
        self.assertIn('Done: report at', self.command('status', '--host', 'vscode').stdout)

    def test_vscode_discovery_and_copilot_precedence(self):
        statefile = self.home / 'config/agent-kaizen/host-acceptance/vscode.json'
        statefile.parent.mkdir(parents=True)
        statefile.write_text(json.dumps({'install': 'manual', 'installed_at': '2020-01-01T00:00:00+00:00'}))
        chat = self.home / 'vscode/agentPlugins/file-x/hash'
        shutil.copytree(ROOT, chat, ignore=shutil.ignore_patterns('.git', 'out', '__pycache__'))
        self.command('check', '--host', 'vscode', '--observe', 'skill_invoked=pass')
        report = max((ROOT / 'out/host-acceptance').glob('vscode-*.json'), key=lambda p: p.stat().st_mtime_ns)
        rows = {r['id']: r for r in json.loads(report.read_text())['checks']}
        for name in ('installed', 'files', 'scripts', 'hooks-offline'):
            self.assertEqual(rows[name]['status'], 'PASS', rows[name])
        self.assertIn('VS Code chat:', rows['installed']['detail'])
        self.assertIn('plugin is installed for VS Code chat only', rows['hooks-live:sessionStart']['detail'])
        statefile.unlink()
        self.command('check', '--host', 'vscode')
        report = max((ROOT / 'out/host-acceptance').glob('vscode-*.json'), key=lambda p: p.stat().st_mtime_ns)
        rows = {r['id']: r for r in json.loads(report.read_text())['checks']}
        self.assertTrue(rows['hooks-live:sessionStart']['detail'].startswith('install has not completed'))
        self.assertNotIn('chat only', rows['hooks-live:sessionStart']['detail'])
        statefile.write_text(json.dumps({'installed_at': '2020-01-01T00:00:00+00:00'}))
        copilot = self.home / 'copilot/installed-plugins/agent-kaizen-tools/agent-kaizen'
        shutil.copytree(chat, copilot)
        self.command('check', '--host', 'vscode', '--observe', 'skill_invoked=pass')
        report = max((ROOT / 'out/host-acceptance').glob('vscode-*.json'), key=lambda p: p.stat().st_mtime_ns)
        rows = {r['id']: r for r in json.loads(report.read_text())['checks']}
        self.assertIn('copilot/installed-plugins', rows['installed']['detail'])
        self.assertIn('VS Code chat install also found', rows['installed']['detail'])
        self.assertNotIn('chat only', rows['hooks-live:sessionStart']['detail'])

    def test_copilot_live_marketplace_and_precedence(self):
        marketplace = self.home / 'marketplace'
        live = marketplace / 'plugin'
        shutil.copytree(ROOT, live, ignore=shutil.ignore_patterns('.git', 'out', '__pycache__'))
        metadata = marketplace / '.claude-plugin'
        metadata.mkdir()
        (metadata / 'marketplace.json').write_text(json.dumps({'plugins': [
            {'name': 'agent-kaizen', 'source': 'plugin'}]}))
        copilot = self.home / 'copilot'
        copilot.mkdir()
        settings = {'enabledPlugins': {'agent-kaizen@agent-kaizen-tools': True},
                    'extraKnownMarketplaces': {'agent-kaizen-tools': {'source': {
                        'source': 'directory', 'path': str(marketplace)}}}}
        settings_file = copilot / 'settings.json'
        statefile = self.home / 'config/agent-kaizen/host-acceptance/vscode.json'
        statefile.parent.mkdir(parents=True)
        statefile.write_text(json.dumps({'install': 'manual', 'installed_at': '2020-01-01T00:00:00+00:00'}))
        chat = self.home / 'vscode/agentPlugins/file-x/hash'
        shutil.copytree(live, chat)

        def check(host):
            self.command('check', '--host', host, '--observe', 'skill_invoked=pass')
            report = max((ROOT / 'out/host-acceptance').glob(host + '-*.json'), key=lambda p: p.stat().st_mtime_ns)
            return {r['id']: r for r in json.loads(report.read_text())['checks']}

        settings_file.write_text(json.dumps(settings))
        for host in ('copilot-cli', 'vscode'):
            rows = check(host)
            for name in ('installed', 'files', 'scripts', 'hooks-offline', 'doctor'):
                self.assertEqual(rows[name]['status'], 'PASS', rows[name])
            self.assertIn('live plugin from ~', rows['installed']['detail'])
        manifest = live / '.claude-plugin/plugin.json'
        original = manifest.read_text()
        data = json.loads(original)
        data['version'] = '0.0.0'
        manifest.write_text(json.dumps(data))
        self.assertEqual(check('copilot-cli')['installed']['status'], 'FAIL')
        manifest.write_text(original)
        settings['enabledPlugins']['agent-kaizen@agent-kaizen-tools'] = False
        settings_file.write_text(json.dumps(settings))
        self.assertEqual(check('copilot-cli')['installed']['status'], 'FAIL')
        settings['enabledPlugins']['agent-kaizen@agent-kaizen-tools'] = True
        settings_file.write_text(json.dumps(settings))
        installed = copilot / 'installed-plugins/agent-kaizen-tools/agent-kaizen'
        shutil.copytree(live, installed)
        rows = check('vscode')
        self.assertIn('copilot/installed-plugins', rows['installed']['detail'])
        self.assertNotIn('live plugin from', rows['installed']['detail'])

    def test_vscode_install_without_copilot(self):
        for name in ('python3', 'git'):
            (self.home / 'bin' / name).symlink_to(shutil.which(name))
        self.env['PATH'] = str(self.home / 'bin')
        result = self.command('install', '--host', 'vscode')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Install GitHub Copilot CLI', result.stdout)
        self.assertIn('Chat: Install Plugin from Source', result.stdout)
        state = json.loads((self.home / 'config/agent-kaizen/host-acceptance/vscode.json').read_text())
        self.assertEqual(state['install'], 'manual')

    def without_copilot(self):
        for name in ('python3', 'git'):
            (self.home / 'bin' / name).symlink_to(shutil.which(name))
        self.env['PATH'] = str(self.home / 'bin')

    def test_vscode_settings_jsonc_and_repeat(self):
        self.without_copilot()
        root = self.home / 'vscode'
        path = root / 'User/settings.json'
        path.parent.mkdir(parents=True)
        original = '{\n    // comment\n    "url": "https://example.invalid/a", /* block */\n}\n'
        path.write_text(original)
        first = self.command('install', '--host', 'vscode')
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertIn('settings changed', first.stdout)
        backup, = path.parent.glob('settings.json.bak-agent-kaizen-*')
        self.assertEqual(backup.read_text(), original)
        content = path.read_text()
        self.assertIn('// comment', content)
        self.assertIn('/* block */', content)
        import runpy
        clean = runpy.run_path(str(TOOL))['jsonc_clean']
        data = json.loads(clean(content))
        source = str((self.home / 'cache/agent-kaizen-acceptance/source').absolute())
        self.assertTrue(data['chat.plugins.enabled'])
        self.assertTrue(data['chat.pluginLocations'][source])
        self.assertEqual(data['url'], 'https://example.invalid/a')
        second = self.command('install', '--host', 'vscode')
        self.assertIn('settings unchanged', second.stdout)
        self.assertEqual(path.read_text(), content)
        self.assertEqual(list(path.parent.glob('settings.json.bak-agent-kaizen-*')), [backup])
        state = json.loads((self.home / 'config/agent-kaizen/host-acceptance/vscode.json').read_text())
        self.assertEqual(state['vscode_settings'], [str(path)])
        cleanup = self.command('cleanup', '--host', 'vscode')
        self.assertIn('chat.pluginLocations', cleanup.stdout)
        self.assertIn('restore the backup', cleanup.stdout)

    def test_vscode_existing_locations_and_disabled(self):
        self.without_copilot()
        path = self.home / 'vscode/User/settings.json'
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'chat.plugins.enabled': False, 'chat.pluginLocations': {'other': True}}))
        result = self.command('install', '--host', 'vscode')
        self.assertIn('Set chat.plugins.enabled to true', result.stdout)
        data = json.loads(path.read_text())
        self.assertIs(data['chat.plugins.enabled'], False)
        self.assertTrue(data['chat.pluginLocations']['other'])
        self.assertTrue(data['chat.pluginLocations'][str((self.home / 'cache/agent-kaizen-acceptance/source').absolute())])

    def test_vscode_invalid_missing_and_print_only(self):
        self.without_copilot()
        root = self.home / 'vscode'
        path = root / 'User/settings.json'
        path.parent.mkdir(parents=True)
        path.write_text('{ broken')
        result = self.command('install', '--host', 'vscode')
        self.assertIn('Invalid VS Code settings', result.stdout)
        self.assertEqual(path.read_text(), '{ broken')
        self.assertFalse(list(path.parent.glob('*.bak-agent-kaizen-*')))
        path.unlink()
        result = self.command('install', '--host', 'vscode', '--print-only')
        self.assertIn('Chat: Install Plugin from Source', result.stdout)
        self.assertFalse(path.exists())
        result = self.command('install', '--host', 'vscode')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(path.read_text())['chat.plugins.enabled'])

    def test_redaction_before_serialization(self):
        import runpy
        module = runpy.run_path(str(TOOL))
        redact = module['redact']
        redact.__globals__['HOME'] = Path('/Users/' + 'éclair')
        data = redact({'path': '/Users/' + 'éclair/test', 'nested': ['/home/' + 'someone/file', '/Users/' + 'another/file']})
        self.assertEqual(data, {'path': '~/test', 'nested': ['~/file', '~/file']})
        self.assertNotIn('éclair', json.dumps(data, ensure_ascii=False))
        self.assertEqual(redact('/uSERS/ÉCLAIR/test'), '~/test')
        self.assertEqual(redact(r'C:\Users\someone\file'), r'~\file')
