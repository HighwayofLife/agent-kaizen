"""install-schedule: declarative review job, backup dir env, scheduler failures."""
import json
import os
import plistlib
import subprocess
import sys
from pathlib import Path

from test_scripts import StubCase, write, executable
from test_schedule import CRONTAB, SYSTEMCTL, LOGINCTL, SCRIPTS

LAUNCHCTL = '''#!{python}
import json, os, sys
with open(os.environ['LAUNCH_LOG'], 'a') as stream:
    stream.write(json.dumps(sys.argv[1:]) + '\\n')
if os.environ.get('STUB_FAIL') in sys.argv:
    sys.stderr.write('launchctl: boom\\n')
    sys.exit(5)
'''
REMOVED = 'removed review job (not requested; pass --review to keep it)'
WOULD = 'would remove review job (not requested; pass --review to keep it)'
# Pretend to be Darwin or Linux whatever the host is.
BOOTSTRAP = ('import platform, runpy, sys; name = sys.argv[1]; platform.system = lambda: name; '
             'sys.argv = sys.argv[2:]; runpy.run_path(sys.argv[0], run_name="__main__")')


class InstallScheduleTests(StubCase):
    def setUp(self):
        super().setUp()
        for name in ('CLAUDE_CONFIG_DIR', 'CODEX_HOME', 'KAIZEN_REVIEW_MODEL',
                     'KAIZEN_REVIEW_MAX_TURNS', 'CLAUDE_PLUGIN_ROOT', 'KAIZEN_BACKUP_DIR', 'KAIZEN_USAGE_DB'):
            self.env.pop(name, None)
        self.cron_file = self.root / 'crontab'
        self.env['CRON_FILE'] = str(self.cron_file)
        self.env['LAUNCH_LOG'] = str(self.root / 'launch.jsonl')
        self.env['SYSTEMD_LOG'] = str(self.root / 'systemd.jsonl')
        self.env['XDG_CONFIG_HOME'] = str(self.root / 'xdg')
        executable(self.bin / 'crontab', CRONTAB)
        executable(self.bin / 'claude', '#!/bin/sh\nexit 0\n')
        executable(self.bin / 'launchctl', LAUNCHCTL.format(python=sys.executable))
        (self.bin / 'python3').symlink_to(sys.executable)
        for name, body in (('systemctl', SYSTEMCTL), ('loginctl', LOGINCTL)):
            executable(self.bin / name, body.format(python=sys.executable))
        (self.home / '.claude').mkdir()
        self.agents = self.home / 'Library/LaunchAgents'
        self.units = self.root / 'xdg/systemd/user'

    def schedule(self, system, *args, code=0):
        result = subprocess.run([sys.executable, '-c', BOOTSTRAP, system,
                                 str(SCRIPTS / 'install-schedule'), *args],
                                env=self.env, cwd=self.work, capture_output=True, text=True)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        return result

    def launch_calls(self):
        path = Path(self.env['LAUNCH_LOG'])
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    # S-6: --apply without --review removes an installed review job.
    def test_launchd_apply_without_review_removes_review(self):
        first = self.schedule('Darwin', '--scheduler', 'launchd', '--apply')
        self.assertNotIn('review', first.stdout)
        self.schedule('Darwin', '--scheduler', 'launchd', '--apply', '--review')
        audit, review = (self.agents / f'com.agent-kaizen.{n}.plist' for n in ('audit', 'review'))
        self.assertTrue(review.exists())
        preview = self.schedule('Darwin', '--scheduler', 'launchd')
        self.assertIn(WOULD, preview.stdout)
        self.assertTrue(review.exists())
        result = self.schedule('Darwin', '--scheduler', 'launchd', '--apply')
        self.assertIn(REMOVED, result.stdout)
        self.assertFalse(review.exists())
        self.assertTrue(audit.exists())
        self.assertIn(['bootout', f'gui/{os.getuid()}', str(review)], self.launch_calls())
        self.assertNotIn(REMOVED, self.schedule('Darwin', '--scheduler', 'launchd', '--apply').stdout)

    def test_cron_apply_without_review_removes_review(self):
        write(self.cron_file, '5 4 * * * echo foreign\n')
        first = self.schedule('Linux', '--scheduler', 'cron', '--apply')
        self.assertNotIn('review', first.stdout.replace('Preview', ''))
        self.schedule('Linux', '--scheduler', 'cron', '--apply', '--review')
        self.assertIn('# agent-kaizen-review', self.cron_file.read_text())
        preview = self.schedule('Linux', '--scheduler', 'cron')
        self.assertIn(WOULD, preview.stdout)
        result = self.schedule('Linux', '--scheduler', 'cron', '--apply')
        self.assertIn(REMOVED, result.stdout)
        text = self.cron_file.read_text()
        self.assertNotIn('# agent-kaizen-review', text)
        self.assertEqual(text.count('# agent-kaizen-audit'), 1)
        self.assertIn('echo foreign', text)
        self.assertNotIn(REMOVED, self.schedule('Linux', '--scheduler', 'cron', '--apply').stdout)

    def test_systemd_apply_without_review_removes_review(self):
        (self.bin / 'crontab').unlink()
        first = self.schedule('Linux', '--scheduler', 'systemd', '--apply')
        self.assertNotIn(REMOVED, first.stdout)
        self.schedule('Linux', '--scheduler', 'systemd', '--apply', '--review')
        self.assertTrue((self.units / 'agent-kaizen-review.timer').exists())
        preview = self.schedule('Linux', '--scheduler', 'systemd')
        self.assertIn(WOULD, preview.stdout)
        result = self.schedule('Linux', '--scheduler', 'systemd', '--apply')
        self.assertIn(REMOVED, result.stdout)
        self.assertEqual(sorted(p.name for p in self.units.iterdir()),
                         ['agent-kaizen-audit.service', 'agent-kaizen-audit.timer'])
        log = [json.loads(line) for line in Path(self.env['SYSTEMD_LOG']).read_text().splitlines()]
        self.assertIn(['--user', 'disable', '--now', 'agent-kaizen-review.timer'], log)
        self.assertNotIn(REMOVED, self.schedule('Linux', '--scheduler', 'systemd', '--apply').stdout)

    def warnings(self, result):
        return [line for line in result.stderr.splitlines() if 'review job is still installed' in line]

    def test_apply_warns_about_review_jobs_in_other_backends(self):
        self.schedule('Linux', '--scheduler', 'systemd', '--apply', '--review')
        self.schedule('Darwin', '--scheduler', 'launchd', '--apply', '--review')
        self.schedule('Linux', '--scheduler', 'cron', '--apply', '--review')
        result = self.schedule('Linux', '--scheduler', 'cron', '--apply')
        lines = self.warnings(result)
        self.assertEqual(len(lines), 2, result.stderr)
        self.assertTrue(any('launchd' in l and 'launchctl bootout' in l and 'com.agent-kaizen.review.plist' in l
                            for l in lines))
        self.assertTrue(any('systemd' in l and 'systemctl --user disable --now agent-kaizen-review.timer' in l
                            for l in lines))
        again = self.warnings(self.schedule('Linux', '--scheduler', 'systemd', '--apply'))
        self.assertEqual(len(again), 1)
        self.assertIn('launchd', again[0])
        self.assertEqual(self.warnings(self.schedule('Linux', '--scheduler', 'cron')), [])

    def test_apply_warns_about_a_cron_review_job_from_systemd(self):
        self.schedule('Linux', '--scheduler', 'cron', '--apply', '--review')
        result = self.schedule('Linux', '--scheduler', 'systemd', '--apply')
        lines = self.warnings(result)
        self.assertEqual(len(lines), 1, result.stderr)
        self.assertIn('cron', lines[0])
        self.assertIn("grep -v '# agent-kaizen-review$' | crontab -", lines[0])

    def test_no_warning_without_a_foreign_review_job_or_with_review(self):
        self.schedule('Linux', '--scheduler', 'systemd', '--apply', '--review')
        self.assertEqual(self.warnings(self.schedule('Linux', '--scheduler', 'cron', '--apply', '--review')), [])
        (self.cron_file).unlink()
        self.schedule('Linux', '--scheduler', 'systemd', '--apply')
        self.assertEqual(self.warnings(self.schedule('Linux', '--scheduler', 'cron', '--apply')), [])

    def test_auto_keeps_review(self):
        self.schedule('Linux', '--scheduler', 'cron', '--apply', '--review')
        result = self.schedule('Linux', '--scheduler', 'cron', '--apply', '--auto', 'none')
        self.assertNotIn(REMOVED, result.stdout)
        self.assertIn('# agent-kaizen-review', self.cron_file.read_text())

    # S-13: KAIZEN_BACKUP_DIR is recorded.
    def test_backup_dir_recorded(self):
        backup = self.root / 'my backups'
        self.env['KAIZEN_BACKUP_DIR'] = str(backup)
        output = self.schedule('Darwin', '--scheduler', 'launchd').stdout
        job = plistlib.loads(output[output.index('<?xml'):].encode())
        self.assertEqual(job['EnvironmentVariables']['KAIZEN_BACKUP_DIR'], str(backup))
        self.assertIn(f"KAIZEN_BACKUP_DIR='{backup}'", self.schedule('Linux', '--scheduler', 'cron').stdout)
        del self.env['KAIZEN_BACKUP_DIR']
        self.assertNotIn('KAIZEN_BACKUP_DIR', self.schedule('Linux', '--scheduler', 'cron').stdout)

    def test_usage_db_recorded(self):
        store = self.root / 'usage store' / 'usage.db'
        self.env['KAIZEN_USAGE_DB'] = str(store)
        output = self.schedule('Darwin', '--scheduler', 'launchd').stdout
        job = plistlib.loads(output[output.index('<?xml'):].encode())
        self.assertEqual(job['EnvironmentVariables']['KAIZEN_USAGE_DB'], str(store))
        self.assertIn(f"KAIZEN_USAGE_DB='{store}'", self.schedule('Linux', '--scheduler', 'cron').stdout)
        del self.env['KAIZEN_USAGE_DB']
        self.assertNotIn('KAIZEN_USAGE_DB', self.schedule('Linux', '--scheduler', 'cron').stdout)

    # S-15: errors, not tracebacks.
    def test_launchctl_bootstrap_failure(self):
        self.env['STUB_FAIL'] = 'bootstrap'
        result = self.schedule('Darwin', '--scheduler', 'launchd', '--apply', '--auto', 'all', code=2)
        lines = result.stderr.strip().splitlines()
        self.assertEqual(lines[0], 'launchctl: boom')  # the tool's own message
        self.assertEqual(len(lines), 2, result.stderr)
        self.assertTrue(lines[1].startswith('install-schedule: '), result.stderr)
        self.assertNotIn('config', result.stdout)

    def test_write_failure(self):
        self.agents.parent.mkdir(parents=True)
        write(self.agents, 'a file, not a directory')
        result = self.schedule('Darwin', '--scheduler', 'launchd', '--apply', code=2)
        self.assertEqual(len(result.stderr.strip().splitlines()), 1, result.stderr)

    def test_crontab_list_failure_does_not_write(self):
        executable(self.bin / 'crontab', '#!/bin/sh\n'
                   'if [ "$1" = -l ]; then echo "crontab: temporary failure" >&2; exit 1; fi\n'
                   'echo written > "$CRON_FILE"\n')
        for flags in (('--apply',), ('--remove',)):
            result = self.schedule('Linux', '--scheduler', 'cron', *flags, code=2)
            self.assertIn('crontab', result.stderr)
            self.assertFalse(self.cron_file.exists())

    def test_no_crontab_message_is_empty_crontab(self):
        executable(self.bin / 'crontab', '#!/bin/sh\n'
                   'if [ "$1" = -l ]; then echo "crontab: No Crontab for me" >&2; exit 1; fi\n'
                   'cat > "$CRON_FILE"\n')
        self.schedule('Linux', '--scheduler', 'cron', '--apply')
        self.assertIn('# agent-kaizen-audit', self.cron_file.read_text())

    # V1-1: a refused opt-in surfaces and fails the command.
    def test_auto_for_a_nested_project_surfaces_the_refusal(self):
        repo = self.root / 'repo'
        write(repo / 'docs/kaizen/config.json', '{}')
        write(repo / 'pkg/docs/kaizen/config.json', '{}')
        env = dict(self.env, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull,
                   GIT_AUTHOR_NAME='T', GIT_AUTHOR_EMAIL='t@example.invalid',
                   GIT_COMMITTER_NAME='T', GIT_COMMITTER_EMAIL='t@example.invalid')
        for command in (['init'], ['add', '.'], ['commit', '-m', 'init']):
            subprocess.run(['git', '-C', str(repo), *command], env=env, check=True, capture_output=True)
        self.env.update(env)
        result = self.schedule('Linux', '--scheduler', 'cron', '--apply', '--auto', str(repo / 'pkg'), code=2)
        self.assertIn(f'config set --for {repo.resolve()} scheduledAutonomy=auto', result.stderr)
        self.assertFalse((self.home / '.claude/agent-kaizen.json').exists())

    # V1-3: the "no crontab" test must not depend on the user's language.
    def test_crontab_list_runs_in_the_c_locale(self):
        executable(self.bin / 'crontab', '#!/bin/sh\n'
                   'if [ "$1" = -l ]; then\n'
                   '  if [ "$LC_ALL" = C ] && [ "$LANG" = C ]; then echo "no crontab for user" >&2\n'
                   '  else echo "keine crontab fuer Benutzer" >&2; fi\n'
                   '  exit 1\n'
                   'fi\n'
                   'cat > "$CRON_FILE"\n')
        self.env.update(LC_ALL='de_DE.UTF-8', LANG='de_DE.UTF-8')
        self.schedule('Linux', '--scheduler', 'cron', '--apply')
        self.assertIn('# agent-kaizen-audit', self.cron_file.read_text())
