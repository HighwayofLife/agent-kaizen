"""Offline scheduler tests with isolated homes and a file-backed crontab."""
import importlib.machinery
import importlib.util
import os
import json
from pathlib import Path
import plistlib
import re
import shlex
import shutil
import subprocess
import sys
from unittest.mock import patch

from test_scripts import StubCase, write, executable


SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
CRONTAB = '''#!/usr/bin/env python3
import os, pathlib, sys
path = pathlib.Path(os.environ['CRON_FILE'])
if sys.argv[1] == '-l':
    if not path.exists():
        sys.stderr.write('no crontab for user\\n')
        sys.exit(1)
    sys.stdout.write(path.read_text())
else:
    path.write_text(sys.stdin.read())
'''

SYSTEMCTL = '''#!{python}
import json, os, sys
with open(os.environ['SYSTEMD_LOG'], 'a') as stream:
    stream.write(json.dumps(sys.argv[1:]) + '\\n')
if sys.argv[2:] == ['is-system-running']:
    state = os.environ.get('STUB_STATE', 'running')
    print(state)
    sys.exit(0 if state == 'running' else 1)
if os.environ.get('STUB_FAIL') in sys.argv:
    sys.exit(1)
sys.exit(int(os.environ.get('STUB_DISABLE_EXIT', '0')) if 'disable' in sys.argv else 0)
'''

LOGINCTL = '''#!{python}
import json, os, sys
with open(os.environ['SYSTEMD_LOG'], 'a') as stream:
    stream.write(json.dumps(['loginctl'] + sys.argv[1:]) + '\\n')
print(os.environ.get('STUB_LINGER', 'Linger=yes'))
'''


