"""kaizen-backup: begin/finish/undo round trips, created files, conflicts, runs."""
import os
import json
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'kaizen-backup'


class KaizenBackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.env = {**os.environ, 'KAIZEN_BACKUP_DIR': str(self.tmp / 'backups')}

    def run_script(self, *args, ok=True):
        result = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], env=self.env,
                                capture_output=True, text=True)
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return result

    def change(self, *files, run='r1', skill='trim'):
        return self.run_script('begin', '--skill', skill, '--ledger', 'test change', '--run', run, *files).stdout.strip()

    def test_edit_and_create_round_trip(self):
        edited, created = self.tmp / 'CLAUDE.md', self.tmp / 'new.md'
        edited.write_text('original\n')
        change = self.change(edited, created)
        edited.write_text('trimmed\n')
        created.write_text('brand new\n')
        self.run_script('finish', change)
        self.run_script('undo', 'last')
        self.assertEqual(edited.read_text(), 'original\n')
        self.assertFalse(created.exists())
        self.assertIn('nothing to undo', self.run_script('undo', 'last', ok=False).stderr)

    def test_conflict_blocks_undo_unless_forced(self):
        target = self.tmp / 'settings.json'
        target.write_text('{}\n')
        change = self.change(target)
        target.write_text('{"a": 1}\n')
        self.run_script('finish', change)
        target.write_text('{"a": 1, "user": true}\n')  # the user edited it afterwards
        result = self.run_script('undo', ok=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn('CONFLICT', result.stdout)
        self.assertEqual(target.read_text(), '{"a": 1, "user": true}\n')
        self.run_script('undo', '--force')
        self.assertEqual(target.read_text(), '{}\n')

    def test_undo_refuses_plugin_symlinks_even_with_force_before_any_restore(self):
        plugin = self.tmp / 'plugin'
        plugin.mkdir()
        self.env['CLAUDE_PLUGIN_ROOT'] = str(plugin)
        for parent_link in (False, True):
            with self.subTest(parent_link=parent_link):
                folder = self.tmp / ('linked-parent' if parent_link else 'linked-file')
                folder.mkdir()
                target, other = folder / 'tool', self.tmp / 'other'
                target.write_text('local original')
                other.write_text('other original')
                change = Path(self.change(other, target))
                other.write_text('other changed')
                self.run_script('finish', change)
                source_dir = plugin / folder.name
                source_dir.mkdir()
                source = source_dir / 'tool'
                source.write_text('plugin source')
                target.unlink()
                if parent_link:
                    folder.rmdir()
                    folder.symlink_to(source_dir, target_is_directory=True)
                else:
                    target.symlink_to(source)
                for flags in ((), ('--force',)):
                    result = self.run_script('undo', change, *flags, ok=False)
                    self.assertEqual(result.returncode, 2)
                    self.assertIn('symlink into plugin root', result.stderr)
                    self.assertIn('--unlink --restore-replaced', result.stderr)
                    self.assertEqual(source.read_text(), 'plugin source')
                    self.assertEqual(other.read_text(), 'other changed')
                    self.assertIsNone(json.loads((change / 'manifest.json').read_text())['reverted'])

    def test_copied_backup_uses_installed_plugin_root_for_symlink_refusal(self):
        installed = self.tmp / 'bin'
        installed.mkdir()
        copied = installed / 'kaizen-backup'
        shutil.copy2(SCRIPT, copied)
        plugin = self.tmp / 'plugin'
        plugin.mkdir()
        (installed / '.kaizen-plugin-root').write_text(str(plugin))
        self.env.pop('CLAUDE_PLUGIN_ROOT', None)
        target, source = self.tmp / 'tool', plugin / 'tool'
        target.write_text('local original')
        change = self.change(target)
        source.write_text('plugin source')
        target.unlink()
        target.symlink_to(source)
        result = subprocess.run([sys.executable, str(copied), 'undo', change, '--force'],
                                env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('symlink into plugin root', result.stderr)
        self.assertEqual(source.read_text(), 'plugin source')

    def test_undo_run_reverts_every_change_in_newest_run(self):
        one, two, other = (self.tmp / n for n in ('one', 'two', 'other'))
        for path in (one, two, other):
            path.write_text('v1')
        old = self.change(other, run='r0')
        other.write_text('v2')
        self.run_script('finish', old)
        for path in (one, two):
            change = self.change(path, run='r1')
            path.write_text('v2')
            self.run_script('finish', change)
        self.run_script('undo', 'run')
        self.assertEqual((one.read_text(), two.read_text(), other.read_text()), ('v1', 'v1', 'v2'))

    def test_actions_are_printed_not_run(self):
        target = self.tmp / 'f'
        target.write_text('x')
        change = self.change(target)
        self.run_script('action', change, '--did', 'brew install fd', '--undo', 'brew uninstall fd')
        self.run_script('finish', change)
        self.assertIn('ACTION to reverse by hand (not run): brew uninstall fd', self.run_script('undo').stdout)

    def test_begin_rejects_unsafe_run_and_skill(self):
        for option in ('--run', '--skill'):
            for value in ('../escape', '/absolute', 'a/b', 'a..b'):
                with self.subTest(option=option, value=value):
                    args = {'--run': 'run', '--skill': 'skill', option: value}
                    result = self.run_script('begin', '--run', args['--run'], '--skill', args['--skill'],
                                             '--ledger', 'test', self.tmp / 'file', ok=False)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertIn('must not contain', result.stderr)
        self.assertFalse(list((self.tmp / 'backups').glob('*/manifest.json')))

    def test_begin_rejects_nul_and_unsafe_environment_run(self):
        with patch.dict(os.environ, self.env):
            main = runpy.run_path(str(SCRIPT))['main']
            for option in ('--run', '--skill'):
                with self.subTest(option=option):
                    args = {'--run': 'run', '--skill': 'skill', option: 'bad\0value'}
                    self.assertEqual(main(['begin', '--run', args['--run'], '--skill', args['--skill'],
                                           '--ledger', 'test', str(self.tmp / 'file')]), 2)
        self.env['KAIZEN_RUN_ID'] = '../escape'
        result = self.run_script('begin', '--skill', 'skill', '--ledger', 'test', self.tmp / 'file', ok=False)
        self.assertEqual(result.returncode, 2, result.stderr)

    def test_finish_rejects_outside_change_dir_and_symlink(self):
        change = Path(self.change(self.tmp / 'file'))
        outside = self.tmp / 'outside'
        shutil.copytree(change, outside)
        original = (outside / 'manifest.json').read_bytes()
        link = self.tmp / 'backups/linked'
        link.symlink_to(outside, target_is_directory=True)
        for path in (outside, link, self.tmp / 'backups/../outside'):
            with self.subTest(path=path):
                result = self.run_script('finish', path, ok=False)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn('inside the backups root', result.stderr)
                self.assertEqual((outside / 'manifest.json').read_bytes(), original)

    def test_begin_rejects_change_dir_symlink_outside_root(self):
        root = self.tmp / 'backups'
        root.mkdir()
        outside = self.tmp / 'outside'
        (root / 'run-01-skill').symlink_to(outside, target_is_directory=True)
        result = self.run_script('begin', '--run', 'run', '--skill', 'skill', '--ledger', 'test',
                                 self.tmp / 'file', ok=False)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('inside the backups root', result.stderr)
        self.assertFalse(outside.exists())

    def test_undo_explicit_dir_ignores_malformed_old_manifest(self):
        target = self.tmp / 'target'
        target.write_text('original')
        change = self.change(target)
        target.write_text('changed')
        old = self.tmp / 'backups/old'
        old.mkdir()
        (old / 'manifest.json').write_text('{broken')
        self.run_script('undo', change, '--force')
        self.assertEqual(target.read_text(), 'original')

    def test_undo_rejects_non_absolute_or_non_normalised_entries_before_restoring(self):
        target = self.tmp / 'target'
        target.write_text('original')
        change = Path(self.change(target, self.tmp / 'created'))
        manifest = change / 'manifest.json'
        data = json.loads(manifest.read_text())
        target.write_text('changed')
        for name in ('relative', str(self.tmp / 'child/../created'),
                     str(self.tmp) + '//created', str(self.tmp) + '/./created'):
            with self.subTest(path=name):
                data['files'][1]['path'] = name
                manifest.write_text(json.dumps(data))
                result = self.run_script('undo', change, '--force', ok=False)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn('absolute and normalised', result.stderr)
                self.assertEqual(target.read_text(), 'changed')
                self.assertIsNone(json.loads(manifest.read_text())['reverted'])

    def test_undo_rejects_backup_outside_its_own_dir_before_restoring(self):
        target = self.tmp / 'target'
        target.write_text('original')
        change = Path(self.change(target))
        target.write_text('changed')
        outside = self.tmp / 'outside'
        outside.write_text('crafted')
        link = change / 'files/link'
        link.symlink_to(outside)
        manifest = change / 'manifest.json'
        data = json.loads(manifest.read_text())
        for name in (str(outside), '../../outside', 'files/link'):
            with self.subTest(backup=name):
                data['files'][0]['backup'] = name
                manifest.write_text(json.dumps(data))
                result = self.run_script('undo', change, '--force', ok=False)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn('inside its change directory', result.stderr)
                self.assertEqual(target.read_text(), 'changed')

    def test_undo_rejects_all_target_symlinks_including_created_entries(self):
        for created in (False, True):
            for parent_link in (False, True):
                with self.subTest(created=created, parent_link=parent_link):
                    folder = self.tmp / f'target-{created}-{parent_link}'
                    folder.mkdir()
                    target, other = folder / 'file', self.tmp / 'other'
                    if not created:
                        target.write_text('original')
                    other.write_text('original')
                    change = Path(self.change(other, target))
                    other.write_text('changed')
                    outside = self.tmp / f'outside-{created}-{parent_link}'
                    outside.mkdir()
                    victim = outside / 'file'
                    victim.write_text('untouched')
                    target.unlink(missing_ok=True)
                    if parent_link:
                        folder.rmdir()
                        folder.symlink_to(outside, target_is_directory=True)
                    else:
                        target.symlink_to(victim)
                    result = self.run_script('undo', change, '--force', ok=False)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertIn('symlink', result.stderr)
                    self.assertEqual(victim.read_text(), 'untouched')
                    self.assertEqual(other.read_text(), 'changed')
                    self.assertTrue((folder if parent_link else target).is_symlink())
                    self.assertIsNone(json.loads((change / 'manifest.json').read_text())['reverted'])

    def test_begin_refuses_symlink_targets_and_parents(self):
        outside = self.tmp / 'outside'
        outside.mkdir()
        victim = outside / 'file'
        victim.write_text('untouched')
        parent = self.tmp / 'parent'
        parent.symlink_to(outside, target_is_directory=True)
        link = self.tmp / 'link'
        link.symlink_to(victim)
        for target in (link, parent / 'file', parent / 'created'):
            with self.subTest(target=target):
                result = self.run_script('begin', '--run', 'run', '--skill', 'skill', '--ledger', 'test',
                                         target, ok=False)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn('symlink', result.stderr)
                self.assertEqual(victim.read_text(), 'untouched')
                # Failed begins leave no manifest; remove their empty directories before retrying.
                shutil.rmtree(self.tmp / 'backups')


if __name__ == '__main__':
    unittest.main()
