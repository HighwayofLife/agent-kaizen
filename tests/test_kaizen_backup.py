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
        self.env.pop('CLAUDE_CONFIG_DIR', None)

    def run_script(self, *args, ok=True):
        result = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], env=self.env,
                                cwd=self.tmp, capture_output=True, text=True)
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return result

    def change(self, *files, run='r1', skill='trim'):
        return self.run_script('begin', '--skill', skill, '--ledger', 'test change', '--run', run, *files).stdout.strip()

    def test_begin_refuses_credential_paths_before_copying_any_file(self):
        home = self.tmp / 'home'
        config, codex = self.tmp / 'claude', self.tmp / 'codex'
        self.env.update(HOME=str(home), CLAUDE_CONFIG_DIR=str(config), CODEX_HOME=str(codex))
        paths = [root / name for root in (config, codex)
                 for name in ('.credentials.json', 'auth.json', 'access-token.json', 'client-secret.json')]
        paths += [home / name for name in ('.ssh/id_probe', '.aws/nested/config', '.gnupg/key',
                                          '.netrc', '.config/gh/hosts.yml', '.docker/config.json')]
        paths += [self.tmp / name for name in ('.env', '.env.example', 'nested/.env', 'nested/.env.local')]
        safe = self.tmp / 'safe.md'
        safe.write_text('ordinary instructions')
        for path in paths:
            with self.subTest(path=path):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('credential decoy')
                result = self.run_script('begin', '--skill', 'test', '--ledger', 'test', safe, path, ok=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('refusing to back up credential path', result.stderr)
                self.assertNotIn('credential decoy', result.stdout + result.stderr)
                self.assertEqual(list((self.tmp / 'backups').iterdir()), [])

    def test_begin_refuses_missing_credentials_and_symlink_aliases(self):
        config = self.tmp / 'config'
        config.mkdir()
        self.env['CLAUDE_CONFIG_DIR'] = str(config)
        credential = config / 'access-token.json'
        target = self.tmp / 'plain.json'
        target.write_text('decoy')
        credential.symlink_to(target)
        alias = self.tmp / 'alias.md'
        alias.symlink_to(credential)
        ssh = self.tmp / 'ssh-target'
        ssh.mkdir()
        home = self.tmp / 'home'
        home.mkdir()
        (home / '.ssh').symlink_to(ssh, target_is_directory=True)
        self.env['HOME'] = str(home)
        for path in (config / 'auth.json', credential, target, alias, ssh / 'missing-key'):
            with self.subTest(path=path):
                result = self.run_script('begin', '--skill', 'test', '--ledger', 'test', path, ok=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('refusing to back up credential path', result.stderr)
                self.assertEqual(list((self.tmp / 'backups').iterdir()), [])

    def test_begin_keeps_config_credential_globs_top_level(self):
        config = self.tmp / 'config'
        self.env['CLAUDE_CONFIG_DIR'] = str(config)
        path = config / 'docs/token-notes.json'
        path.parent.mkdir(parents=True)
        path.write_text('ordinary notes')
        change = Path(self.change(path))
        self.assertEqual((change / 'files/1').read_text(), 'ordinary notes')

    def test_begin_treats_credential_roots_as_literal_paths(self):
        config = self.tmp / 'config[probe],literal'
        config.mkdir()
        self.env['CLAUDE_CONFIG_DIR'] = str(config)
        path = config / 'auth.json'
        path.write_text('decoy')
        result = self.run_script('begin', '--skill', 'test', '--ledger', 'test', path, ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('refusing to back up credential path', result.stderr)
        self.assertEqual(list((self.tmp / 'backups').iterdir()), [])

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
        shutil.copy2(SCRIPT.with_name('kaizen_credentials.py'), installed / 'kaizen_credentials.py')
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

    def test_begin_resolves_symlink_targets_and_parents(self):
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
                change = Path(self.change(target))
                entry = json.loads((change / 'manifest.json').read_text())['files'][0]
                self.assertEqual(entry['path'], str(target.resolve()))
                self.assertEqual(entry['created'], not target.exists())
                self.assertEqual(victim.read_text(), 'untouched')

    def test_round_trip_with_symlinked_home_and_default_backup_root(self):
        home = self.tmp / 'home'
        home.mkdir()
        linked = self.tmp / 'linked-home'
        linked.symlink_to(home, target_is_directory=True)
        self.env.update(HOME=str(linked))
        self.env.pop('KAIZEN_BACKUP_DIR')
        target, created = home / 'CLAUDE.md', home / 'new.md'
        target.write_text('original')
        change = Path(self.change('~/CLAUDE.md', '~/new.md'))
        self.assertEqual(change.parent, home / '.claude/kaizen-backups')
        self.assertEqual([entry['path'] for entry in json.loads((change / 'manifest.json').read_text())['files']],
                         [str(target), str(created)])
        target.write_text('changed')
        created.write_text('created')
        self.run_script('finish', linked / '.claude/kaizen-backups' / change.name)
        self.run_script('undo', 'last')
        self.assertEqual(target.read_text(), 'original')
        self.assertFalse(created.exists())

    def test_round_trip_with_backup_root_behind_symlink(self):
        actual = self.tmp / 'actual-backups'
        actual.mkdir()
        linked = self.tmp / 'linked-backups'
        linked.symlink_to(actual, target_is_directory=True)
        self.env['KAIZEN_BACKUP_DIR'] = str(linked)
        target = self.tmp / 'CLAUDE.md'
        for which in ('last', 'run', 'explicit'):
            with self.subTest(which=which):
                target.write_text('original')
                change = Path(self.change(target))
                self.assertEqual(change.parent, actual)
                target.write_text('changed')
                self.run_script('finish', linked / change.name)
                self.run_script('undo', linked / change.name if which == 'explicit' else which)
                self.assertEqual(target.read_text(), 'original')

    def test_finish_rejects_replacement_symlinks(self):
        for parent_link in (False, True):
            with self.subTest(parent_link=parent_link):
                folder = self.tmp / f'target-{parent_link}'
                folder.mkdir()
                target = folder / 'file'
                target.write_text('original')
                change = Path(self.change(target))
                original = (change / 'manifest.json').read_bytes()
                outside = self.tmp / f'outside-{parent_link}'
                outside.mkdir()
                (outside / 'file').write_text('untouched')
                target.unlink()
                if parent_link:
                    folder.rmdir()
                    folder.symlink_to(outside, target_is_directory=True)
                else:
                    target.symlink_to(outside / 'file')
                result = self.run_script('finish', change, ok=False)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn('symlink', result.stderr)
                self.assertEqual((change / 'manifest.json').read_bytes(), original)

    def test_undo_preflights_directory_targets_before_any_restore(self):
        for created in (False, True):
            for populated in (False, True):
                with self.subTest(created=created, populated=populated):
                    target = self.tmp / f'target-{created}-{populated}'
                    if not created:
                        target.write_text('original')
                    # A bad target in an older change must block the whole run's undo.
                    older = Path(self.change(target))
                    other = self.tmp / 'other'
                    other.write_text('original')
                    newer = Path(self.change(other))
                    other.write_text('changed')
                    self.run_script('finish', older)
                    self.run_script('finish', newer)
                    target.unlink(missing_ok=True)
                    target.mkdir()
                    if populated:
                        (target / 'child').write_text('untouched')
                    for flags in ((), ('--force',)):
                        result = self.run_script('undo', 'run', *flags, ok=False)
                        self.assertEqual(result.returncode, 2, result.stderr)
                        self.assertIn('target is a directory', result.stderr)
                        self.assertEqual(other.read_text(), 'changed')
                        self.assertTrue(target.is_dir())
                        if populated:
                            self.assertEqual((target / 'child').read_text(), 'untouched')
                        for change in (older, newer):
                            self.assertIsNone(json.loads((change / 'manifest.json').read_text())['reverted'])
                    # Keep the next subtest's run independent of the rejected one.
                    shutil.rmtree(self.tmp / 'backups')


    def test_undo_run_with_same_file_in_two_changes_restores_the_original(self):
        target = self.tmp / 'shared'
        target.write_text('v1')
        first = self.change(target, run='r1')
        target.write_text('v2')
        self.run_script('finish', first)
        second = self.change(target, run='r1')
        target.write_text('v3')
        self.run_script('finish', second)
        result = self.run_script('undo', 'run')
        self.assertNotIn('CONFLICT', result.stdout)
        self.assertEqual(target.read_text(), 'v1')

    def test_undo_run_with_same_file_still_conflicts_on_outside_edit(self):
        target = self.tmp / 'shared'
        target.write_text('v1')
        first = self.change(target, run='r1')
        target.write_text('v2')
        self.run_script('finish', first)
        second = self.change(target, run='r1')
        target.write_text('v3')
        self.run_script('finish', second)
        target.write_text('outside edit')
        result = self.run_script('undo', 'run', ok=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn('CONFLICT', result.stdout)
        self.assertEqual(target.read_text(), 'outside edit')

    def test_undo_run_conflicts_on_a_manual_edit_between_two_changes(self):
        target = self.tmp / 'shared'
        target.write_text('v1')
        first = self.change(target, run='r1')
        target.write_text('v2')
        self.run_script('finish', first)
        target.write_text('MANUAL-EDIT')
        second = self.change(target, run='r1')
        target.write_text('v3')
        self.run_script('finish', second)
        result = self.run_script('undo', 'run', ok=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn('CONFLICT', result.stdout)
        self.assertIn(str(target), result.stdout)
        self.assertIn(Path(first).name, result.stdout)
        self.assertIn(Path(second).name, result.stdout)
        self.assertEqual(target.read_text(), 'v3')
        self.assertEqual(self.run_script('list').stdout.count('open'), 2)
        self.run_script('undo', 'run', '--force')
        self.assertEqual(target.read_text(), 'v1')

    def test_undo_run_removes_file_created_by_one_change_and_edited_by_the_next(self):
        target = self.tmp / 'made'
        first = self.change(target, run='r1')
        target.write_text('v1')
        self.run_script('finish', first)
        second = self.change(target, run='r1')
        target.write_text('v2')
        self.run_script('finish', second)
        self.run_script('undo', 'run')
        self.assertFalse(target.exists())

    def test_undo_unfinished_change_with_created_file_is_a_conflict(self):
        edited, created = self.tmp / 'edited', self.tmp / 'created'
        edited.write_text('original')
        change = Path(self.change(edited, created))
        edited.write_text('half done')
        created.write_text('orphan')
        result = self.run_script('undo', change, ok=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn(str(created), result.stdout)
        self.assertIn('never finished', result.stdout)
        self.assertEqual((edited.read_text(), created.read_text()), ('half done', 'orphan'))
        self.assertIsNone(json.loads((change / 'manifest.json').read_text())['reverted'])
        self.run_script('undo', change, '--force')
        self.assertEqual(edited.read_text(), 'original')
        self.assertFalse(created.exists())
        self.assertTrue(json.loads((change / 'manifest.json').read_text())['reverted'])

    def test_undo_unfinished_change_without_created_file_still_reverts(self):
        edited, created = self.tmp / 'edited', self.tmp / 'created'
        edited.write_text('original')
        change = Path(self.change(edited, created))
        edited.write_text('half done')
        self.run_script('undo', change)
        self.assertEqual(edited.read_text(), 'original')
        self.assertTrue(json.loads((change / 'manifest.json').read_text())['reverted'])

    def test_newest_change_is_decided_by_created_at_not_run_id_text(self):
        target = self.tmp / 'target'
        target.write_text('x')
        older = self.change(target, run='weekly-1')
        newer = self.change(target, run='20991231-000000')
        lines = self.run_script('list').stdout.splitlines()
        self.assertEqual([line.split('\t')[0] for line in lines], [newer, older])
        self.run_script('undo', 'last')
        self.assertTrue(json.loads((Path(newer) / 'manifest.json').read_text())['reverted'])
        self.assertIsNone(json.loads((Path(older) / 'manifest.json').read_text())['reverted'])

    def test_manifest_without_created_at_sorts_by_run_id(self):
        target = self.tmp / 'target'
        target.write_text('x')
        old = Path(self.change(target, run='a-old'))
        manifest = json.loads((old / 'manifest.json').read_text())
        del manifest['created_at']
        (old / 'manifest.json').write_text(json.dumps(manifest))
        new = self.change(target, run='0-new')
        lines = self.run_script('list').stdout.splitlines()
        self.assertEqual([line.split('\t')[0] for line in lines], [new, str(old)])

    def test_failed_begin_leaves_no_folder_and_a_retry_works(self):
        good, folder = self.tmp / 'good', self.tmp / 'folder'
        good.write_text('x')
        folder.mkdir()
        result = self.run_script('begin', '--run', 'r3', '--skill', 'e', '--ledger', 't', good, folder, ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('not a regular file', result.stderr)
        self.assertEqual(list((self.tmp / 'backups').iterdir()), [])
        change = Path(self.change(good, run='r3', skill='e'))
        self.assertEqual(change.name, 'r3-01-e')

    def test_begin_numbers_changes_from_folder_names_when_a_manifest_is_missing(self):
        good = self.tmp / 'good'
        good.write_text('x')
        (self.tmp / 'backups/r4-01-e').mkdir(parents=True)
        self.assertEqual(Path(self.change(good, run='r4', skill='e')).name, 'r4-02-e')

    def test_corrupt_manifests_are_skipped_with_a_warning_naming_the_file(self):
        target = self.tmp / 'target'
        target.write_text('original')
        change = self.change(target)
        target.write_text('changed')
        self.run_script('finish', change)
        root = self.tmp / 'backups'
        (root / 'bad-json').mkdir()
        (root / 'bad-json/manifest.json').write_text('{broken')
        (root / 'bad-keys').mkdir()
        (root / 'bad-keys/manifest.json').write_text('{}')
        (root / 'bad-read/manifest.json').mkdir(parents=True)
        for args in (('list',), ('undo', 'last')):
            result = self.run_script(*args)
            for name in ('bad-json', 'bad-keys', 'bad-read'):
                self.assertIn(str(root / name / 'manifest.json'), result.stderr)
            self.assertNotIn('Traceback', result.stderr)
        self.assertEqual(target.read_text(), 'original')
        self.run_script('begin', '--run', 'r2', '--skill', 's', '--ledger', 't', target)  # not blocked

    def test_undo_of_a_named_corrupt_manifest_names_the_file_without_traceback(self):
        root = self.tmp / 'backups'
        for name, text in (('bad-json', '{broken'), ('bad-keys', '{}')):
            (root / name).mkdir(parents=True)
            (root / name / 'manifest.json').write_text(text)
            result = self.run_script('undo', root / name, ok=False)
            self.assertEqual(result.returncode, 2)
            self.assertIn(str(root / name / 'manifest.json'), result.stderr)
            self.assertNotIn('Traceback', result.stderr)

    def test_backup_folders_are_private_and_restore_keeps_the_file_mode(self):
        self.env.pop('KAIZEN_BACKUP_DIR')
        self.env['CLAUDE_CONFIG_DIR'] = str(self.tmp / 'config')
        root = self.tmp / 'config' / 'kaizen-backups'
        root.mkdir(parents=True)
        root.chmod(0o755)
        target = self.tmp / 'target'
        target.write_text('original')
        target.chmod(0o640)
        change = Path(self.change(target))
        target.write_text('changed')
        self.run_script('finish', change)
        self.assertEqual(root.stat().st_mode & 0o777, 0o700)
        self.assertEqual(change.stat().st_mode & 0o777, 0o700)
        self.assertEqual((change / 'files').stat().st_mode & 0o777, 0o700)
        target.chmod(0o600)
        self.run_script('undo', 'last')
        self.assertEqual(target.read_text(), 'original')
        self.assertEqual(target.stat().st_mode & 0o777, 0o640)

    def test_user_chosen_existing_backup_root_keeps_its_mode(self):
        root = self.tmp / 'backups'
        root.mkdir()
        root.chmod(0o755)
        target = self.tmp / 'target'
        target.write_text('x')
        change = Path(self.change(target))
        self.assertEqual(root.stat().st_mode & 0o777, 0o755)
        self.assertEqual(change.stat().st_mode & 0o777, 0o700)

    def test_new_backup_root_is_private(self):
        target = self.tmp / 'target'
        target.write_text('x')
        self.change(target)
        self.assertEqual((self.tmp / 'backups').stat().st_mode & 0o777, 0o700)

    def test_default_root_follows_claude_config_dir_and_explicit_dir_wins(self):
        home, config = self.tmp / 'home', self.tmp / 'config'
        home.mkdir()
        self.env.update(HOME=str(home), CLAUDE_CONFIG_DIR=str(config))
        self.env.pop('KAIZEN_BACKUP_DIR')
        target = self.tmp / 'target'
        target.write_text('x')
        self.assertEqual(Path(self.change(target)).parent, config / 'kaizen-backups')
        self.assertFalse((home / '.claude').exists())
        self.env['KAIZEN_BACKUP_DIR'] = str(self.tmp / 'explicit')
        self.assertEqual(Path(self.change(target)).parent, self.tmp / 'explicit')


if __name__ == '__main__':
    unittest.main()
