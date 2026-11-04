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
