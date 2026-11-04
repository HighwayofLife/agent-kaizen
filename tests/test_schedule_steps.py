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
import unittest
from unittest.mock import patch

from test_scripts import SCRIPTS, StubCase, executable, write


# Independent pins: adding a Bash grant requires reviewing its exec/write flags.
PROPOSE_BASH = (
    'Bash(ls:*)',         # Lists metadata; no command execution or output-file flag.
    'Bash(head:*)',       # Reads initial bytes/lines; writes only stdout.
    'Bash(tail:*)',       # Reads final bytes/lines (or follows); writes only stdout.
    'Bash(shasum:*)',     # Reads/hashes/checks files; no exec or output-file flag.
    'Bash(sha256sum:*)',  # Reads/hashes/checks files; no exec or output-file flag.
)
AUTO_BASH = PROPOSE_BASH + (
    'Bash({backup} begin:*)',           # Copies inputs only into the protected backup root.
    'Bash(python3 {backup} begin:*)',   # Same fixed helper, not arbitrary Python code.
    'Bash({python} {backup} begin:*)',  # Same fixed helper with the runner's interpreter.
    'Bash({backup} finish:*)',          # Writes only a validated backup manifest.
    'Bash(python3 {backup} finish:*)',  # Same manifest-only operation.
    'Bash({python} {backup} finish:*)',  # Same manifest-only operation.
    'Bash({backup} list:*)',            # Prints backup metadata only.
    'Bash(python3 {backup} list:*)',    # Same metadata-only operation.
    'Bash({python} {backup} list:*)',   # Same metadata-only operation.
    'Bash(python3 {ledger} add:*)',     # Appends to configured ledgers; no exec/path override.
    'Bash({python} {ledger} add:*)',    # Same scoped writer with the runner's interpreter.
)

