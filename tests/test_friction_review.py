"""Scheduled friction preparation and transactional reconciliation."""
import json
from datetime import timedelta

from test_friction_prepare import PreparationTests, prepare


class ScheduledFrictionTests(PreparationTests):
    def scheduled(self, mode="propose-only"):
        return prepare.prepare(self.config / "audits", self.backups, self.obj, self.report,
                               self.runner["effective"](self.project), mode, self.current + timedelta(seconds=2),
                               self.runner["action_project"], self.runner["key"], retain=True)

    def test_suggestion_import_acknowledges_and_strips(self):
        inputs, receipt = self.scheduled()
        output = self.write(self.obj.folder / "review.md", 'Review\n<!-- kaizen-host-actions {"v":1,"actions":[]} -->\n')
        self.runner["reconcile_scheduled"](self.config / "audits", self.obj, output, receipt)
        self.assertEqual(output.read_text(), 'Review\n')
        self.assertIsNone(self.scheduled())
        self.assertTrue(inputs.exists())

    def test_apply_stays_pending_and_does_not_acknowledge(self):
        self.probe["findings"] = [dict(id="low-disk", catalog_id="low-disk", subject="project-volume",
                                       evidence=dict(free_disk_bytes=1))]
        self.write_evidence()
        inputs, receipt = self.scheduled("auto")
        ident = json.loads(inputs.read_text())["actions"][0]["id"]
        output = self.write(self.obj.folder / "review.md", '<!-- kaizen-host-actions ' + json.dumps(
            dict(v=1, actions=[dict(id=ident, intent="apply")])) + ' -->\n')
        self.runner["reconcile_scheduled"](self.config / "audits", self.obj, output, receipt)
        self.assertIsNotNone(self.scheduled("auto"))
        store = json.loads((self.config / "audits/host-actions.json").read_text())
        self.assertIn('pending', json.dumps(store))

    def test_malformed_output_cannot_acknowledge(self):
        _, receipt = self.scheduled()
        output = self.write(self.obj.folder / "review.md", '<!-- kaizen-host-actions broken -->\n')
        with self.assertRaises(ValueError):
            self.runner["reconcile_scheduled"](self.config / "audits", self.obj, output, receipt)
        self.assertIsNotNone(self.scheduled())

    def test_audit_policy_global_and_scoped(self):
        options = self.runner["command_options"](type("Args", (), {"dry_run": True})())
        self.write(self.config / "agent-kaizen.json", '{"friction":"off","frictionSlowCallSeconds":123}')
        command = self.runner["audit_command"](options, self.config / "audits")
        scoped = self.runner["audit_command"](options, self.obj.folder, self.obj)
        for argv in (command, scoped):
            self.assertIn('--no-friction', argv)
            self.assertEqual(argv[argv.index('--friction-slow-seconds') + 1], '123')