class ScheduleTests(StubCase):
    def setUp(self):
        super().setUp()
        self.env.pop('CLAUDE_CONFIG_DIR', None)
        self.env.pop('CODEX_HOME', None)
        self.env.pop('KAIZEN_REVIEW_MODEL', None)
        self.env.pop('KAIZEN_REVIEW_MAX_TURNS', None)
        self.env.pop('CLAUDE_PLUGIN_ROOT', None)
        self.cron_file = self.root / 'crontab'
        self.env['CRON_FILE'] = str(self.cron_file)
        executable(self.bin / 'crontab', CRONTAB)
        executable(self.bin / 'claude', '#!/bin/sh\nexit 0\n')
        (self.home / '.claude').mkdir()

    def isolated_path(self, *args, code=2):
        empty = self.root / 'empty-bin'
        empty.mkdir(exist_ok=True)
        env = dict(self.env, PATH=str(empty))
        result = subprocess.run([sys.executable, str(SCRIPTS / 'install-schedule'), *args],
                                cwd=self.work, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        return result

    def launchd_job(self):
        output = self.run_script('install-schedule', '--scheduler', 'launchd').stdout
        return plistlib.loads(output[output.index('<?xml'):].encode())

    def test_absolute_python_and_runner(self):
        line = self.run_script('install-schedule', '--scheduler', 'cron').stdout.strip()
        tokens = shlex.split(line)
        command = shlex.split(tokens[tokens.index('-c') + 1])
        self.assertEqual(command[0], sys.executable)
        self.assertEqual(command[1], str(self.home / '.claude/bin/kaizen-scheduled'))
        self.assertEqual(command[2], 'audit')

    def test_environment_unset(self):
        for scheduler in ('cron', 'launchd'):
            output = self.run_script('install-schedule', '--scheduler', scheduler).stdout
            self.assertNotIn('CLAUDE_CONFIG_DIR', output)
            self.assertNotIn('CODEX_HOME', output)
        self.assertEqual(self.launchd_job()['EnvironmentVariables'], {'PATH': self.env['PATH']})

    def test_environment_set_and_custom_paths(self):
        claude = self.root / 'claude config'
        codex = self.root / 'codex config'
        claude.mkdir()
        codex.mkdir()
        self.env.update(CLAUDE_CONFIG_DIR=str(claude), CODEX_HOME=str(codex))
        job = self.launchd_job()
        for key in ('PATH', 'CLAUDE_CONFIG_DIR', 'CODEX_HOME'):
            self.assertEqual(job['EnvironmentVariables'][key], self.env[key])
        command = shlex.split(job['ProgramArguments'][2])
        self.assertIn(str(claude / 'bin/kaizen-scheduled'), command)
        self.assertIn(str(claude / 'audits/run.log'), command)
        output = self.run_script('install-schedule', '--scheduler', 'cron', '--review').stdout
        for line in output.splitlines():
            tokens = shlex.split(line)
            self.assertIn('env', tokens)
            for key in ('CLAUDE_CONFIG_DIR', 'CODEX_HOME'):
                self.assertIn(f'{key}={self.env[key]}', tokens)

    def test_apply_twice_remove_preserves_foreign_lines_and_links(self):
        foreign = 'PATH=/x\n5 4 * * * echo foreign\n'
        write(self.cron_file, foreign + '0 9 */3 * * old-audit # agent-kaizen-audit\n'
              + '0 9 * * 1 claude -p old-cycle # agent-kaizen-review\n')
        for _ in range(2):
            result = self.run_script('install-schedule', '--scheduler', 'cron', '--apply', '--review')
            self.assertIn('would ', result.stdout)
            self.assertIn('OK kaizen-scheduled', result.stdout)
            self.assertLess(result.stdout.index('would '), result.stdout.index('OK kaizen-scheduled'))
            contents = self.cron_file.read_text()
            self.assertTrue(contents.startswith(foreign))
            self.assertEqual(contents.count('PATH='), 3)  # foreign + two inline assignments
            self.assertEqual(contents.count('# agent-kaizen-audit'), 1)
            self.assertEqual(contents.count('# agent-kaizen-review'), 1)
        for source, target in (('kaizen-scheduled', 'kaizen-scheduled'), ('token-audit', 'kaizen-token-audit'),
                               ('kaizen-backup', 'kaizen-backup'), ('pricing.json', 'kaizen-pricing.json')):
            self.assertEqual((self.home / '.claude/bin' / target).read_bytes(),
                             (SCRIPTS / source).read_bytes())
        self.assertTrue(os.access(self.home / '.claude/bin/kaizen-scheduled', os.X_OK))
        self.assertTrue((self.home / '.claude/bin/kaizen-scheduled').is_symlink())
        check = subprocess.run([sys.executable, str(self.home / '.claude/bin/kaizen-link'), '--check'],
                               env=self.env, capture_output=True, text=True)
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        self.assertIn('0 drift, 0 broken', check.stdout)
        self.assertNotIn('old-', contents)
        record = self.home / '.claude/bin/.kaizen-plugin-root'
        self.assertTrue(record.is_file())
        self.isolated_remove_without_claude()
        self.assertEqual(self.cron_file.read_text(), foreign)
        self.assertFalse(record.exists())

    def test_install_refuses_symlinked_plugin_root_record(self):
        target = write(self.root / 'plugin-source', 'untouched\n')
        record = self.home / '.claude/bin/.kaizen-plugin-root'
        record.parent.mkdir()
        for destination in (target, self.root / 'missing'):
            with self.subTest(destination=destination):
                record.symlink_to(destination)
                result = self.run_script('install-schedule', '--scheduler', 'cron', '--apply', code=2)
                self.assertIn('refusing symlinked plugin-root record', result.stderr)
                self.assertEqual(target.read_text(), 'untouched\n')
                self.assertFalse((self.root / 'missing').exists())
                self.assertTrue(record.is_symlink())
                record.unlink()

    def test_remove_unlinks_symlinked_plugin_root_record(self):
        target = write(self.root / 'plugin-source', 'untouched\n')
        record = self.home / '.claude/bin/.kaizen-plugin-root'
        record.parent.mkdir()
        record.symlink_to(target)
        self.run_script('install-schedule', '--scheduler', 'cron', '--remove')
        self.assertFalse(record.is_symlink())
        self.assertEqual(target.read_text(), 'untouched\n')

    def test_install_replaces_prefixed_preserves_generic_and_existing_link(self):
        target = self.home / '.claude/bin'
        original = (SCRIPTS / 'kaizen-scheduled').read_bytes()
        write(target / 'kaizen-scheduled', 'old runner')
        write(target / 'rules-lint', 'foreign tool')
        (target / 'kaizen-backup').symlink_to(SCRIPTS / 'kaizen-backup')
        write(self.home / '.claude/agent-kaizen.json', '{"localScripts":["notes-ledger"]}')
        result = self.install(code=1)
        self.assertEqual(next(target.glob('kaizen-scheduled.replaced-*')).read_text(), 'old runner')
        self.assertTrue((target / 'kaizen-scheduled').is_symlink())
        self.assertEqual((SCRIPTS / 'kaizen-scheduled').read_bytes(), original)
        self.assertEqual((target / 'rules-lint').read_text(), 'foreign tool')
        self.assertFalse(list(target.glob('rules-lint.replaced-*')))
        self.assertIn('DRIFT rules-lint', result.stdout)
        self.assertIn('skip LOCAL notes-ledger', result.stdout)
        self.assertFalse((target / 'notes-ledger').exists())

    def test_cache_install_replaces_stale_credentials_module(self):
        plugin = self.root / 'plugins/cache/agent-kaizen/version'
        shutil.copytree(SCRIPTS, plugin / 'scripts')
        command = [sys.executable, str(plugin / 'scripts/install-schedule'), '--scheduler', 'cron', '--apply']
        first = subprocess.run(command, env=self.env, capture_output=True, text=True)
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        installed = self.home / '.claude/bin/kaizen_credentials.py'
        installed.write_text('stale module')
        result = subprocess.run(command, env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(installed.read_bytes(), (plugin / 'scripts/kaizen_credentials.py').read_bytes())
        self.assertEqual(next(installed.parent.glob('kaizen_credentials.py.replaced-*')).read_text(), 'stale module')

    def test_cache_install_reports_unresolved_dependency_drift(self):
        plugin = self.root / 'plugins/cache/agent-kaizen/version'
        shutil.copytree(SCRIPTS, plugin / 'scripts')
        command = [sys.executable, str(plugin / 'scripts/install-schedule'), '--scheduler', 'cron', '--apply']
        first = subprocess.run(command, env=self.env, capture_output=True, text=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        for name in ('packet-report', 'notes-ledger', 'token-audit'):
            (plugin / 'scripts' / name).write_text('changed')
        result = subprocess.run(command, env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        for name in ('packet-report', 'notes-ledger', 'token-audit'):
            self.assertIn('DRIFT ' + name, result.stdout)

    def test_cache_install_copies_dependencies_and_survives_plugin_move(self):
        plugin = self.root / 'plugins/cache/agent-kaizen/version'
        shutil.copytree(SCRIPTS, plugin / 'scripts')
        custom = self.root / 'custom-config'
        self.env['CLAUDE_CONFIG_DIR'] = str(custom)
        result = subprocess.run([sys.executable, str(plugin / 'scripts/install-schedule'),
                                 '--scheduler', 'cron', '--apply'],
                                env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        target = custom / 'bin'
        self.assertIn('would copy kaizen-scheduled', result.stdout)
        self.assertFalse((target / 'kaizen-scheduled').is_symlink())
        check = subprocess.run([sys.executable, str(target / 'kaizen-link'), '--check'],
                               env=self.env, capture_output=True, text=True)
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        loader = importlib.machinery.SourceFileLoader('installed_scheduled', str(target / 'kaizen-scheduled'))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        with patch.dict(os.environ, self.env, clear=True):
            options = module.command_options(module.argparse.Namespace(dry_run=True))
            module.run_checks(custom / 'audits', options)
        checks = next((custom / 'audits').glob('checks-*.md')).read_text()
        drift = checks.split('## Drift\n\n', 1)[1].split('\n\n##', 1)[0]
        self.assertIn('OK kaizen-scheduled', drift)
        self.assertIn('kaizen-link: 0 drift, 0 broken', drift)
        self.assertNotIn('unavailable:', drift)
        self.assertFalse((self.home / '.claude/hooks').exists())
        shutil.rmtree(plugin)
        for name in ('usage-series', 'kaizen-scheduled', 'kaizen-backup'):
            help_result = subprocess.run([sys.executable, str(target / name), '--help'],
                                         env=self.env, capture_output=True, text=True)
            self.assertEqual(help_result.returncode, 0, help_result.stderr)

    def test_install_preserves_preexisting_runner_symlink_source(self):
        target = self.home / '.claude/bin/kaizen-scheduled'
        target.parent.mkdir(parents=True)
        target.symlink_to(SCRIPTS / 'kaizen-scheduled')
        original = target.read_bytes()
        self.install()
        self.assertTrue(target.is_symlink())
        self.assertEqual((SCRIPTS / 'kaizen-scheduled').read_bytes(), original)
        self.assertEqual(target.resolve(), SCRIPTS / 'kaizen-scheduled')
        loader = importlib.machinery.SourceFileLoader('linked_scheduled', str(target))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        with patch.dict(os.environ, self.env, clear=True):
            output = module.run_drift(module.argparse.Namespace(python=sys.executable))
        self.assertIn('kaizen-link: 0 drift, 0 broken', output)

    def test_custom_bin_passes_explicit_hooks_dir(self):
        module = self.load_schedule()
        module.BIN = self.root / 'other/bin'
        with patch.dict(os.environ, self.env, clear=True), patch.object(module.subprocess, 'run') as run:
            run.return_value = subprocess.CompletedProcess([], 0)
            with patch.object(module, 'cron', return_value=0):
                self.assertEqual(module.main(['--scheduler', 'cron', '--apply']), 0)
        commands = [call.args[0] for call in run.call_args_list]
        for command in commands:
            self.assertEqual(command[command.index('--hooks-dir') + 1], str(self.root / 'other/hooks'))
            self.assertIn('--replace-prefixed', command)
            self.assertNotIn('--replace', command)

    def isolated_remove_without_claude(self):
        empty = self.root / 'empty-bin'
        executable(empty / 'crontab', CRONTAB.replace('#!/usr/bin/env python3', '#!' + sys.executable))
        self.isolated_path('--scheduler', 'cron', '--remove', code=0)

    def test_review_requires_claude(self):
        for flag in ('--review', '--auto'):
            result = self.isolated_path('--scheduler', 'launchd', flag)
            self.assertIn('claude not found on PATH; install Claude Code or put it on PATH, then re-run',
                          result.stderr)
        self.run_script('install-schedule', '--scheduler', 'cron', '--review')

    def test_missing_crontab(self):
        result = self.isolated_path('--scheduler', 'cron')
        self.assertIn('crontab not found', result.stderr)
        self.assertIn('0 9 */3 * * env ', result.stderr)
        self.assertIn('# agent-kaizen-audit', result.stderr)

    def review_command(self, *args):
        output = self.run_script('install-schedule', '--scheduler', 'cron', '--review', *args).stdout
        line = next(line for line in output.splitlines() if line.endswith('# agent-kaizen-review'))
        tokens = shlex.split(line)
        return shlex.split(tokens[tokens.index('-c') + 1])

    def test_review_runner_arguments(self):
        command = self.review_command()
        self.assertEqual(command[:3], [sys.executable, str(self.home / '.claude/bin/kaizen-scheduled'), 'review'])
        self.assertEqual(command[command.index('--claude') + 1], str(self.bin / 'claude'))
        self.assertEqual(command[command.index('--python') + 1], sys.executable)
        for forbidden in ('cycle', 'propose-only', '--tools', '--allowedTools', 'acceptEdits',
                          '--project-dir', '--model', '--max-turns'):
            self.assertNotIn(forbidden, command)
        command = self.review_command('--project-dir', str(self.work), '--project-dir', str(self.root),
                                      '--model', 'test-model', '--max-turns', '7')
        self.assertEqual([command[i + 1] for i, word in enumerate(command) if word == '--project-dir'],
                         [str(self.work), str(self.root)])
        self.assertEqual(command[command.index('--model') + 1], 'test-model')
        self.assertEqual(command[command.index('--max-turns') + 1], '7')
        self.env.update(KAIZEN_REVIEW_MODEL='env-model', KAIZEN_REVIEW_MAX_TURNS='9')
        command = self.review_command()
        self.assertEqual(command[command.index('--model') + 1], 'env-model')
        self.assertEqual(command[command.index('--max-turns') + 1], '9')

    def install(self, *args, code=0):
        return self.run_script('install-schedule', '--scheduler', 'cron', '--apply', *args, code=code)

    def project(self, name):
        path = self.root / name
        (path / 'docs/kaizen').mkdir(parents=True)
        return path

    def test_auto_global_and_custom_home(self):
        for custom in (False, True):
            home = self.root / 'custom config' if custom else self.home / '.claude'
            if custom:
                self.env['CLAUDE_CONFIG_DIR'] = str(home)
            self.install('--auto', 'all')
            self.assertEqual(json.loads((home / 'agent-kaizen.json').read_text())['scheduledAutonomy'], 'auto')

    def test_project_auto_none_and_bare(self):
        one, two = self.project('one'), self.project('two')
        self.install('--auto', str(one), str(two))
        global_file = self.home / '.claude/agent-kaizen.json'
        # A project's auto only takes effect once the global file lists the project.
        self.assertEqual(json.loads(global_file.read_text()), {'autoProjects': [str(one), str(two)]})
        for path in (one, two):
            self.assertEqual(json.loads((path / 'docs/kaizen/config.json').read_text())['scheduledAutonomy'], 'auto')
        write(global_file, '{ "scheduledAutonomy": "propose", "autonomy": "propose" }\n')
        self.install('--auto', str(one), str(two))
        self.assertEqual(json.loads(global_file.read_text()), {
            'scheduledAutonomy': 'propose', 'autonomy': 'propose', 'autoProjects': [str(one), str(two)]})
        before = (one / 'docs/kaizen/config.json').read_bytes()
        result = self.install('--auto', 'none', '--project-dir', str(one))
        self.assertEqual(json.loads(global_file.read_text())['scheduledAutonomy'], 'propose')
        self.assertIn(str(one), result.stdout)
        self.assertIn('scheduledAutonomy=propose', result.stdout)
        self.assertLess(result.stdout.index('installed:'),
                        result.stdout.index('Remaining project-level auto opt-ins:'))
        self.assertEqual((one / 'docs/kaizen/config.json').read_bytes(), before)
        result = self.install('--auto', '--project-dir', str(two))
        self.assertIn(f'--auto without a value now means: auto mode for {two} only', result.stdout)
        self.install('--auto', 'all', str(one), code=2)
        result = self.install('--auto', str(self.work), code=2)
        self.assertIn('docs/kaizen', result.stderr)

    def test_print_only_and_no_auto_preserve_config(self):
        config = write(self.home / '.claude/agent-kaizen.json', '{ "autonomy": "propose", "scheduledAutonomy": "auto" }\n')
        before = config.read_bytes()
        result = self.run_script('install-schedule', '--scheduler', 'cron', '--auto', 'none')
        self.assertIn('config set scheduledAutonomy=propose', result.stdout)
        self.assertEqual(config.read_bytes(), before)
        self.install('--review')
        self.assertEqual(config.read_bytes(), before)

    def test_environment_reaches_runner_and_claude(self):
        claude, codex = self.root / 'claude config', self.root / 'codex config'
        self.env.update(CLAUDE_CONFIG_DIR=str(claude), CODEX_HOME=str(codex))
        project = self.project('env project')
        write(project / 'docs/kaizen/config.json', '{"schedule":"always"}')
        executable(self.bin / 'claude', '#!' + sys.executable +                    '\nimport os, pathlib, json\npathlib.Path(' + repr(str(self.record)) +                    ').write_text(json.dumps({k:os.environ.get(k) for k in ("CLAUDE_CONFIG_DIR","CODEX_HOME")}))\n')
        self.install('--review', '--project-dir', str(project))
        output = self.run_script('install-schedule', '--scheduler', 'cron', '--review',
                                 '--project-dir', str(project)).stdout
        line = next(line for line in output.splitlines() if line.endswith('# agent-kaizen-review'))
        rest = line.split(' ', 5)[5].rsplit(' # agent-kaizen-review', 1)[0]
        result = subprocess.run(['/bin/sh', '-c', rest], env={'HOME': str(self.home)},
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr + (claude / 'audits/run.log').read_text())
        self.assertEqual(json.loads(self.record.read_text()),
                         dict(CLAUDE_CONFIG_DIR=str(claude), CODEX_HOME=str(codex)))

    def load_schedule(self):
        loader = importlib.machinery.SourceFileLoader('schedule', str(SCRIPTS / 'install-schedule'))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(os.environ, self.env, clear=True):
            loader.exec_module(module)
        return module

    def test_windows_and_non_darwin_launchd_mutations(self):
        schedule = self.load_schedule()
        with patch.object(schedule.platform, 'system', return_value='Windows'):
            self.assertEqual(schedule.main([]), 2)
        for system, args in (('Linux', ['--scheduler', 'launchd', '--apply']),
                             ('Linux', ['--scheduler', 'launchd', '--remove'])):
            with self.subTest(system=system, args=args), patch.object(schedule.platform, 'system', return_value=system):
                with self.assertRaises(SystemExit) as raised:
                    schedule.main(args)
                self.assertEqual(raised.exception.code, 2)

    def test_crontab_disappears_after_lookup(self):
        schedule = self.load_schedule()
        with patch.object(schedule.shutil, 'which', return_value='/missing/crontab'), \
                patch.object(schedule.subprocess, 'run', side_effect=FileNotFoundError):
            self.assertEqual(schedule.main(['--scheduler', 'cron']), 2)

    def test_nonzero_crontab_ignores_stdout(self):
        schedule = self.load_schedule()
        result = subprocess.CompletedProcess(['crontab', '-l'], 1, stdout='discard this\n',
                                            stderr='no crontab for user\n')
        ok = subprocess.CompletedProcess([], 0)
        with patch.object(schedule.shutil, 'which', return_value=str(self.bin / 'crontab')), \
                patch.object(schedule.subprocess, 'run', side_effect=[ok, ok, ok, result, ok]) as run:
            self.assertEqual(schedule.main(['--scheduler', 'cron', '--apply']), 0)
        self.assertNotIn('discard this', run.call_args.kwargs['input'])

    def test_cron_quotes_and_escapes_environment(self):
        self.env['CODEX_HOME'] = str(self.root / "config's 50%")
        output = self.run_script('install-schedule', '--scheduler', 'cron', '--review').stdout
        for line in output.splitlines():
            self.assertNotIn('%', line.replace('\\%', ''))
            tokens = shlex.split(line.replace('\\%', '%'))
            self.assertIn('CODEX_HOME=' + self.env['CODEX_HOME'], tokens)
            command = tokens[tokens.index('-c') + 1]
            self.assertIn('kaizen-scheduled', command)

    def systemd_setup(self, cron=False):
        self.env['PATH'] = str(self.bin)
        (self.bin / 'python3').symlink_to(sys.executable)
        if not cron:
            (self.bin / 'crontab').unlink()
        self.env['XDG_CONFIG_HOME'] = str(self.root / 'custom config')
        self.env['SYSTEMD_LOG'] = str(self.root / 'systemd.jsonl')
        for name, body in (('systemctl', SYSTEMCTL), ('loginctl', LOGINCTL)):
            executable(self.bin / name, body.format(python=sys.executable))
        return Path(self.env['XDG_CONFIG_HOME']) / 'systemd/user'

    def linux_schedule(self, *args, code=0):
        # Exercise auto selection on Linux even when the test host is macOS.
        bootstrap = ('import platform, runpy, sys; platform.system = lambda: "Linux"; '
                     'sys.argv = sys.argv[1:]; runpy.run_path(sys.argv[0], run_name="__main__")')
        result = subprocess.run([sys.executable, '-c', bootstrap, str(SCRIPTS / 'install-schedule'), *args],
                                env=self.env, cwd=self.work, capture_output=True, text=True)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        return result

    def systemd_calls(self):
        path = Path(self.env['SYSTEMD_LOG'])
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_systemd_units_apply_remove_and_linger(self):
        directory = self.systemd_setup()
        self.env['STUB_LINGER'] = 'Linger=no'
        result = self.linux_schedule('--scheduler', 'systemd', '--apply', '--review')
        self.assertEqual(len(list(directory.iterdir())), 4)
        for name, calendar in (('audit', '*-*-01/3 09:00:00'), ('review', 'Mon *-*-* 09:00:00')):
            timer = (directory / f'agent-kaizen-{name}.timer').read_text()
            self.assertIn(f'OnCalendar={calendar}\nPersistent=true\n', timer)
            self.assertEqual(timer.split('[Install]\n')[1], 'WantedBy=timers.target\n')
            service = (directory / f'agent-kaizen-{name}.service').read_text()
            self.assertIn('Type=oneshot\n', service)
            self.assertIn(f'Environment="PATH={self.env["PATH"]}"', service)
            command = shlex.split(service.split("ExecStart=/bin/sh -c '")[1].strip()[:-1])
            self.assertTrue(Path(command[0]).is_absolute())
            self.assertTrue(Path(command[1]).is_absolute())
        self.assertIn('loginctl enable-linger ', result.stdout)
        self.assertTrue(result.stdout.rstrip().endswith("Check the timers: systemctl --user list-timers 'agent-kaizen-*'"))
        calls = self.systemd_calls()
        reload_index = calls.index(['--user', 'daemon-reload'])
        for name in ('audit', 'review'):
            self.assertGreater(calls.index(['--user', 'enable', '--now', f'agent-kaizen-{name}.timer']), reload_index)
        self.assertFalse(any('enable-linger' in call for call in calls))
        before = {path.name: path.read_bytes() for path in directory.iterdir()}
        self.env['STUB_LINGER'] = 'Linger=yes'
        result = self.linux_schedule('--scheduler', 'systemd', '--apply', '--review')
        self.assertNotIn('loginctl enable-linger', result.stdout)
        self.assertEqual(before, {path.name: path.read_bytes() for path in directory.iterdir()})
        self.env['STUB_DISABLE_EXIT'] = '1'
        self.linux_schedule('--remove')
        self.assertEqual(list(directory.iterdir()), [])
        calls = self.systemd_calls()
        self.assertEqual(calls[-1], ['--user', 'daemon-reload'])
        for name in ('audit', 'review'):
            self.assertIn(['--user', 'disable', '--now', f'agent-kaizen-{name}.timer'], calls)

    def test_systemd_escaping_and_cron_round_trip(self):
        self.systemd_setup(cron=True)
        self.env['CLAUDE_CONFIG_DIR'] = str(self.root / "c%d$e's config")
        self.env['CODEX_HOME'] = str(self.root / 'codex')
        args = ['--review', '--project-dir', str(self.root / "p%$'q")]
        output = self.linux_schedule('--scheduler', 'systemd', *args).stdout
        self.assertIn('Environment="CLAUDE_CONFIG_DIR=' + self.env['CLAUDE_CONFIG_DIR'].replace('%', '%%') + '"', output)
        self.assertIn('Environment="CODEX_HOME=' + self.env['CODEX_HOME'] + '"', output)
        cron = self.linux_schedule('--scheduler', 'cron', *args).stdout
        cron_commands = [shlex.split(line.replace('\\%', '%')) for line in cron.splitlines()]
        for line, tokens in zip((line for line in output.splitlines() if line.startswith('ExecStart=')), cron_commands):
            self.assertIn('%%', line)
            self.assertIn('$$', line)
            # Decode systemd C escapes and specifiers, then compare the exact shell command.
            command = line[len("ExecStart=/bin/sh -c '"):-1]
            command = re.sub(r'\\([\\\'"nrt])', lambda m: {'n': '\n', 'r': '\r', 't': '\t'}.get(m[1], m[1]), command)
            command = command.replace('%%', '%').replace('$$', '$')
            self.assertEqual(command, tokens[tokens.index('-c') + 1])

    def test_systemd_escape_helper(self):
        schedule = self.load_schedule()
        self.assertEqual(schedule.unit_escape('a\\b"c%d$e'), 'a\\\\b\\"c%%d$e')
        self.assertEqual(schedule.unit_escape('a\\b"c%d$e', exec=True), 'a\\\\b\\"c%%d$$e')
        self.assertEqual(schedule.unit_escape("a'b", exec=True), r"a\'b")

    def test_systemd_auto_detection_and_cron_priority(self):
        self.systemd_setup()
        self.env['STUB_STATE'] = 'degraded'
        result = self.linux_schedule()
        self.assertIn('agent-kaizen-audit.service', result.stdout)
        self.env['STUB_STATE'] = 'offline'
        result = self.linux_schedule(code=2)
        self.assertIn('schedule these jobs by hand', result.stderr)
        self.assertIn('kaizen-scheduled audit', result.stderr)
        result = self.linux_schedule('--scheduler', 'systemd', '--apply', code=2)
        self.assertIn('offline', result.stderr)
        executable(self.bin / 'crontab', CRONTAB)
        Path(self.env['SYSTEMD_LOG']).unlink()
        result = self.linux_schedule()
        self.assertIn('# agent-kaizen-audit', result.stdout)
        self.assertEqual(self.systemd_calls(), [])

    def test_systemd_print_needs_no_tools_or_writes(self):
        directory = self.systemd_setup()
        (self.bin / 'systemctl').unlink()
        (self.bin / 'loginctl').unlink()
        result = self.linux_schedule('--scheduler', 'systemd', '--review')
        self.assertIn('agent-kaizen-review.service', result.stdout)
        self.assertNotIn('CLAUDE_CONFIG_DIR', result.stdout)
        self.assertNotIn('CODEX_HOME', result.stdout)
        self.assertFalse(Path(self.env['XDG_CONFIG_HOME']).exists())
        self.assertEqual(self.systemd_calls(), [])
        for flag in ('--apply', '--remove'):
            result = self.linux_schedule('--scheduler', 'systemd', flag, code=2)
            self.assertIn('systemctl not found', result.stderr)
        self.assertFalse(directory.exists())

    def test_systemd_migration_remove_preserves_cron_bytes(self):
        directory = self.systemd_setup(cron=True)
        self.linux_schedule('--scheduler', 'systemd', '--apply', '--review')
        foreign = 'PATH=/x\n5 4 * * * echo foreign'  # Preserve even a missing final newline.
        self.cron_file.write_text('old # agent-kaizen-audit\nold # agent-kaizen-review\n' + foreign)
        self.linux_schedule('--remove')
        self.assertEqual(self.cron_file.read_bytes(), foreign.encode())
        self.assertEqual(list(directory.iterdir()), [])
        self.assertEqual(self.systemd_calls()[-1], ['--user', 'daemon-reload'])

    def test_systemd_remove_without_systemctl_still_cleans_cron_and_units(self):
        directory = self.systemd_setup(cron=True)
        self.linux_schedule('--scheduler', 'systemd', '--apply', '--review')
        self.cron_file.write_text('old # agent-kaizen-audit\nkeep\n')
        (self.bin / 'systemctl').unlink()
        result = self.linux_schedule('--remove', code=2)
        self.assertEqual(self.cron_file.read_text(), 'keep\n')
        self.assertEqual(list(directory.iterdir()), [])
        self.assertIn('daemon-reload failed', result.stderr)

    def test_systemd_failing_systemctl_reports_without_traceback(self):
        self.systemd_setup()
        self.env['STUB_FAIL'] = 'enable'
        result = self.linux_schedule('--scheduler', 'systemd', '--apply', '--review', code=2)
        self.assertIn('enable --now agent-kaizen-audit.timer failed', result.stderr)

    def test_systemd_default_config_without_loginctl_and_auto_none(self):
        self.systemd_setup()
        self.env.pop('XDG_CONFIG_HOME')
        (self.bin / 'loginctl').unlink()
        result = self.linux_schedule('--scheduler', 'systemd', '--apply', '--auto', 'none')
        directory = self.home / '.config/systemd/user'
        self.assertEqual(len(list(directory.iterdir())), 4)
        self.assertNotIn('loginctl enable-linger', result.stdout)
        self.assertTrue(result.stdout.rstrip().endswith("Check the timers: systemctl --user list-timers 'agent-kaizen-*'"))

    def test_systemd_analyze_when_available(self):
        analyze = shutil.which('systemd-analyze')
        if not analyze:
            self.skipTest('systemd-analyze is not installed')
        directory = self.systemd_setup()
        self.env['CLAUDE_CONFIG_DIR'] = str(self.root / "c%d$e's config")
        self.linux_schedule('--scheduler', 'systemd', '--apply', '--review')
        for expression in ('*-*-01/3 09:00:00', 'Mon *-*-* 09:00:00'):
            result = subprocess.run([analyze, 'calendar', expression], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        for service in directory.glob('*.service'):
            result = subprocess.run([analyze, 'verify', str(service)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
