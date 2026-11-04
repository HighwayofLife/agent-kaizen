"""Offline integration checks for scheduled reports and unattended permissions."""
from datetime import datetime, timezone
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from unittest.mock import patch

from test_scripts import SCRIPTS, StubCase, executable, write


class ScheduleStepsTests(StubCase):
    def setUp(self):
        super().setUp()
        self.scripts = self.root / 'plugin/scripts'
        self.scripts.mkdir(parents=True)
        self.runner = self.scripts / 'kaizen-scheduled'
        shutil.copy2(SCRIPTS / 'kaizen-scheduled', self.runner)
        self.config = self.root / 'config'
        self.audits = self.config / 'audits'
        self.project = self.root / 'project'
        (self.project / 'docs/kaizen').mkdir(parents=True)
        shutil.copy(SCRIPTS.parent / 'tests/fixtures/packets.jsonl',
                    write(self.project / 'out/packets.jsonl', ''))
        self.env.update(CLAUDE_CONFIG_DIR=str(self.config), CODEX_HOME=str(self.root / 'codex'))
        self.env['CLAUDE_PLUGIN_ROOT'] = str(self.scripts.parent)
        self.env.pop('KAIZEN_SKIP_CHECKS', None)
        write(self.scripts / 'pricing.json', '{}')
        self.stub('token-audit', """
import pathlib, sys
out = pathlib.Path(sys.argv[sys.argv.index('--out') + 1])
out.mkdir(parents=True, exist_ok=True)
report = out / 'token-audit-stub.md'
report.write_text('token report')
print(report)
""")
        self.stub('kaizen-link', """
import os, sys
print('DRIFT example')
for n in range(35): print('drift line ' + str(n))
sys.exit(int(os.environ.get('LINK_EXIT', '1')))
""")
        self.stub('rules-lint', """
import os, sys
print('rules-lint: 1 stale-rule hit(s)')
sys.exit(int(os.environ.get('LINT_EXIT', '1')))
""")
        self.stub('notes-ledger', """
import os, sys
print('measurement proposal')
sys.exit(int(os.environ.get('LEDGER_EXIT', '0')))
""")
        self.stub('kaizen-project-report', """
import json, pathlib, sys
out = pathlib.Path(sys.argv[sys.argv.index('--out') + 1])
out.write_text('project report regenerated')
""")
        self.claude = executable(self.bin / 'claude', '#!' + sys.executable + "\n" + """
import json, os, pathlib, sys
report = pathlib.Path(sys.argv[2].split(' ', 2)[2])
assert report.read_text() == 'token report'
assert list(report.parent.glob('project-report-*.md'))[0].read_text() == 'project report regenerated'
pathlib.Path(os.environ['RECORD']).write_text(json.dumps(sys.argv[1:]))
print('proposal')
""")
        loader = importlib.machinery.SourceFileLoader('scheduled_steps', str(self.runner))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        self.module = importlib.util.module_from_spec(spec)
        loader.exec_module(self.module)

    def stub(self, name, body):
        return executable(self.scripts / name, '#!' + sys.executable + '\n' + body)

    def index(self):
        write(self.audits / 'projects/index.json', json.dumps({
            'v': 1, 'projects': {str(self.project): self.module.key(self.project)}}))

    def run_scheduled(self, command, *args):
        result = subprocess.run([sys.executable, str(self.runner), command, *map(str, args)],
                                env=self.env, cwd=self.work, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def check_text(self):
        return next(self.audits.glob('checks-*.md')).read_text()

    def test_audit_reports_findings_and_step_failure(self):
        self.index()
        self.env['LEDGER_EXIT'] = '1'
        result = self.run_scheduled('audit')
        text = self.check_text()
        for heading in ('Drift', 'Stale rules', 'Notes ledger: measurements due'):
            self.assertIn('## ' + heading, text)
        self.assertIn('DRIFT example', text)
        self.assertIn('rules-lint: 1 stale-rule hit(s)', text)
        self.assertIn('unavailable: exit 1', text)
        self.assertNotIn('drift line 29', text)
        self.assertIn('step notes-ledger: failed (exit 1', result.stdout)
        self.assertEqual(len(list(self.audits.glob('projects/*/project-report-*.md'))), 1)

    def test_check_exit_two_is_unavailable(self):
        self.env.update(LINK_EXIT='2', LINT_EXIT='2')
        result = self.run_scheduled('audit')
        self.assertEqual(self.check_text().count('unavailable: exit 2'), 2)
        self.assertIn('step kaizen-link: failed (exit 2', result.stdout)
        self.assertIn('step rules-lint: failed (exit 2', result.stdout)

    def test_success_output_and_crashed_project_step_keep_audit_status(self):
        self.index()
        self.env.update(LINK_EXIT='0', LINT_EXIT='0')
        self.stub('kaizen-project-report', 'raise RuntimeError("broken report")\n')
        result = self.run_scheduled('audit')
        self.assertIn('DRIFT example', self.check_text())
        self.assertNotIn('unavailable:', self.check_text())
        self.assertIn('step kaizen-project-report: failed (exit 1', result.stdout)

    def test_fresh_audit_discovers_and_indexes_project(self):
        write(self.config / 'projects/session/one.jsonl', json.dumps({'cwd': str(self.project)}) + '\n')
        self.assertFalse((self.audits / 'projects/index.json').exists())
        self.run_scheduled('audit')
        index = json.loads((self.audits / 'projects/index.json').read_text())['projects']
        self.assertEqual(index[str(self.project)], self.module.key(self.project))
        self.assertEqual(len(list(self.audits.glob('projects/*/project-report-*.md'))), 1)

    def test_skip_checks_and_missing_siblings(self):
        self.index()
        self.env['KAIZEN_SKIP_CHECKS'] = '1'
        self.run_scheduled('audit')
        self.assertFalse(list(self.audits.glob('checks-*.md')))
        self.assertFalse(list(self.audits.glob('projects/*/project-report-*.md')))
        self.env.pop('KAIZEN_SKIP_CHECKS')
        for name in ('kaizen-link', 'rules-lint', 'notes-ledger', 'kaizen-project-report'):
            (self.scripts / name).unlink()
        result = self.run_scheduled('audit')
        self.assertNotIn('step ', result.stdout)
        self.assertFalse(list(self.audits.glob('checks-*.md')))

    def review(self, *args):
        return self.run_scheduled('review', '--project-dir', self.project, '--claude', self.claude, *args)

    def test_review_regenerates_report_and_forces_propose(self):
        write(self.config / 'agent-kaizen.json', '{"scheduledAutonomy":"auto"}')
        self.review()
        self.assertFalse(self.record.exists())  # no activity
        self.review('--propose-only', '--force')
        command = json.loads(self.record.read_text())
        report = self.audits / 'projects' / self.module.key(self.project) / 'token-audit-stub.md'
        self.assertEqual(command[1], f'/agent-kaizen:cycle propose-only {report}')
        self.assertEqual(command[command.index('--allowedTools') + 1], self.module.REVIEW_TOOLS)
        self.assertEqual(command[command.index('--tools') + 1], self.module.REVIEW_AVAILABLE)
        self.assertNotIn('--disallowedTools', command)
        self.assertEqual(command[command.index('--permission-mode') + 1], 'dontAsk')

    def test_force_preserves_off_and_disabled_and_requires_selection(self):
        self.index()
        self.run_scheduled('review', '--force', '--claude', self.claude)
        self.assertFalse(self.record.exists())
        write(self.project / 'docs/kaizen/config.json', '{"schedule":"off"}')
        self.review('--force')
        self.assertFalse(self.record.exists())
        write(self.config / 'agent-kaizen.json', '{"enabled":false}')
        self.review('--force')
        self.assertFalse(self.record.exists())

    def test_skip_checks_in_review(self):
        executable(self.claude, '#!' + sys.executable + '\nprint("proposal")\n')
        self.env['KAIZEN_SKIP_CHECKS'] = '1'
        self.review('--propose-only', '--force')
        self.assertFalse(list(self.audits.glob('checks-*.md')))
        self.assertFalse(list(self.audits.glob('projects/*/project-report-*.md')))

    def test_force_and_propose_dry_run(self):
        write(self.config / 'agent-kaizen.json', '{"scheduledAutonomy":"auto"}')
        result = self.review('--force', '--propose-only', '--dry-run')
        self.assertIn('gate: due (forced)', result.stdout)
        self.assertIn('/agent-kaizen:cycle propose-only', result.stdout)
        self.assertFalse(self.audits.exists())

    def test_auto_ledger_allow_and_deny_fail_closed(self):
        csv, timeline = self.root / 'ledger.csv', self.root / 'timeline.md'
        write(self.config / 'agent-kaizen.json', json.dumps({'notesLedger': {
            'csv': str(csv), 'timeline': str(timeline)}}))
        with patch.dict(os.environ, self.env, clear=True):
            options = self.module.command_options(self.module.argparse.Namespace(dry_run=True))
            command = self.module.review_command(options, 'auto', 'report', 'session', self.project)
            allowed = command[command.index('--allowedTools') + 1]
            for python in ('python3', options.python):
                self.assertIn(f'Bash({python} {self.scripts}/notes-ledger add:*)', allowed)
            self.assertNotIn('notes-ledger set', allowed)
            self.assertNotIn('Bash(git log:*)', allowed)
            self.assertNotIn('Bash(git diff:*)', allowed)
            self.assertNotIn('Bash(git log:*)', self.module.REVIEW_TOOLS)
            self.assertNotIn('Bash(git diff:*)', self.module.REVIEW_TOOLS)
            deny = command[command.index('--disallowedTools') + 1].split(',')
            for path in (csv, timeline):
                for tool in ('Edit', 'Write'):
                    self.assertIn(f'{tool}(//{path.as_posix().lstrip("/")})', deny)
            for rule in [*self.module.HARD_STOP_DENY.split(','), *self.module.config_home_deny(self.project)]:
                self.assertIn(rule, deny)
            propose = self.module.review_command(options, 'propose-only', 'report', 'session')
            self.assertEqual(propose[propose.index('--allowedTools') + 1], self.module.REVIEW_TOOLS)
            write(self.config / 'agent-kaizen.json', json.dumps({'notesLedger': {'csv': str(csv) + '('}}))
            with self.assertRaisesRegex(ValueError, 'cannot build deny rules'):
                self.module.review_command(options, 'auto', 'report', 'session')

    def configure_ledgers(self, mode='auto'):
        from test_notes_ledger import HEADER, TIMELINE
        self.csv = write(self.root / 'ledger.csv', HEADER + '2026-10-01,test,Existing,manual,active,no\n')
        self.timeline = write(self.root / 'timeline.md', TIMELINE)
        self.original_ledgers = self.csv.read_bytes(), self.timeline.read_bytes()
        write(self.config / 'agent-kaizen.json', json.dumps({
            'scheduledAutonomy': mode, 'notesLedger': {
                'csv': str(self.csv), 'timeline': str(self.timeline)}}))
        self.env.update(CSV=str(self.csv), TIMELINE=str(self.timeline))

    def guard_result(self, code):
        result = subprocess.run([sys.executable, str(self.runner), 'review', '--force',
                                 '--project-dir', str(self.project), '--claude', str(self.claude)],
                                env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result

    def assert_ledger_violation(self):
        folder = self.audits / 'projects' / self.module.key(self.project)
        state = json.loads((folder / 'state.json').read_text())
        self.assertEqual(state['status'], 'ledger-violation')
        self.assertNotIn('reviewed_at', state)
        self.assertTrue(state['ledger_errors'])
        self.assertIn('ledger-violation', next(folder.glob('cycle-*.failed.md')).read_text())
        self.assertFalse(list(folder.glob('cycle-????-??-??.md')))
        return state

    def test_guard_restores_git_log_truncation_in_both_modes(self):
        for mode in ('auto', 'propose'):
            with self.subTest(mode=mode):
                self.configure_ledgers(mode)
                executable(self.claude, '#!' + sys.executable + '\n' + """
import os, subprocess
subprocess.run(['git', 'init', '-q'], check=True)
env = dict(os.environ, GIT_AUTHOR_NAME='Test', GIT_COMMITTER_NAME='Test',
           GIT_AUTHOR_EMAIL='test@example.invalid', GIT_COMMITTER_EMAIL='test@example.invalid')
subprocess.run(['git', '-c', 'commit.gpgsign=false', 'commit', '--allow-empty', '-qm', 'fixture'],
               env=env, check=True)
subprocess.run(['git', 'log', '--output=' + os.environ['CSV']], check=True)
print('model returned success')
""")
                result = self.guard_result(1)
                self.assertIn('restored snapshot', result.stdout)
                self.assertEqual(self.csv.read_bytes(), self.original_ledgers[0])
                state = self.assert_ledger_violation()
                self.assertIn(str(self.csv), '\n'.join(state['ledger_errors']))

    def test_guard_accepts_real_notes_ledger_add(self):
        shutil.copy2(SCRIPTS / 'notes-ledger', self.scripts / 'notes-ledger')
        for mode in ('auto', 'propose'):
            with self.subTest(mode=mode):
                self.configure_ledgers(mode)
                self.env['LEDGER_SCRIPT'] = str(self.scripts / 'notes-ledger')
                executable(self.claude, '#!' + sys.executable + '\n' + """
import hashlib, json, os, pathlib, stat, subprocess, sys
report = pathlib.Path(sys.argv[2].split(' ', 2)[2])
snapshot = next(report.parent.glob('.ledger-*'))
assert stat.S_IMODE(snapshot.stat().st_mode) == 0o700
manifest = json.loads((snapshot / 'manifest.json').read_text())
assert {entry['kind'] for entry in manifest} == {'csv', 'timeline'}
for entry in manifest:
    original = pathlib.Path(entry['path']).read_bytes()
    assert pathlib.Path(entry['snapshot']).read_bytes() == original
    assert entry['size'] == len(original)
    assert entry['sha256'] == hashlib.sha256(original).hexdigest()
subprocess.run([sys.executable, os.environ['LEDGER_SCRIPT'], 'add', '--date', '2026-10-03',
                '--category', 'test', '--change', 'New change', '--why', 'because',
                '--measure', 'count', '--source', 'manual'], check=True)
""")
                self.guard_result(0)
                self.assertTrue(self.csv.read_bytes().startswith(self.original_ledgers[0]))
                self.assertIn(b'New change', self.csv.read_bytes())
                self.assertIn(b'New change', self.timeline.read_bytes())
                self.assertFalse(self.timeline.read_bytes().startswith(self.original_ledgers[1]))
                folder = self.audits / 'projects' / self.module.key(self.project)
                self.assertEqual(json.loads((folder / 'state.json').read_text())['status'], 'ok')
                self.assertFalse(list(folder.glob('.ledger-*')))

    def test_guard_restores_missing_changed_or_partial_ledgers(self):
        mutations = ["csv.unlink()", "csv.write_bytes(b'x' * len(csv.read_bytes()))",
                     "csv.write_bytes(csv.read_bytes() + b'partial')",
                     "timeline.write_bytes(b''.join(reversed(timeline.read_bytes().splitlines(keepends=True))))",
                     "timeline.unlink()"]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.configure_ledgers()
                executable(self.claude, '#!' + sys.executable + '\n' +
                           'import os\nfrom pathlib import Path\n' +
                           'csv, timeline = Path(os.environ["CSV"]), Path(os.environ["TIMELINE"])\n' +
                           mutation + '\n')
                self.guard_result(1)
                self.assertEqual((self.csv.read_bytes(), self.timeline.read_bytes()), self.original_ledgers)
                self.assert_ledger_violation()

    def test_guard_fails_closed_on_unreadable_source(self):
        self.configure_ledgers()
        read_bytes = Path.read_bytes

        def guarded_read(path):
            if path == self.csv:
                raise PermissionError('unreadable fixture')
            return read_bytes(path)

        with patch.dict(os.environ, self.env, clear=True), \
                patch.object(Path, 'read_bytes', guarded_read), \
                patch.object(self.module, 'scheduled_housekeep') as housekeep:
            code = self.module.main(['review', '--force', '--project-dir', str(self.project),
                                     '--claude', str(self.claude)])
        self.assertEqual(code, 1)
        housekeep.assert_not_called()
        self.assertFalse(self.record.exists())
        state = self.assert_ledger_violation()
        self.assertIn('unreadable fixture', '\n'.join(state['ledger_errors']))

    def test_guard_restores_when_run_truncates_ledgers_and_snapshots(self):
        self.configure_ledgers()
        executable(self.claude, '#!' + sys.executable + '\n' + """
import json, pathlib, sys
report = pathlib.Path(sys.argv[2].split(' ', 2)[2])
snapshot = next(report.parent.glob('.ledger-*'))
for entry in json.loads((snapshot / 'manifest.json').read_text()):
    pathlib.Path(entry['path']).write_bytes(b'')
    pathlib.Path(entry['snapshot']).write_bytes(b'')
""")
        self.guard_result(1)
        self.assertEqual((self.csv.read_bytes(), self.timeline.read_bytes()), self.original_ledgers)
        self.assert_ledger_violation()

    def test_guard_rejects_symlinked_ledgers_before_launch(self):
        for kind in ('csv', 'timeline'):
            with self.subTest(kind=kind):
                self.configure_ledgers()
                path = getattr(self, kind)
                target = path.with_suffix('.target')
                path.rename(target)
                path.symlink_to(target)
                self.guard_result(1)
                self.assertFalse(self.record.exists())
                self.assertTrue(path.is_symlink())
                self.assertEqual(target.read_bytes(), self.original_ledgers[kind == 'timeline'])
                state = self.assert_ledger_violation()
                self.assertIn('regular file, not a symlink', '\n'.join(state['ledger_errors']))
                path.unlink()

    def test_guard_accepts_timeline_last_line_without_newline(self):
        self.configure_ledgers()
        self.timeline.write_bytes(b'first\r\nlast')
        executable(self.claude, '#!' + sys.executable + '\n' +
                   'import os\nfrom pathlib import Path\n' +
                   'Path(os.environ["TIMELINE"]).write_bytes(b"first\\ninserted\\nlast\\nnew row\\n")\n')
        self.guard_result(0)
        self.assertIn(b'new row', self.timeline.read_bytes())

    def test_bad_global_config_blocks_review_and_cycle(self):
        read_text = Path.read_text
        for fixture in ('{', '[]', 'unreadable'):
            with self.subTest(fixture=fixture):
                path = write(self.config / 'agent-kaizen.json', fixture)

                def guarded_read(candidate, *args, **kwargs):
                    if candidate == path and fixture == 'unreadable':
                        raise PermissionError('unreadable fixture')
                    return read_text(candidate, *args, **kwargs)

                with patch.dict(os.environ, self.env, clear=True), \
                        patch.object(Path, 'read_text', guarded_read), \
                        patch.object(self.module, 'run_review') as review, \
                        patch.object(self.module, 'scheduled_housekeep') as housekeep:
                    code = self.module.main(['review', '--force', '--project-dir', str(self.project),
                                             '--claude', str(self.claude)])
                    options = self.module.command_options(self.module.argparse.Namespace(dry_run=True))
                    with self.assertRaisesRegex(ValueError, 'scheduled review blocked'):
                        self.module.review_command(options, 'auto', 'report', 'session')
                self.assertEqual(code, 2)
                review.assert_not_called()
                housekeep.assert_not_called()
                self.assertFalse(self.record.exists())

    def test_violation_write_errors_skip_later_projects_and_housekeeping(self):
        later = self.root / 'z-project'
        (later / 'docs/kaizen').mkdir(parents=True)
        original_open, original_state = Path.open, self.module.write_state
        for failure in ('report', 'state'):
            with self.subTest(failure=failure):
                self.configure_ledgers()

                def guarded_open(path, mode='r', *args, **kwargs):
                    if failure == 'report' and path.name.startswith('cycle-') and mode == 'a':
                        raise OSError('report write fixture')
                    return original_open(path, mode, *args, **kwargs)

                def guarded_state(project, state):
                    if failure == 'state' and state.get('status') == 'ledger-violation':
                        raise OSError('state write fixture')
                    return original_state(project, state)

                with patch.dict(os.environ, self.env, clear=True), \
                        patch.object(self.module.LedgerGuard, 'verify', return_value=['violation fixture']), \
                        patch.object(Path, 'open', guarded_open), \
                        patch.object(self.module, 'write_state', guarded_state), \
                        patch.object(self.module, 'scheduled_housekeep') as housekeep:
                    code = self.module.main(['review', '--force', '--project-dir', str(self.project),
                                             '--project-dir', str(later), '--claude', str(self.claude)])
                self.assertEqual(code, 2)
                housekeep.assert_not_called()
                later_folder = self.audits / 'projects' / self.module.key(later)
                self.assertFalse((later_folder / 'state.json').exists())

    def test_guard_error_stops_later_projects_and_housekeeping(self):
        self.configure_ledgers()
        later = self.root / 'z-project'
        (later / 'docs/kaizen').mkdir(parents=True)
        with patch.dict(os.environ, self.env, clear=True), \
                patch.object(self.module.LedgerGuard, 'verify', side_effect=RuntimeError('guard error')), \
                patch.object(self.module, 'scheduled_housekeep') as housekeep:
            code = self.module.main(['review', '--force', '--project-dir', str(self.project),
                                     '--project-dir', str(later), '--claude', str(self.claude)])
        self.assertEqual(code, 1)
        housekeep.assert_not_called()
        self.assert_ledger_violation()
        later_folder = self.audits / 'projects' / self.module.key(later)
        self.assertFalse((later_folder / 'state.json').exists())

    def test_invalid_raw_ledger_fails_closed(self):
        for ledger in ({'csv': '/x', 'bogus': 1}, {'timeline': '/x'}, ['csv'], 'csv'):
            with self.subTest(ledger=ledger):
                write(self.config / 'agent-kaizen.json', json.dumps({'notesLedger': ledger}))
                with patch.dict(os.environ, self.env, clear=True):
                    options = self.module.command_options(self.module.argparse.Namespace(dry_run=True))
                    with self.assertRaisesRegex(ValueError, 'notesLedger.*invalid'):
                        self.module.review_command(options, 'auto', 'report', 'session')

    def test_ledger_paths_must_be_absolute(self):
        for name in ('csv', 'timeline'):
            ledger = {'csv': str(self.root / 'ledger.csv'), name: 'relative/ledger'}
            with self.subTest(name=name), patch.dict(os.environ, self.env, clear=True):
                self.assertFalse(self.module.valid_value('notesLedger', ledger))
                result = subprocess.run([sys.executable, str(self.runner), 'config', 'set',
                                         'notesLedger=' + json.dumps(ledger)],
                                        env=self.env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                write(self.config / 'agent-kaizen.json', json.dumps({'notesLedger': ledger}))
                with self.assertRaisesRegex(ValueError, 'absolute'):
                    self.module.ledger_deny()
                options = self.module.command_options(self.module.argparse.Namespace(dry_run=True))
                with self.assertRaisesRegex(ValueError, 'absolute'):
                    self.module.review_command(options, 'auto', 'report', 'session')
        with patch.dict(os.environ, self.env, clear=True):
            self.assertTrue(self.module.valid_value('notesLedger', {'csv': '~/ledger.csv'}))

    def test_auto_backup_allows_only_non_restoring_subcommands(self):
        self.stub('kaizen-backup', '')
        with patch.dict(os.environ, self.env, clear=True):
            options = self.module.command_options(self.module.argparse.Namespace(dry_run=True))
            command = self.module.review_command(options, 'auto', 'report', 'session')
        rules = command[command.index('--allowedTools') + 1].split(',')
        backup = self.scripts / 'kaizen-backup'
        expected = {f'Bash({prefix}{backup} {subcommand}:*)'
                    for prefix in ('', 'python3 ', options.python + ' ')
                    for subcommand in ('begin', 'finish', 'list')}
        self.assertEqual({rule for rule in rules if 'kaizen-backup' in rule}, expected)

    def test_ledger_symlink_names_and_targets_are_denied(self):
        csv = write(self.root / 'ledger-target.csv', '')
        timeline = write(self.root / 'timeline-target.md', '')
        links = [self.root / 'ledger.csv', self.root / 'timeline.md']
        for link, target in zip(links, (csv, timeline)):
            link.symlink_to(target)
        write(self.config / 'agent-kaizen.json', json.dumps({'notesLedger': {
            'csv': str(links[0]), 'timeline': str(links[1])}}))
        with patch.dict(os.environ, self.env, clear=True):
            options = self.module.command_options(self.module.argparse.Namespace(dry_run=True))
            command = self.module.review_command(options, 'auto', 'report', 'session')
        deny = command[command.index('--disallowedTools') + 1].split(',')
        for path in (*links, csv, timeline):
            for tool in ('Edit', 'Write'):
                self.assertIn(f'{tool}(//{path.as_posix().lstrip("/")})', deny)

    def test_drift_uses_environment_plugin_root_before_install_record(self):
        write(self.scripts / '.kaizen-plugin-root', str(self.root / 'old-plugin'))
        self.stub('kaizen-link', """
import os, sys
assert sys.argv[1:] == ['--check', '--plugin-root', os.environ['CLAUDE_PLUGIN_ROOT']]
print('checked environment plugin root')
""")
        with patch.dict(os.environ, self.env, clear=True):
            options = self.module.command_options(self.module.argparse.Namespace(dry_run=True))
            self.module.run_checks(self.audits, options)
        self.assertIn('checked environment plugin root', self.check_text())
        self.assertNotIn('unavailable:', self.check_text())

    def test_drift_without_plugin_root_is_unavailable(self):
        self.env.pop('CLAUDE_PLUGIN_ROOT')
        with patch.dict(os.environ, self.env, clear=True):
            options = self.module.command_options(self.module.argparse.Namespace(dry_run=True))
            self.module.run_checks(self.audits, options)
        self.assertIn('## Drift\n\nunavailable: plugin root unknown', self.check_text())
        self.assertNotIn('DRIFT example', self.check_text())

    def test_new_report_retention_families(self):
        current = datetime(2026, 11, 4, tzinfo=timezone.utc)
        families = ('checks', 'token-audit', 'projects/a/project-report', 'projects/a/cycle',
                    'projects/b/project-report')
        for family in families:
            for n in range(7):
                path = write(self.audits / f'{family}-{n}.md', 'report')
                stamp = current.timestamp() - (407 - n) * 86400
                os.utime(path, (stamp, stamp))
        with patch.dict(os.environ, self.env, clear=True):
            plan = self.module.housekeep(self.audits, self.module.effective(), now=current)
        self.assertEqual(len(plan), 10)
        for family in families:
            for n in range(7):
                self.assertEqual((self.audits / f'{family}-{n}.md').exists(), n >= 2)

    def test_real_project_report_packet_sections(self):
        for name in ('kaizen-project-report', 'packet-report'):
            shutil.copy2(SCRIPTS / name, self.scripts / name)
        self.index()
        self.run_scheduled('audit')
        text = next(self.audits.glob('projects/*/project-report-*.md')).read_text()
        self.assertIn('## Packet outcomes', text)
        self.assertIn('## Calibration', text)