class ScheduledReviewIntegrationTests(PreparationTests):
    def setUp(self):
        super().setUp()
        import os
        import sys
        self.env = dict(self.environment, HOME=str(self.root), REVIEW_RECORD=str(self.root / 'calls'))
        self.audit = self.write(self.root / 'audit.py', '#!' + sys.executable + '\nprint(' + repr(str(self.report)) + ')\n')
        self.audit.chmod(0o755)
        self.claude = self.write(self.root / 'claude', '#!' + sys.executable + '''
import json, os, pathlib, sys, time
args = sys.argv[1:]
home = pathlib.Path(os.environ['KAIZEN_BACKUP_DIR'])
marker = list(home.glob('.active-run*.json'))
with open(os.environ['REVIEW_RECORD'], 'a') as out:
    out.write(json.dumps({'argv': args, 'marker': bool(marker)}) + '\\n')
print('Review', flush=True)
print('<!-- kaizen-host-actions {"v":1,"actions":[]} -->', flush=True)
if os.environ.get('REVIEW_SLEEP'): time.sleep(10)
''')
        self.claude.chmod(0o755)
        self.runner_path = self.root.parent / 'unused'
        from test_friction_prepare import PATH
        self.runner_path = PATH.parent / 'kaizen-scheduled'

    def review_run(self, *extra, runner=None, env=None):
        import subprocess
        import sys
        command = [sys.executable, str(runner or self.runner_path), 'review', '--force',
                   '--project-dir', str(self.project), '--audits', str(self.config / 'audits'),
                   '--token-audit', str(self.audit), '--claude', str(self.claude), *extra]
        return subprocess.run(command, env=env or self.env, capture_output=True, text=True)

    def calls(self):
        return [json.loads(line) for line in (self.root / 'calls').read_text().splitlines()]

    def state(self):
        return json.loads(next((self.backups / 'friction').glob('prepare-*.json')).read_text())

    def test_copied_install_runs_installed_preparation(self):
        import os
        import shutil
        import sys
        import subprocess
        from test_schedule import CRONTAB
        plugin = self.root / 'plugins/cache/agent-kaizen/version'
        shutil.copytree(self.runner_path.parent, plugin / 'scripts')
        binary = self.root / 'bin'
        cron = self.write(binary / 'crontab', CRONTAB.replace('#!/usr/bin/env python3', '#!' + sys.executable))
        cron.chmod(0o755)
        env = dict(self.env, CRON_FILE=str(self.root / 'cron'), PATH=str(binary) + os.pathsep + os.environ['PATH'])
        installed = subprocess.run([sys.executable, str(plugin / 'scripts/install-schedule'), '--apply', '--scheduler', 'cron'], env=env, capture_output=True, text=True)
        self.assertEqual(installed.returncode, 0, installed.stderr)
        target = self.config / 'bin'
        self.assertTrue((target / 'kaizen_friction_prepare.py').is_file())
        self.assertFalse((target / 'kaizen_friction_prepare.py').is_symlink())
        shutil.rmtree(plugin)
        result = self.review_run(runner=target / 'kaizen-scheduled', env=env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('friction-inputs=', self.calls()[0]['argv'][1])
        self.assertEqual(self.state()['acknowledged_generation'], '00000000000000000001')

    def test_timeout_leaves_generation_pending(self):
        env = dict(self.env, REVIEW_SLEEP='1', KAIZEN_REVIEW_TIMEOUT='0.3')
        result = self.review_run(env=env)
        self.assertIn('timed out', result.stdout)
        state = self.state()
        self.assertEqual(state['generation'], 1)
        self.assertNotIn('acknowledged_generation', state)
        self.assertIsNotNone(self.scheduled() if hasattr(self, 'scheduled') else self.run_prepare())

    def test_closed_gate_and_open_gate_argv(self):
        result = self.review_run()
        self.assertEqual(result.returncode, 0, result.stderr)
        first = self.calls()[0]
        prompt = first['argv'][1]
        self.assertEqual(prompt.count('friction-inputs='), 1)
        argument = prompt.split(' friction-inputs=', 1)[1]
        self.assertTrue(json.loads(argument).endswith('friction-inputs-00000000000000000001.json'))
        self.assertIn(str(self.report), prompt)
        self.assertIn('--allowedTools', first['argv'])
        self.assertIn('--disallowedTools', first['argv'])
        self.assertTrue(first['marker'])
        self.review_run()
        second = self.calls()[1]
        self.assertNotIn('friction-inputs=', second['argv'][1])
        self.assertTrue(second['marker'])
        def stable_argv(argv):
            argv = list(argv)
            argv[argv.index('-p') + 1] = '<prompt>'
            argv[argv.index('--session-id') + 1] = '<session>'
            return argv
        self.assertEqual(stable_argv(first['argv']), stable_argv(second['argv']))
        before = len(self.calls())
        dry = self.review_run('--dry-run')
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertIn('--allowedTools', dry.stdout)
        self.assertNotIn('friction-inputs=', dry.stdout)
        self.assertEqual(len(self.calls()), before)

    def test_optional_preparation_failures_fall_back(self):
        import shutil
        for failure in ('missing', 'exception', 'malformed'):
            with self.subTest(failure=failure):
                scripts = self.root / ('scripts-' + failure)
                shutil.copytree(self.runner_path.parent, scripts)
                helper = scripts / 'kaizen_friction_prepare.py'
                if failure == 'missing':
                    helper.unlink()
                elif failure == 'exception':
                    helper.write_text('def prepare(*args, **kwargs):\n    raise ValueError("failed")\n')
                else:
                    helper.write_text('def prepare(*args, **kwargs):\n    return "malformed"\n')
                result = self.review_run(runner=scripts / 'kaizen-scheduled')
                self.assertEqual(result.returncode, 0, result.stderr)
                prompt = self.calls()[-1]['argv'][1]
                self.assertIn(str(self.report), prompt)
                self.assertNotIn('friction-inputs=', prompt)
                self.assertFalse(list((self.backups / 'friction').glob('prepare-*.json')))

    def test_retry_after_failed_import_preserves_generation(self):
        import shutil
        scripts = self.root / 'retry-scripts'
        shutil.copytree(self.runner_path.parent, scripts)
        helper = scripts / 'kaizen_friction_actions.py'
        original = helper.read_text()
        # Fail only the transactional import, after preparation has succeeded.
        helper.write_text(original.replace('def import_actions(self,', 'def import_actions_disabled(self,', 1))
        first = self.review_run(runner=scripts / 'kaizen-scheduled')
        self.assertIn('could not be reconciled', first.stdout)
        state = self.state()
        self.assertNotIn('acknowledged_generation', state)
        receipt_path = next((self.backups / 'friction').glob('receipt-*.json'))
        first_receipt = json.loads(receipt_path.read_text())
        first_prompt = self.calls()[0]['argv'][1]
        helper.write_text(original)
        second = self.review_run(runner=scripts / 'kaizen-scheduled')
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(self.calls()[1]['argv'][1].split(' friction-inputs=')[1],
                         first_prompt.split(' friction-inputs=')[1])
        self.assertEqual(self.state()['acknowledged_generation'], '00000000000000000001')
        final_state = self.state()
        self.assertEqual(final_state['acknowledged'], first_receipt['comparison'])
        self.assertEqual(json.loads(receipt_path.read_text())['comparison'], first_receipt['comparison'])
        store = json.loads((self.config / 'audits/host-actions.json').read_text())
        self.assertEqual(json.dumps(store).count('scheduled:00000000000000000001'), 1)
        self.review_run(runner=scripts / 'kaizen-scheduled')
        self.assertNotIn('friction-inputs=', self.calls()[2]['argv'][1])
        self.assertEqual(self.state(), final_state)