CREDENTIAL_PATHS = {
    'config': ('.credentials.json', 'auth.json', '*token*.json', '*secret*.json'),
    'home': ('.ssh/**', '.aws/**', '.gnupg/**', '.netrc', '.config/gh/**', '.docker/config.json'),
    'project': ('**/.env', '**/.env.*'),
}
FILE_COMMAND_DENIES = (
    'cp', 'touch', 'mkdir', 'sed', 'dd', 'install', 'ln', 'truncate', 'perl', 'python3 -c', 'python',
)


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
report = pathlib.Path(sys.argv[2].rsplit(' notes-ledger-path=', 1)[0].split(' ', 2)[2])
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

    @unittest.skipUnless(shutil.which('git'), 'git required')
    def test_worktree_reports_and_checks_use_only_canonical_project(self):
        self.env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull,
                        GIT_AUTHOR_NAME='Test', GIT_AUTHOR_EMAIL='test@example.invalid',
                        GIT_COMMITTER_NAME='Test', GIT_COMMITTER_EMAIL='test@example.invalid')
        write(self.project / 'docs/kaizen/config.json', '{}')
        worktree = self.root / 'worktree'
        for args in (('init',), ('add', 'docs'), ('commit', '-m', 'enroll'),
                     ('worktree', 'add', '-b', 'linked', str(worktree))):
            subprocess.run(['git', '-C', str(self.project), *args], env=self.env,
                           capture_output=True, check=True)
        # Stale instructions exist only on the worktree branch, as in the audit finding.
        write(worktree / 'docs/agents/history.md', 'project-repos.txt\n')
        shutil.copy2(SCRIPTS / 'rules-lint', self.scripts / 'rules-lint')
        shutil.copy2(SCRIPTS / 'rules-lint.patterns', self.scripts / 'rules-lint.patterns')
        self.env['REPORT_RECORD'] = str(self.root / 'report-calls')
        self.stub('kaizen-project-report', """
import os, pathlib, sys
project = sys.argv[sys.argv.index('--project') + 1]
with open(os.environ['REPORT_RECORD'], 'a') as calls: calls.write(project + '\\n')
pathlib.Path(sys.argv[sys.argv.index('--out') + 1]).write_text(project)
""")
        self.stub('notes-ledger', """
import sys
print(' '.join(sys.argv[1:]))
""")
        # A stale index may contain just the worktree, or both paths with one shared key.
        for paths in ((worktree,), (self.project, worktree)):
            with self.subTest(paths=paths):
                write(self.audits / 'projects/index.json', json.dumps({
                    'v': 1, 'projects': {str(path): self.module.key(self.project) for path in paths}}))
                Path(self.env['REPORT_RECORD']).unlink(missing_ok=True)
                self.run_scheduled('audit')
                self.assertEqual(Path(self.env['REPORT_RECORD']).read_text().splitlines(),
                                 [str(self.project)])
                checks = self.check_text()
                self.assertIn('rules-lint: 0 stale-rule hit(s)', checks)
                self.assertIn('due --project ' + str(self.project), checks)
                self.assertNotIn(str(worktree), checks)
                reports = list(self.audits.glob('projects/*/project-report-*.md'))
                self.assertTrue(reports)
                self.assertTrue(all(path.read_text() == str(self.project) for path in reports))

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
        self.assertEqual(command[1], f'/agent-kaizen:cycle propose-only {report} notes-ledger-path={self.scripts}/notes-ledger')
        self.assertEqual(command[command.index('--allowedTools') + 1], self.module.REVIEW_TOOLS)
        self.assertEqual(command[command.index('--tools') + 1], self.module.REVIEW_AVAILABLE)
        self.assertIn(f'Read(//{self.project.as_posix().lstrip("/")}/**/.env)',
                      command[command.index('--disallowedTools') + 1].split(','))
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
            ledger_path = command[command.index('-p') + 1].split('notes-ledger-path=', 1)[1]
            self.assertEqual(ledger_path, str(self.scripts / 'notes-ledger'))
            self.assertIn(f'Bash(python3 {ledger_path} add:*)', allowed)
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
report = pathlib.Path(sys.argv[2].rsplit(' notes-ledger-path=', 1)[0].split(' ', 2)[2])
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
report = pathlib.Path(sys.argv[2].rsplit(' notes-ledger-path=', 1)[0].split(' ', 2)[2])
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

    def test_guard_reports_ledger_parent_symlink_without_writing_through_it(self):
        self.configure_ledgers()
        folder = self.root / 'ledgers'
        folder.mkdir()
        csv, timeline = folder / self.csv.name, folder / self.timeline.name
        self.csv.rename(csv)
        self.timeline.rename(timeline)
        self.csv, self.timeline = csv, timeline
        write(self.config / 'agent-kaizen.json', json.dumps({
            'scheduledAutonomy': 'auto', 'notesLedger': {
                'csv': str(csv), 'timeline': str(timeline)}}))
        self.env['LEDGER_PARENT'] = str(folder)
        executable(self.claude, '#!' + sys.executable + '\n' + """
import os, pathlib, shutil
folder = pathlib.Path(os.environ['LEDGER_PARENT'])
saved = folder.with_name('saved-ledgers')
outside = folder.with_name('outside-ledgers')
folder.rename(saved)
shutil.copytree(saved, outside)
folder.symlink_to(outside, target_is_directory=True)
""")
        self.guard_result(1)
        self.assertTrue(folder.is_symlink())
        self.assertEqual((csv.read_bytes(), timeline.read_bytes()), self.original_ledgers)
        state = self.assert_ledger_violation()
        self.assertTrue(all('resolved path changed' in error for error in state['ledger_errors']))
        self.assertTrue(all('refusing to restore through it' in error for error in state['ledger_errors']))
        self.assertFalse(list((self.root / 'outside-ledgers').glob('.kaizen-restore-*')))

    def test_guard_restores_identical_replacement_symlinks_after_launch(self):
        for kind in ('csv', 'timeline'):
            with self.subTest(kind=kind):
                self.configure_ledgers()
                self.env['REPLACE_LEDGER'] = kind.upper()
                executable(self.claude, '#!' + sys.executable + '\n' + """
import os, pathlib
path = pathlib.Path(os.environ[os.environ['REPLACE_LEDGER']])
target = path.with_suffix('.target')
target.write_bytes(path.read_bytes())
path.unlink()
path.symlink_to(target)
""")
                path = getattr(self, kind)
                try:
                    self.guard_result(1)
                    self.assertFalse(path.is_symlink())
                    self.assertEqual(path.read_bytes(), self.original_ledgers[kind == 'timeline'])
                    self.assertEqual(path.with_suffix('.target').read_bytes(), path.read_bytes())
                    self.assert_ledger_violation()
                finally:
                    if path.is_symlink():
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

    def test_each_mode_has_exact_vetted_bash_grants(self):
        self.stub('kaizen-backup', '')
        with patch.dict(os.environ, self.env, clear=True):
            options = self.module.command_options(self.module.argparse.Namespace(dry_run=True))
            for mode, pinned in (('propose-only', PROPOSE_BASH), ('auto', AUTO_BASH)):
                with self.subTest(mode=mode):
                    command = self.module.review_command(options, mode, 'report', 'session')
                    bash = {rule for rule in command[command.index('--allowedTools') + 1].split(',')
                            if rule.startswith('Bash(')}
                    expected = {rule.format(backup=self.scripts / 'kaizen-backup',
                                           ledger=self.scripts / 'notes-ledger', python=options.python)
                                for rule in pinned}
                    self.assertEqual(bash, expected)
                    if mode == 'auto':
                        deny = command[command.index('--disallowedTools') + 1].split(',')
                        for tool in ('Edit', 'Write'):
                            self.assertIn(f'{tool}(**/.git/**)', deny)

    def test_auto_uses_default_permissions_and_scoped_edits(self):
        with patch.dict(os.environ, self.env, clear=True):
            options = self.module.command_options(self.module.argparse.Namespace(dry_run=True))
            command = self.module.review_command(options, 'auto', 'report', 'session', self.project)
        self.assertEqual(command[command.index('--permission-mode') + 1], 'default')
        allowed = command[command.index('--allowedTools') + 1].split(',')
        self.assertNotIn('Edit', allowed)
        self.assertNotIn('Write', allowed)
        expected = {f'{tool}(//{path.as_posix().lstrip("/")}/**)'
                    for path in (self.project, self.config, self.root / 'codex')
                    for tool in ('Edit', 'Write')}
        self.assertEqual({rule for rule in allowed if rule.startswith(('Edit(', 'Write('))}, expected)

    def test_file_command_hard_stops_preserve_exact_python_helpers(self):
        self.stub('kaizen-backup', '')
        with patch.dict(os.environ, self.env, clear=True):
            options = self.module.command_options(self.module.argparse.Namespace(dry_run=True))
            command = self.module.review_command(options, 'auto', 'report', 'session', self.project)
        allowed = command[command.index('--allowedTools') + 1].split(',')
        denied = command[command.index('--disallowedTools') + 1].split(',')
        for name in FILE_COMMAND_DENIES:
            self.assertIn(f'Bash({name}:*)', denied)

        def matches_prefix(rule, invocation):
            # Check the command-prefix contract; the opt-in live probe checks the CLI itself.
            if not rule.startswith('Bash(') or not rule.endswith(':*)'):
                return False
            prefix = rule[5:-3]
            return invocation == prefix or invocation.startswith(prefix + ' ')

        for python in ('python3', options.python):
            for helper, operation in (('notes-ledger', 'add'), ('kaizen-backup', 'begin'),
                                      ('kaizen-backup', 'finish'), ('kaizen-backup', 'list')):
                invocation = f'{python} {self.scripts / helper} {operation} --help'
                self.assertTrue(any(matches_prefix(rule, invocation) for rule in allowed), invocation)
                self.assertFalse(any(matches_prefix(rule, invocation) for rule in denied), invocation)
        for invocation in ('python3 -c pass', 'python arbitrary.py', 'cp source target'):
            self.assertTrue(any(matches_prefix(rule, invocation) for rule in denied), invocation)
            self.assertFalse(any(matches_prefix(rule, invocation) for rule in allowed), invocation)

    def test_config_git_and_settings_denies_cover_aliases_and_targets(self):
        for name in ('CLAUDE_CONFIG_DIR', 'CODEX_HOME'):
            target = self.root / (name.lower() + '-target')
            target.mkdir()
            alias = self.root / (name.lower() + '-alias')
            alias.symlink_to(target, target_is_directory=True)
            self.env[name] = str(alias)
        with patch.dict(os.environ, self.env, clear=True):
            options = self.module.command_options(self.module.argparse.Namespace(dry_run=True))
            command = self.module.review_command(options, 'auto', 'report', 'session', self.project)
        denied = command[command.index('--disallowedTools') + 1].split(',')
        allowed = command[command.index('--allowedTools') + 1].split(',')
        for name in ('CLAUDE_CONFIG_DIR', 'CODEX_HOME'):
            alias = Path(self.env[name])
            for path in (alias, alias.resolve()):
                root = '//' + path.as_posix().lstrip('/')
                for tool in ('Edit', 'Write'):
                    self.assertIn(f'{tool}({root}/**/.git/**)', denied)
                    self.assertIn(f'{tool}({root}/settings*.json)', denied)
                    self.assertIn(f'{tool}({root}/**)', allowed)

    def test_both_modes_pin_credentials_and_deny_resolved_and_unresolved_paths(self):
        self.assertEqual(self.module.CREDENTIAL_PATHS, CREDENTIAL_PATHS)
        config_target = self.root / 'real-config'
        config_target.mkdir()
        alias = self.root / 'config-alias'
        alias.symlink_to(config_target, target_is_directory=True)
        self.env['CLAUDE_CONFIG_DIR'] = str(alias)
        ssh_target = self.root / 'real-ssh'
        ssh_target.mkdir()
        (self.home / '.ssh').symlink_to(ssh_target, target_is_directory=True)
        credential = write(self.root / 'credential-target', 'private')
        for name in ('.credentials.json', 'access-token.json', 'client-secret.json'):
            (config_target / name).symlink_to(credential)
        with patch.dict(os.environ, self.env, clear=True):
            options = self.module.command_options(self.module.argparse.Namespace(dry_run=True))
            for mode in ('auto', 'propose-only'):
                command = self.module.review_command(options, mode, 'report', 'session', self.project)
                denied = set(command[command.index('--disallowedTools') + 1].split(','))
                roots = {'config': (alias, config_target, self.root / 'codex'),
                         'home': (self.home,), 'project': (self.project,)}
                for scope, patterns in CREDENTIAL_PATHS.items():
                    for root in roots[scope]:
                        for pattern in patterns:
                            for tool in ('Read', 'Edit', 'Write'):
                                self.assertIn(f'{tool}(//{root.as_posix().lstrip("/")}/{pattern})', denied)
                for path, suffix in ((ssh_target, '/**'), (credential, '')):
                    for tool in ('Read', 'Edit', 'Write'):
                        self.assertIn(f'{tool}(//{path.as_posix().lstrip("/")}{suffix})', denied)

    def test_backup_root_deny_covers_resolved_and_unresolved_trees(self):
        resolved = self.root / 'real-backups'
        resolved.mkdir()
        alias = self.root / 'backup-alias'
        alias.symlink_to(resolved, target_is_directory=True)
        self.env['KAIZEN_BACKUP_DIR'] = str(alias)
        with patch.dict(os.environ, self.env, clear=True):
            options = self.module.command_options(self.module.argparse.Namespace(dry_run=True))
            command = self.module.review_command(options, 'auto', 'report', 'session')
        deny = command[command.index('--disallowedTools') + 1].split(',')
        for root in (resolved, alias):
            for tool in ('Edit', 'Write'):
                self.assertIn(f'{tool}(//{root.as_posix().lstrip("/")}/**)', deny)

    def backup_cycle(self, finish='no', exit_code='0'):
        shutil.copy2(SCRIPTS / 'kaizen-backup', self.scripts / 'kaizen-backup')
        self.env.update(KAIZEN_BACKUP_DIR=str(self.root / 'backups'),
                        BACKUP_SCRIPT=str(self.scripts / 'kaizen-backup'),
                        FINISH_BACKUP=finish, CYCLE_EXIT=exit_code,
                        CHANGE_RECORD=str(self.root / 'changes.json'),
                        TARGET=str(write(self.project / 'instructions.md', 'original')))
        write(self.config / 'agent-kaizen.json', '{"scheduledAutonomy":"auto"}')
        executable(self.claude, '#!' + sys.executable + '\n' + """
import json, os, pathlib, subprocess, sys
def backup(*args):
    return subprocess.check_output([sys.executable, os.environ['BACKUP_SCRIPT'], *map(str, args)], text=True).strip()
target = pathlib.Path(os.environ['TARGET'])
changes = []
for number in range(2):
    change = pathlib.Path(backup('begin', '--skill', 'trim', '--ledger', 'test', target))
    changes.append(str(change))
    target.write_text('applied ' + str(number))
    if os.environ['FINISH_BACKUP'] != 'no':
        backup('finish', change, '--verification', os.environ['FINISH_BACKUP'])
pathlib.Path(os.environ['CHANGE_RECORD']).write_text(json.dumps(changes))
print('cycle output')
sys.exit(int(os.environ['CYCLE_EXIT']))
""")

    def backup_state(self):
        folder = self.audits / 'projects' / self.module.key(self.project)
        return folder, json.loads((folder / 'state.json').read_text())

    def test_protected_backup_copy_cannot_be_edited_then_restored(self):
        self.backup_cycle()
        protected = write(self.config / 'settings.json', '{"protected":true}')
        self.env['TARGET'] = str(protected)
        root = self.root / 'real-backups'
        root.mkdir()
        alias = self.root / 'backup-alias'
        alias.symlink_to(root, target_is_directory=True)
        self.env.update(KAIZEN_BACKUP_DIR=str(alias), EXPECTED_BACKUP_ROOT=str(root))
        executable(self.claude, self.claude.read_text().replace(
            "    target.write_text('applied ' + str(number))", """
    import fnmatch
    print('pinned backup root:', os.environ['KAIZEN_BACKUP_DIR'] == os.environ['EXPECTED_BACKUP_ROOT'])
    copy = change / 'files/1'
    rules = sys.argv[sys.argv.index('--disallowedTools') + 1].split(',')
    blocked = []
    # Simulate model Edit/Write permission checks against the actual runner command.
    for tool in ('Edit', 'Write'):
        denied = any(fnmatch.fnmatch('//' + copy.as_posix().lstrip('/'), rule[len(tool) + 1:-1])
                     for rule in rules if rule.startswith(tool + '('))
        if not denied:
            copy.write_text('crafted settings')
        blocked.append(denied)
    print('blocked backup edits:', blocked)
"""))
        self.guard_result(0)
        self.assertEqual(protected.read_text(), '{"protected":true}')
        folder, state = self.backup_state()
        self.assertEqual(state['status'], 'rolled-back')
        report = next(folder.glob('cycle-*.failed.md')).read_text()
        self.assertIn('blocked backup edits: [True, True]', report)
        self.assertIn('pinned backup root: True', report)

    def test_forged_preexisting_dirs_cannot_claim_runner_ownership(self):
        self.backup_cycle()
        old_target = write(self.project / 'old.md', 'old original')
        preexisting = []
        for name in ('same', 'moved', 'replaced'):
            result = subprocess.run([sys.executable, self.env['BACKUP_SCRIPT'], 'begin', '--run', name,
                                     '--skill', 'trim', '--ledger', 'old', str(old_target)],
                                    env=self.env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            preexisting.append(result.stdout.strip())
        old_target.write_text('current must stay')
        self.env['PREEXISTING'] = json.dumps(preexisting)
        injection = """
import datetime, shutil
old = [pathlib.Path(name) for name in json.loads(os.environ['PREEXISTING'])]
moved = old[1].with_name('renamed-old-dir')
old[1].rename(moved)
retired = old[2].with_name('retired-old-dir')
old[2].rename(retired)
shutil.copytree(retired, old[2])  # same old name, different inode
for folder in (old[0], moved, old[2], retired):
    manifest = folder / 'manifest.json'
    data = json.loads(manifest.read_text())
    data.update(run_id=os.environ['KAIZEN_RUN_ID'], session_id=os.environ['KAIZEN_SESSION_ID'],
                created_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
    manifest.write_text(json.dumps(data))
"""
        executable(self.claude, self.claude.read_text().replace('changes = []', injection + '\nchanges = []'))
        self.guard_result(0)
        self.assertEqual(old_target.read_text(), 'current must stay')
        for manifest in (self.root / 'backups').glob('*/manifest.json'):
            data = json.loads(manifest.read_text())
            if data['ledger'] == 'old':
                self.assertIsNone(data['reverted'])

    def test_malformed_preexisting_manifest_does_not_block_cycle_rollback(self):
        self.backup_cycle()
        old = self.root / 'backups/old'
        old.mkdir(parents=True)
        self.env['OLD_MANIFEST'] = str(old / 'manifest.json')
        executable(self.claude, self.claude.read_text().replace("print('cycle output')", """
pathlib.Path(os.environ['OLD_MANIFEST']).write_text('{broken')
print('cycle output')
"""))
        self.guard_result(0)
        self.assertEqual(Path(self.env['TARGET']).read_text(), 'original')
        self.assertEqual(self.backup_state()[1]['status'], 'rolled-back')

    def test_rollback_symlink_refusal_fails_run_without_touching_target(self):
        self.backup_cycle()
        victim = write(self.root / 'victim.md', 'untouched')
        self.env['VICTIM'] = str(victim)
        executable(self.claude, self.claude.read_text().replace("print('cycle output')", """
target.unlink()
target.symlink_to(os.environ['VICTIM'])
print('cycle output')
"""))
        self.guard_result(1)
        self.assertEqual(victim.read_text(), 'untouched')
        self.assertTrue(Path(self.env['TARGET']).is_symlink())
        folder, state = self.backup_state()
        self.assertEqual(state['status'], 'failed')
        self.assertIn('symlink', next(folder.glob('cycle-*.failed.md')).read_text())

    def test_auto_rolls_back_unfinished_and_failed_verification_newest_first(self):
        for finish in ('no', 'failed'):
            for exit_code in ('0', '1'):
                with self.subTest(finish=finish, exit_code=exit_code):
                    self.backup_cycle(finish, exit_code)
                    self.guard_result(0)
                    self.assertEqual(Path(self.env['TARGET']).read_text(), 'original')
                    folder, state = self.backup_state()
                    self.assertEqual(state['status'], 'rolled-back')
                    self.assertNotIn('reviewed_at', state)
                    report = next(folder.glob('cycle-*.failed.md')).read_text()
                    changes = json.loads(Path(self.env['CHANGE_RECORD']).read_text())
                    self.assertLess(report.index('rolled-back: ' + changes[1]),
                                    report.index('rolled-back: ' + changes[0]))
                    for change in changes:
                        self.assertTrue(json.loads((Path(change) / 'manifest.json').read_text())['reverted'])

    def test_auto_keeps_finished_verified_backups(self):
        self.backup_cycle('passed')
        self.guard_result(0)
        self.assertEqual(Path(self.env['TARGET']).read_text(), 'applied 1')
        folder, state = self.backup_state()
        self.assertEqual(state['status'], 'ok')
        self.assertNotIn('rolled-back', next(folder.glob('cycle-????-??-??.md')).read_text())
        for change in json.loads(Path(self.env['CHANGE_RECORD']).read_text()):
            self.assertIsNone(json.loads((Path(change) / 'manifest.json').read_text())['reverted'])

    def test_auto_matches_session_when_begin_overrides_run_id(self):
        self.backup_cycle()
        executable(self.claude, self.claude.read_text().replace(
            "'--ledger', 'test', target", "'--ledger', 'test', '--run', 'explicit-run', target"))
        self.guard_result(0)
        self.assertEqual(Path(self.env['TARGET']).read_text(), 'original')
        self.assertEqual(self.backup_state()[1]['status'], 'rolled-back')

    def test_auto_never_rolls_back_other_runs_or_old_backups(self):
        self.backup_cycle()
        original = self.claude.read_text()
        # Create unrelated backups after this run starts, and an old backup with matching ids.
        injection = """
other = target.with_name('other.md')
other.write_text('other original')
foreign = pathlib.Path(backup('begin', '--skill', 'trim', '--ledger', 'other', '--run', 'another-run', other))
manifest = foreign / 'manifest.json'
data = json.loads(manifest.read_text())
data['session_id'] = 'another-session'
manifest.write_text(json.dumps(data))
other.write_text('other applied')
old = target.with_name('old.md')
old.write_text('old original')
previous = pathlib.Path(backup('begin', '--skill', 'trim', '--ledger', 'old', old))
manifest = previous / 'manifest.json'
data = json.loads(manifest.read_text())
data['created_at'] = '2000-01-01T00:00:00+00:00'
manifest.write_text(json.dumps(data))
old.write_text('old applied')
"""
        executable(self.claude, original.replace('changes = []', injection + '\nchanges = []'))
        self.guard_result(0)
        self.assertEqual((self.project / 'other.md').read_text(), 'other applied')
        self.assertEqual((self.project / 'old.md').read_text(), 'old applied')
        self.assertEqual(Path(self.env['TARGET']).read_text(), 'original')
        untouched = [json.loads(path.read_text()) for path in (self.root / 'backups').glob('*/manifest.json')
                     if json.loads(path.read_text())['ledger'] in ('other', 'old')]
        self.assertEqual(len(untouched), 2)
        self.assertTrue(all(data['reverted'] is None for data in untouched))

    def test_auto_rollback_failure_fails_run_and_keeps_backup(self):
        self.backup_cycle()
        original = self.claude.read_text()
        executable(self.claude, original.replace("print('cycle output')", """
# Prevent undo of one entry without deleting its backup directory or manifest.
data = json.loads((pathlib.Path(changes[-1]) / 'manifest.json').read_text())
(pathlib.Path(changes[-1]) / data['files'][0]['backup']).unlink()
print('cycle output')
"""))
        self.guard_result(1)
        folder, state = self.backup_state()
        self.assertEqual(state['status'], 'failed')
        self.assertNotIn('reviewed_at', state)
        self.assertIn('rollback failed:', next(folder.glob('cycle-*.failed.md')).read_text())
        change = Path(json.loads(Path(self.env['CHANGE_RECORD']).read_text())[-1])
        self.assertTrue(change.is_dir())
        self.assertIsNone(json.loads((change / 'manifest.json').read_text())['reverted'])

    def test_rollback_scan_error_does_not_skip_ledger_verification(self):
        self.configure_ledgers()
        executable(self.claude, '#!' + sys.executable + '\n' + """
import os, pathlib
pathlib.Path(os.environ['CSV']).write_bytes(b'')
""")
        with patch.dict(os.environ, self.env, clear=True), \
                patch.object(self.module, 'rollback_auto_changes', side_effect=OSError('scan error')):
            code = self.module.main(['review', '--force', '--project-dir', str(self.project),
                                     '--claude', str(self.claude)])
        self.assertEqual(code, 1)
        self.assertEqual(self.csv.read_bytes(), self.original_ledgers[0])
        self.assert_ledger_violation()

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
