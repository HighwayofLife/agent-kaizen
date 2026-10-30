"""Offline retention plans, safety boundaries, and scheduled runner wiring."""
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import runpy
import unittest
from unittest import mock

from test_scripts import SCRIPTS, StubCase, executable, write


class HousekeepTests(StubCase):
    def setUp(self):
        super().setUp()
        self.ns = runpy.run_path(str(SCRIPTS / 'kaizen-scheduled'))
        self.audits = self.root / 'audits'
        self.now = datetime(2026, 10, 30, tzinfo=timezone.utc)
        self.cfg = {'retention': {'value': 'auto'}, 'retentionOverrides': {'value': {}}}

    def file(self, name, days=40, size=1, hours=0):
        path = write(self.audits / name, 'x' * size)
        stamp = self.now.timestamp() - days * 86400 - hours * 3600
        os.utime(path, (stamp, stamp))
        return path

    def cleanup(self, dry=False, cfg=None):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            plan = self.ns['housekeep'](self.audits, cfg or self.cfg, dry, self.now)
        return plan, out.getvalue(), err.getvalue()

    def test_windows_logs_and_exact_entries(self):
        self.file('extracts/old.extract.json', size=3)
        fresh = self.file('extracts/new.extract.json', days=30)
        self.file('projects/p/cycle-old.failed.md', size=4)
        self.file('stamp.noticed-2025-01-01', size=5)
        self.file('projects/p/stamp.noticed-2025-01-01', size=6)
        self.file('projects/p/host-probe-old.json', size=7)
        self.file('projects/p/friction-inputs-old.json', size=8)
        self.file('projects/p/old.extract.json', size=9)
        plan, output, errors = self.cleanup()
        self.assertEqual(errors, '')
        expected = [
            ('extracts/old.extract.json', 'extracts', 3),
            ('projects/p/friction-inputs-old.json', 'extracts', 8),
            ('projects/p/host-probe-old.json', 'extracts', 7),
            ('projects/p/old.extract.json', 'extracts', 9),
            ('projects/p/cycle-old.failed.md', 'markers', 4),
            ('projects/p/stamp.noticed-2025-01-01', 'markers', 6),
            ('stamp.noticed-2025-01-01', 'markers', 5)]
        self.assertEqual(plan, [dict(path=p, kind=k, size=s, reason='age') for p, k, s in expected])
        self.assertEqual(len(output.splitlines()), len(plan))
        for line, entry in zip(output.splitlines(), plan):
            self.assertTrue(line.endswith('housekeep: deleted {path} kind={kind} size={size} reason={reason}'.format(**entry)))
        self.assertTrue(fresh.exists())

    def test_report_families_and_reviewed_siblings(self):
        for folder in ('', 'projects/p/'):
            for family in ('token-audit', 'cycle') if folder else ('token-audit',):
                for n in range(7):
                    self.file(f'{folder}{family}-{n}.md', days=407 - n)
                    self.file(f'{folder}{family}-{n}.reviewed', days=407 - n)
        orphan = self.file('token-audit-orphan.reviewed', days=500)
        self.file('projects/p/cycle-old.failed.md', days=400)
        plan, _, _ = self.cleanup()
        for folder, family in (('', 'token-audit'), ('projects/p/', 'token-audit'), ('projects/p/', 'cycle')):
            for n in range(7):
                self.assertEqual((self.audits / f'{folder}{family}-{n}.md').exists(), n >= 2)
                self.assertEqual((self.audits / f'{folder}{family}-{n}.reviewed').exists(), n >= 2)
        self.assertEqual(sum(e['reason'] == 'report' for e in plan), 6)
        self.assertEqual(next(e['kind'] for e in plan if e['path'].endswith('.failed.md')), 'markers')
        self.assertTrue(orphan.exists())

    def test_caps_oldest_then_path_and_protected_reports(self):
        self.cfg['retentionOverrides']['value'] = {'extracts': {'maxMB': 1}, 'reports': {'maxMB': 1}}
        for name in ('c', 'b', 'a'):
            self.file(f'extracts/{name}.extract.json', days=1, size=600 * 1024)
        for n in range(7):
            self.file(f'token-audit-{n}.md', days=n, size=600 * 1024)
        plan, _, _ = self.cleanup()
        self.assertEqual([e['path'] for e in plan], ['extracts/a.extract.json', 'extracts/b.extract.json',
                                                   'token-audit-6.md', 'token-audit-5.md'])
        self.assertTrue(all(e['reason'] == 'cap' for e in plan))
        self.assertEqual(len(list(self.audits.glob('token-audit-*.md'))), 5)

    def test_overrides_days_hours_and_revalidation(self):
        for limits, age, hours, deleted in (({'days': 5}, 6, 0, True),
                ({'hours': 2, 'days': 30}, 0, 3, True), ({'days': 0}, 6, 0, False),
                ({'days': True}, 6, 0, False), ({'hours': '2'}, 6, 0, False),
                ({'maxMB': 0}, 6, 0, False), ({'unknown': 2}, 6, 0, False)):
            with self.subTest(limits=limits):
                path = self.file('extracts/old.extract.json', days=age, hours=hours)
                self.cfg['retentionOverrides']['value'] = {'extracts': limits}
                plan, _, err = self.cleanup()
                self.assertEqual(bool(plan), deleted)
                self.assertEqual(bool(err), not deleted)
                path.unlink(missing_ok=True)
        self.file('extracts/old.extract.json', days=6)
        self.cfg['retentionOverrides']['value'] = {'nosuchkind': {'days': 1}}
        plan, _, err = self.cleanup()
        self.assertEqual(plan, [])
        self.assertIn('housekeep: retentionOverrides: unknown kind nosuchkind, ignored', err)

    def test_off_does_not_scan_or_print(self):
        self.file('extracts/old.extract.json', days=900)
        self.cfg['retention']['value'] = 'off'
        with mock.patch.dict(self.ns['housekeep'].__globals__, retention_matches=mock.Mock(side_effect=AssertionError)):
            self.assertEqual(self.cleanup(), ([], '', ''))

    def test_never_names_and_symlinks(self):
        names = ('host-actions.json', 'host-fixes/x.json', 'projects/index.json',
                 'projects/p/state.json', 'run.log', 'extracts/notes.txt',
                 'kaizen-backups/token-audit-x.md')
        paths = [self.file(n, days=900) for n in names]
        outside = write(self.root / 'outside' / 'old.extract.json', 'private')
        os.utime(outside, (1, 1))
        (self.audits / 'extracts/link.extract.json').symlink_to(outside)
        (self.audits / 'projects/linked').symlink_to(outside.parent, target_is_directory=True)
        (self.audits / 'projects/internal').symlink_to(self.audits / 'extracts', target_is_directory=True)
        self.assertEqual(self.cleanup(), ([], '', ''))
        self.assertTrue(all(p.exists() for p in paths))
        self.assertTrue(outside.exists())
        self.assertTrue((self.audits / 'extracts/link.extract.json').is_symlink())

    def test_empty_touched_directories_only(self):
        self.file('extracts/old.extract.json')
        self.file('projects/empty/old.extract.json')
        self.file('projects/state/old.extract.json')
        self.file('projects/state/state.json')
        untouched = self.audits / 'projects/untouched'
        untouched.mkdir()
        self.cleanup()
        self.assertFalse((self.audits / 'extracts').exists())
        self.assertFalse((self.audits / 'projects/empty').exists())
        self.assertTrue((self.audits / 'projects/state').exists())
        self.assertTrue(untouched.exists())
        self.assertTrue((self.audits / 'projects').exists())

    def test_dry_run_plan_matches_real(self):
        self.file('extracts/old.extract.json')
        self.file('projects/p/cycle-old.failed.md')
        preview, output, _ = self.cleanup(True)
        self.assertTrue(all((self.audits / e['path']).exists() for e in preview))
        actual, real, _ = self.cleanup()
        self.assertEqual(preview, actual)
        self.assertEqual([line.split('housekeep: ')[1].replace('would delete', 'deleted') for line in output.splitlines()],
                         [line.split('housekeep: ')[1] for line in real.splitlines()])

    def test_report_ties_windows_and_nonregular_candidates(self):
        for n in range(7):
            self.file(f'token-audit-{n}.md', days=400)
        for n in range(7):
            self.file(f'projects/fresh/token-audit-{n}.md', days=365)
        outside = write(self.root / 'outside.reviewed', 'private')
        (self.audits / 'token-audit-0.reviewed').symlink_to(outside)
        (self.audits / 'extracts').mkdir()
        os.mkfifo(self.audits / 'extracts/pipe.extract.json')
        (self.audits / 'extracts/directory.extract.json').mkdir()
        plan, _, _ = self.cleanup()
        self.assertEqual([e['path'] for e in plan], ['token-audit-0.md', 'token-audit-1.md'])
        self.assertTrue(outside.exists())
        self.assertTrue((self.audits / 'token-audit-0.reviewed').is_symlink())
        self.assertEqual(len(list((self.audits / 'projects/fresh').glob('*.md'))), 7)

    def test_invalid_override_shapes_and_valid_fields_survive(self):
        for overrides in ([], {'extracts': []}):
            self.cfg['retentionOverrides']['value'] = overrides
            path = self.file('extracts/old.extract.json', days=6)
            plan, _, err = self.cleanup()
            self.assertEqual(plan, [])
            self.assertIn('housekeep: retentionOverrides:', err)
            self.assertTrue(path.exists())
        self.cfg['retentionOverrides']['value'] = {'extracts': {'days': 5, 'hours': 0}}
        self.assertEqual(len(self.cleanup()[0]), 1)

    def test_wrapper_housekeeps_when_body_raises(self):
        for name, args in (('audit', (self.audits, None)),
                           ('review', (self.audits, None, None, None))):
            cleanup = mock.Mock()
            with mock.patch.dict(self.ns['run_audit'].__globals__,
                                 **{'_run_' + name: mock.Mock(side_effect=ValueError('body')),
                                    'housekeep': cleanup, 'effective': lambda: self.cfg}):
                with self.assertRaisesRegex(ValueError, 'body'):
                    self.ns['run_' + name](*args)
            cleanup.assert_called_once_with(self.audits, self.cfg)

    def test_vanished_file_does_not_stop_cli(self):
        vanished = self.file('extracts/a.extract.json', days=900)
        other = self.file('projects/p/b.extract.json', days=900)
        original = Path.unlink

        def unlink(path, *args, **kwargs):
            if path == vanished:
                original(path)
                raise FileNotFoundError('already removed')
            return original(path, *args, **kwargs)

        out = io.StringIO()
        with mock.patch.object(Path, 'unlink', unlink), redirect_stdout(out):
            status = self.ns['main'](['housekeep', '--audits', str(self.audits)])
        self.assertEqual(status, 0)
        self.assertFalse(other.exists())
        self.assertFalse(other.parent.exists())
        self.assertIn('housekeep: skipped extracts/a.extract.json', out.getvalue())

    @unittest.skipIf(os.geteuid() == 0, 'root can read chmod 000 folders')
    def test_unreadable_project_does_not_stop_cli(self):
        blocked = self.file('projects/blocked/a.extract.json', days=900)
        other = self.file('projects/other/b.extract.json', days=900)
        blocked.parent.chmod(0)
        try:
            result = self.run_script('kaizen-scheduled', 'housekeep', '--audits', self.audits)
        finally:
            blocked.parent.chmod(0o700)
        self.assertTrue(blocked.exists())
        self.assertFalse(other.exists())
        self.assertIn('housekeep: cannot scan', result.stdout)
        self.assertNotIn('Traceback', result.stderr)

    def test_changed_file_is_skipped_and_result_only_lists_deletions(self):
        changed = self.file('extracts/a.extract.json')
        deleted = self.file('extracts/b.extract.json')
        original = self.ns['housekeep'].__globals__['retention_stat']
        calls = 0

        def replace_before_delete(root, path):
            nonlocal calls
            if path == changed:
                calls += 1
                if calls == 2:
                    path.write_text('replacement')
                    os.utime(path, ns=(1, 1))
            return original(root, path)

        with mock.patch.dict(self.ns['housekeep'].__globals__, retention_stat=replace_before_delete):
            result, output, _ = self.cleanup()
        self.assertEqual(changed.read_text(), 'replacement')
        self.assertFalse(deleted.exists())
        self.assertEqual([entry['path'] for entry in result], ['extracts/b.extract.json'])
        self.assertIn('housekeep: skipped extracts/a.extract.json', output)

    def test_cli_resolves_symlinked_audits(self):
        old = self.file('extracts/old.extract.json', days=900)
        link = self.root / 'audits-link'
        link.symlink_to(self.audits, target_is_directory=True)
        self.run_script('kaizen-scheduled', 'housekeep', '--audits', link)
        self.assertFalse(old.exists())

    def test_missing_folder_and_cli_disabled(self):
        self.assertEqual(self.cleanup(), ([], '', ''))
        self.env['CLAUDE_CONFIG_DIR'] = str(self.root / 'cfg')
        write(self.root / 'cfg/agent-kaizen.json', '{"enabled":false}')
        path = self.file('extracts/old.extract.json', days=900)
        self.run_script('kaizen-scheduled', 'housekeep', '--help')
        self.run_script('kaizen-scheduled', 'housekeep', '--audits', self.audits, '--dry-run')
        self.assertTrue(path.exists())
        self.run_script('kaizen-scheduled', 'housekeep', '--audits', self.audits)
        self.assertFalse(path.exists())

    def test_wrappers_always_housekeep_once_and_preserve_status(self):
        for name, args in (('audit', (self.audits, None)), ('review', (self.audits, None, None, None))):
            for status in (0, 3):
                with self.subTest(name=name, status=status):
                    cleanup = mock.Mock(side_effect=RuntimeError('test failure'))
                    out = io.StringIO()
                    with mock.patch.dict(self.ns['run_audit'].__globals__,
                                         **{'_run_' + name: mock.Mock(return_value=status),
                                            'housekeep': cleanup, 'effective': lambda: self.cfg}), redirect_stdout(out):
                        self.assertEqual(self.ns['run_' + name](*args), status)
                    cleanup.assert_called_once_with(self.audits, self.cfg)
                    self.assertIn('housekeep: failed (test failure)', out.getvalue())

    def test_cli_audit_review_failure_no_due_and_dry_run(self):
        # Same subprocess stub approach as test_runner; no external executables run.
        audit = executable(self.bin / 'audit', '''#!/usr/bin/env python3
import json, os, pathlib, sys
args = sys.argv[1:]
out = pathlib.Path(args[args.index('--out') + 1])
out.mkdir(parents=True, exist_ok=True)
report = out / 'token-audit-stub.md'
report.write_text('report')
print(report)
pathlib.Path(os.environ['AUDIT_RECORD']).write_text(json.dumps(args))
sys.exit(int(os.environ.get('STUB_AUDIT_EXIT', '0')))
''')
        claude = executable(self.bin / 'claude', '#!/usr/bin/env python3\nprint("proposal")\n')
        cfg, cx = self.root / 'cfg', self.root / 'cx'
        self.env.update(CLAUDE_CONFIG_DIR=str(cfg), CODEX_HOME=str(cx), AUDIT_RECORD=str(self.record))
        project = self.work
        write(project / 'docs/kaizen/config.json', '{"schedule":"always"}')
        write(cfg / 'projects/p/session.jsonl', json.dumps({'type': 'user', 'cwd': str(project)}) + '\n')
        for command, status in (('audit', 0), ('audit', 3), ('review', 0), ('review', 3)):
            with self.subTest(command=command, status=status):
                old = self.file('extracts/old.extract.json', days=900)
                self.env['STUB_AUDIT_EXIT'] = str(status)
                args = [command, '--audits', self.audits, '--token-audit', audit]
                if command == 'review':
                    args += ['--claude', claude]
                result = self.run_script('kaizen-scheduled', *args, code=status if command == 'audit' else 0)
                self.assertFalse(old.exists())
                self.assertEqual(result.stdout.count('housekeep: deleted'), 1)
                argv = json.loads(self.record.read_text())
                self.assertEqual(argv[argv.index('--extract-out') + 1], str(self.audits / 'extracts'))
        old = self.file('extracts/old.extract.json', days=900)
        self.run_script('kaizen-scheduled', 'review', '--audits', self.audits, '--dry-run', '--token-audit', audit)
        self.assertTrue(old.exists())
        write(project / 'docs/kaizen/config.json', '{"schedule":"off"}')
        self.run_script('kaizen-scheduled', 'review', '--audits', self.audits, '--claude', claude, '--token-audit', audit)
        self.assertFalse(old.exists())
