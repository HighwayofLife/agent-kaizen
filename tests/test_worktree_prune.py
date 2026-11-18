import hashlib
import io
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import zlib
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/worktree-prune'


class WorktreePruneTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.primary, self.target = self.root / 'primary', self.root / 'target'
        self.home = self.root / 'home'
        self.journal = self.home / '.claude/audits/worktree-prunes'
        self.config = self.root / 'config'
        self.old = int(time.time()) - 3 * 86400
        self.env = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
        self.env.pop('KAIZEN_GIT', None)
        self.env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
                        HOME=str(self.home), CLAUDE_CONFIG_DIR=str(self.config), GIT_AUTHOR_NAME='Fixture',
                        GIT_COMMITTER_NAME='Fixture', GIT_AUTHOR_EMAIL='test@example.invalid',
                        GIT_COMMITTER_EMAIL='test@example.invalid',
                        GIT_AUTHOR_DATE=f'@{self.old} +0000', GIT_COMMITTER_DATE=f'@{self.old} +0000')
        self.git(self.root, 'init', '-qb', 'main', self.primary)
        (self.primary / 'tracked').write_text('committed\n')
        (self.primary / '.gitignore').write_text('private.local\nbuild/\n')
        (self.primary / '.gitattributes').write_text('tracked filter=fixture\n')
        self.git(self.primary, 'add', '.')
        self.git(self.primary, 'commit', '-qm', 'fixture')
        self.git(self.primary, 'worktree', 'add', '-qb', 'topic', self.target)
        self.common = self.primary / '.git'
        self.admin = Path(self.git(self.target, 'rev-parse', '--absolute-git-dir'))
        self.age()

    def git(self, path, *args):
        return subprocess.run(['git', '-C', str(path), *map(str, args)], env=self.env,
                              check=True, capture_output=True, text=True).stdout.strip()

    def age(self):
        for path in [self.target, *self.target.rglob('*'), self.admin / 'HEAD',
                     self.admin / 'index', self.admin / 'logs/HEAD', self.common / 'logs/refs/heads/topic']:
            if path.exists():
                os.utime(path, (self.old, self.old), follow_symlinks=False)

    def refused(self, reason, *, cwd=None, project=None, record=None, path=None, **env):
        before = self.git(self.primary, 'worktree', 'list', '--porcelain')
        refs = self.git(self.primary, 'show-ref')
        args = ['undo', str(record)] if record else ['apply', '--path', str(path or self.target)]
        result = subprocess.run([str(SCRIPT), *args, '--project', str(project or self.primary)],
                                env=dict(self.env, **env), cwd=cwd or self.primary,
                                capture_output=True, text=True)
        self.assertEqual((result.returncode, result.stdout), (2, ''), result.stderr)
        self.assertIn(reason, result.stderr)
        self.assertEqual(self.git(self.primary, 'worktree', 'list', '--porcelain'), before)
        self.assertEqual(self.git(self.primary, 'show-ref'), refs)

    def test_unknown_admin_file_and_bounded_private_walk(self):
        patch_file = self.admin / 'saved.patch'
        patch_file.write_text('valuable patch')
        self.refused('unrecognized worktree metadata')
        patch_file.unlink()
        namespace = self.script_functions()
        refs = self.admin / 'refs'
        refs.mkdir(exist_ok=True)
        for number in range(3):
            (refs / str(number)).mkdir()
        with patch.dict(namespace['check_metadata'].__globals__, MAX_WALK_ENTRIES=2):
            with self.assertRaisesRegex(namespace['Refused'], 'limit'):
                namespace['check_metadata'](self.admin, self.common)

    def test_shebang_does_not_use_path_interpreter(self):
        self.assertTrue(SCRIPT.read_text().startswith('#!/usr/bin/python3 -I\n'))

    def test_eligible_apply_and_protected_directories(self):
        self.refused('eligible worktree')
        self.assertFalse(self.home.exists())
        nested = self.target / 'nested'
        nested.mkdir()
        for cwd in (self.target, nested):
            self.refused('current directory', cwd=cwd)
        self.refused('supplied project', project=nested)

    def test_hidden_ignored_and_generated_entries(self):
        tracked = self.target / 'tracked'
        tracked.write_text('local edits\n')
        for flag in ('assume-unchanged', 'skip-worktree'):
            self.git(self.target, 'update-index', '--' + flag, 'tracked')
            self.age()
            self.refused('hidden entries')
            self.git(self.target, 'update-index', '--no-' + flag, 'tracked')
        self.git(self.target, 'restore', 'tracked')
        for name in ('private.local', 'build'):
            entry = self.target / name
            entry.mkdir() if name == 'build' else entry.touch()
            self.age()
            self.refused('worktree has')
            entry.rmdir() if entry.is_dir() else entry.unlink()
        self.git(self.target, 'init', '-q', self.target / 'nested')
        self.age()
        self.refused('worktree has')

    def test_overrides_do_not_hide_changes_or_enable_filters(self):
        (self.target / 'untracked').write_text('local edits\n')
        self.git(self.target, 'config', 'status.showUntrackedFiles', 'no')
        self.age()
        self.refused('worktree has changes', GIT_INDEX_FILE=str(self.common / 'index'),
                     GIT_DIR=str(self.common), GIT_WORK_TREE=str(self.primary))
        self.git(self.target, 'config', 'filter.fixture.clean', 'false')
        self.refused('unsafe Git configuration')

    def test_locked_recent_sparse_or_unmerged(self):
        self.git(self.primary, 'worktree', 'lock', self.target)
        self.refused('locked')
        self.git(self.primary, 'worktree', 'unlock', self.target)
        (self.target / 'tracked').touch()
        self.refused('not idle')
        self.git(self.target, 'config', 'core.sparseCheckout', 'true')
        self.refused('sparse checkout')
        self.git(self.target, 'config', '--unset', 'core.sparseCheckout')
        self.git(self.target, 'commit', '--allow-empty', '-qm', 'unmerged')
        self.age()
        self.refused('not provably merged')

    def test_undo_refuses_moved_branch_and_disables_recreation(self):
        tip = self.git(self.target, 'rev-parse', 'HEAD')
        self.git(self.primary, 'worktree', 'remove', self.target)
        self.journal.mkdir(parents=True, mode=0o700)
        record = self.journal / 'fixture.json'
        record.write_text(json.dumps(dict(v=1, phase='removed', project=str(self.primary),
                                          common=str(self.common), path=str(self.target),
                                          branch='refs/heads/topic', branch_tip=tip)))
        record.chmod(0o600)
        self.refused('disabled pending safe removal', record=record)
        redirected = self.config / 'audits/worktree-prunes'
        redirected.mkdir(parents=True, mode=0o700)
        shutil.copy2(record, redirected / record.name)
        self.refused('outside the private journal', record=redirected / record.name)
        forged = json.loads(record.read_text())
        forged['path'] = str(self.root / 'unrelated')
        (self.journal / 'forged.json').write_text(json.dumps(forged))
        (self.journal / 'forged.json').chmod(0o600)
        self.refused('disabled pending safe removal', record=self.journal / 'forged.json')
        self.assertFalse(Path(forged['path']).exists())
        self.git(self.primary, 'commit', '--allow-empty', '-qm', 'new tip')
        self.git(self.primary, 'branch', '-f', 'topic', 'main')
        self.refused('branch tip no longer equals', record=record)
        self.assertFalse(self.target.exists())

    def test_main_and_unregistered_directories(self):
        self.refused('not an eligible linked worktree', path=self.primary, cwd=self.root,
                     project=self.target)
        unrelated = self.root / 'unregistered'
        unrelated.mkdir()
        self.refused('not an eligible linked worktree', path=unrelated)

    def test_wrong_common_and_forged_admin(self):
        unrelated = self.root / 'unrelated'
        self.git(self.root, 'init', '-q', unrelated)
        (self.admin / 'commondir').write_text(f'{unrelated / ".git"}\n')
        self.refused('inconsistent Git directories')
        (self.admin / 'commondir').write_text('../..\n')
        for fake in (self.root / 'fake', self.admin.with_name('fake')):
            with self.subTest(fake=fake):
                shutil.copytree(self.admin, fake)
                (fake / 'commondir').write_text(f'{self.common}\n')
                (self.target / '.git').write_text(f'gitdir: {fake}\n')
                self.refused('registration' if fake.parent == self.admin.parent
                             else 'inconsistent Git directories')

    def test_registered_worktrees_overlap_in_either_direction(self):
        nested = self.target / 'nested'
        self.git(self.primary, 'worktree', 'add', '-qb', 'nested', nested)
        self.refused('overlaps another registered worktree')
        self.refused('overlaps another registered worktree', path=nested)

    def check_alias(self, alias):
        self.refused('alias', path=alias)
        self.refused('current directory', cwd=alias)
        self.refused('supplied project', project=alias)

    def test_symlink_alias(self):
        alias = self.target.with_name('alias')
        alias.symlink_to(self.target, target_is_directory=True)
        self.check_alias(alias)

    def test_case_alias(self):
        alias = self.target.with_name('TARGET')
        if not alias.exists():
            self.skipTest('case-sensitive volume')
        self.check_alias(alias)

    def test_detached_head_and_missing_branch(self):
        self.git(self.target, 'checkout', '-q', '--detach')
        self.refused('detached')
        self.git(self.target, 'checkout', '-q', 'topic')
        (self.common / 'refs/heads/topic').unlink()
        self.refused('Git check failed')

    def test_staged_and_unstaged_edits(self):
        (self.target / 'tracked').write_text('dirty\n')
        self.age()
        self.refused('changes to tracked bytes')
        self.git(self.target, 'add', 'tracked')
        self.age()
        self.refused('index does not equal HEAD')

    def test_same_size_and_mtime_edit(self):
        tracked = self.target / 'tracked'
        old = tracked.stat()
        self.git(self.target, 'update-index', '--refresh')
        os.utime(self.admin / 'index', (self.old + 60, self.old + 60))
        tracked.write_bytes(b'otherdata\n')
        os.utime(tracked, ns=(old.st_atime_ns, old.st_mtime_ns))
        self.assertEqual(tracked.stat().st_size, old.st_size)
        self.assertEqual(self.git(self.target, '-c', 'core.trustctime=false', 'status', '--porcelain'), '')
        self.refused('changes to tracked bytes')

    def test_executable_bit_change(self):
        (self.target / 'tracked').chmod(0o755)
        self.refused('worktree has changes')

    def test_gitlink(self):
        tip = self.git(self.target, 'rev-parse', 'HEAD')
        self.git(self.target, 'update-index', '--add', '--cacheinfo', f'160000,{tip},submodule')
        self.git(self.target, 'commit', '-qm', 'gitlink')
        self.git(self.primary, 'merge', '--ff-only', 'topic')
        self.age()
        self.refused('HEAD has submodules')

    def test_intent_to_add(self):
        (self.target / 'new').touch()
        self.git(self.target, 'add', '--intent-to-add', 'new')
        self.age()
        self.refused('index has hidden entries')

    def test_blob_must_exist_with_matching_type_and_size(self):
        oid = self.git(self.target, 'rev-parse', 'HEAD:tracked')
        blob = self.common / 'objects' / oid[:2] / oid[2:]
        blob.unlink()
        self.refused('blob is missing')
        for data in (b'blob 1\0x', b'tree 0\0'):
            with self.subTest(data=data):
                blob.write_bytes(zlib.compress(data))
                self.refused('unexpected type or size')

    def test_blob_payload_must_hash_to_its_oid(self):
        oid = self.git(self.target, 'rev-parse', 'HEAD:tracked')
        blob = self.common / 'objects' / oid[:2] / oid[2:]
        blob.unlink()
        blob.write_bytes(zlib.compress(b'blob 10\0corrupted\n'))
        output = subprocess.run(['git', '-C', str(self.target), 'cat-file', '--batch-check'],
                                input=oid + '\n', env=self.env, capture_output=True, text=True, check=True)
        self.assertEqual(output.stdout, f'{oid} blob 10\n')
        self.refused('Git blob payload does not match its object ID')

    def test_blob_payload_is_streamed_across_chunks(self):
        tracked = self.primary / 'tracked'
        tracked.write_bytes(b'x' * (2 * 1024 * 1024))
        self.git(self.primary, 'commit', '-qam', 'large blob')
        self.git(self.target, 'merge', '--ff-only', 'main')
        self.age()
        self.refused('eligible worktree')

    def test_refuses_alternates_into_checkout_or_admin(self):
        oid = self.git(self.target, 'rev-parse', 'HEAD:tracked')
        objects = self.common / 'objects'
        blob = objects / oid[:2] / oid[2:]
        alternate = self.admin / 'objects'
        borrowed = alternate / oid[:2] / oid[2:]
        borrowed.parent.mkdir(parents=True)
        blob.rename(borrowed)
        alternate_file = objects / 'info/alternates'
        self.refused('Git blob is missing', GIT_ALTERNATE_OBJECT_DIRECTORIES=str(alternate))
        alternate_file.write_text(os.path.relpath(alternate, objects) + '\n')
        self.assertEqual(self.git(self.target, 'cat-file', '-t', oid), 'blob')
        self.refused('alternate object directory is inside the removal scope')
        (objects / 'alias').symlink_to(borrowed.parent)
        alternate_file.write_text('"alias/.."\n')
        self.assertEqual(self.git(self.target, 'cat-file', '-t', oid), 'blob')
        self.refused('alternate object directory is inside the removal scope')

        external = self.root / 'external-objects'
        (external / 'info').mkdir(parents=True)
        alternate_file.write_text(str(external) + '\n')
        (external / 'info/alternates').write_text(str(alternate) + '\n')
        self.refused('alternate object directory is inside the removal scope')
        (external / 'info/alternates').unlink()
        external_blob = external / oid[:2] / oid[2:]
        external_blob.parent.mkdir()
        borrowed.rename(external_blob)
        self.refused('eligible worktree')

        (alternate / 'info').mkdir()
        checkout_objects = self.target / 'objects'
        checkout_objects.mkdir()
        (alternate / 'info/alternates').write_text(str(checkout_objects) + '\n')
        self.age()
        self.refused('alternate object directory is inside the removal scope')

    def test_alternates_entries_fail_closed(self):
        alternate_file = self.common / 'objects/info/alternates'
        external = self.root / 'external-objects'
        external.mkdir()
        checkout_objects = self.target

        for suffix in (b':' + os.fsencode(self.admin / 'objects'), b'garbage'):
            with self.subTest(suffix=suffix):
                alternate_file.write_bytes(b'"' + os.fsencode(external) + b'"' + suffix + b'\n')
                self.refused('cannot safely resolve Git alternates')
        for entry in (b'"unterminated', b'"bad\\q"', b'"bad\\000"', b'bad\0path'):
            with self.subTest(entry=entry):
                alternate_file.write_bytes(entry + b'\n')
                self.refused('cannot safely resolve Git alternates')

        alternate_file.write_bytes(os.fsencode(external) + b':' + os.fsencode(checkout_objects) + b'\n')
        self.refused('cannot safely resolve Git alternates')
        alternate_file.write_bytes(os.fsencode(external) + b'\n')
        self.refused('eligible worktree')

    def test_alternate_path_with_colon_inside_checkout(self):
        alternate = self.target / 'objects:store'
        alternate.mkdir()
        (self.common / 'objects/info/alternates').write_text(str(alternate) + '\n')
        self.age()
        self.refused('alternate object directory is inside the removal scope')

    def test_index_extensions_refuse_private_or_unknown_data(self):
        index = self.admin / 'index'
        for version in (2, 4):
            self.git(self.target, 'update-index', '--index-version', version)
            original = index.read_bytes()
            oid = bytes.fromhex(self.git(self.target, 'rev-parse', 'HEAD:tracked'))
            for name, data in ((b'REUC', b'tracked\0' + b'100644\0' * 3 + oid * 3),
                               (b'ABCD', b'\0')):
                with self.subTest(version=version, name=name):
                    raw = original[:-20] + name + len(data).to_bytes(4, 'big') + data
                    index.write_bytes(raw + hashlib.sha1(raw).digest())
                    self.age()
                    self.refused('index extension ' + name.decode())
            index.write_bytes(original)
        self.git(self.target, 'update-index', '--split-index')
        self.age()
        self.refused('index extension link')

    def test_private_config_and_reflogs(self):
        for name in ('config.worktree', 'logs/refs/arbitrary/value', 'logs/SECONDARY'):
            with self.subTest(name=name):
                path = self.admin / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'')
                self.refused(name)
                path.unlink()

    def test_private_refs_and_shared_stash(self):
        tip = self.git(self.target, 'rev-parse', 'HEAD')
        self.git(self.primary, 'update-ref', 'refs/stash', tip)
        self.refused('eligible worktree')
        for name in ('refs/worktree/private', 'refs/bisect/private', 'refs/rewritten/private',
                     'refs/stash', 'packed-refs'):
            with self.subTest(name=name):
                ref = self.admin / name
                ref.parent.mkdir(parents=True, exist_ok=True)
                ref.write_text(f'{tip}\n')
                self.refused('worktree has private refs')
                ref.unlink()

    def test_unretained_and_malformed_head_reflog(self):
        self.git(self.target, 'checkout', '-q', '--detach')
        self.git(self.target, 'commit', '--allow-empty', '-qm', 'reflog only')
        self.git(self.target, 'checkout', '-q', 'topic')
        self.age()
        self.refused('reflog has unretained commits')
        (self.admin / 'logs/HEAD').write_bytes(b'malformed\n')
        self.refused('cannot parse worktree HEAD reflog')

    def test_preflight_never_runs_repository_commands(self):
        marker = self.root / 'executed'
        commands = self.target / 'commands'
        commands.mkdir()
        for name in ('git', 'post-checkout'):
            executable = commands / name
            executable.write_text(f'#!/bin/sh\ntouch "{marker}"\n')
            executable.chmod(0o755)
        command = commands / 'post-checkout'
        self.git(self.target, 'config', 'core.hooksPath', commands)
        self.git(self.target, 'config', 'core.fsmonitor', command)
        self.age()
        env = dict(PATH=f'{commands}{os.pathsep}{self.env["PATH"]}')
        self.refused('worktree has changes', **env)
        self.git(self.target, 'config', 'filter.fixture.clean', command)
        self.refused('unsafe Git configuration', **env)
        self.assertFalse(marker.exists())

    def test_git_override_must_be_external_regular_absolute_file(self):
        sibling = self.root / 'sibling'
        self.git(self.primary, 'worktree', 'add', '-qb', 'sibling', sibling)
        # The registration remains even when the checkout marker is missing.
        (sibling / '.git').unlink()
        alias = self.root / 'alias'
        alias.symlink_to(sibling, target_is_directory=True)
        marker = self.root / 'executed'
        external = self.root / 'git'
        real = shutil.which('git')
        external.write_text(f'#!/bin/sh\ntouch "{marker}"\nexec "{real}" "$@"\n')
        external.chmod(0o755)
        self.refused('eligible worktree', KAIZEN_GIT=str(external))
        marker.unlink()
        symlink = self.root / 'git-link'
        symlink.symlink_to(external)
        for directory in (self.primary, self.common, sibling):
            shutil.copy2(external, directory / 'git')
        for override in ('git', symlink, self.root, self.primary / 'git', self.common / 'git',
                         alias / 'git'):
            with self.subTest(override=override):
                self.refused('unknown', KAIZEN_GIT=str(override))
                self.assertFalse(marker.exists())

    def test_direct_execution_ignores_pythonpath_startup_hooks(self):
        marker = self.root / 'startup-executed'
        (self.root / 'sitecustomize.py').write_text(f'open({str(marker)!r}, "w").close()\n')
        self.refused('eligible worktree', PYTHONPATH=str(self.root))
        self.assertFalse(marker.exists())

    def test_live_scan_refuses_untracked_xattrs(self):
        locations = [(self.target / 'tracked', 'tracked'), (self.target, '.'),
                     *((self.admin / name, 'admin/' + name) for name in ('index', 'HEAD', 'logs/HEAD'))]
        for path, label in locations:
            with self.subTest(label=label):
                if hasattr(os, 'setxattr'):
                    os.setxattr(path, 'user.fixture', b'private')
                elif sys.platform == 'darwin':
                    subprocess.run(['xattr', '-w', 'com.apple.quarantine', 'fixture', str(path)], check=True)
                    self.refused('eligible worktree')
                    subprocess.run(['xattr', '-w', 'user.fixture', 'private', str(path)], check=True)
                else:
                    self.skipTest('no xattr setter for this platform')
                self.refused(f'extended attributes at {label!r}')
                if hasattr(os, 'removexattr'):
                    os.removexattr(path, 'user.fixture')
                else:
                    subprocess.run(['xattr', '-d', 'user.fixture', str(path)], check=True)

    def test_unavailable_xattrs_are_a_json_residual(self):
        functions = self.script_functions()
        argv = [str(SCRIPT), 'apply', '--project', str(self.primary), '--path', str(self.target)]
        with patch.dict(functions, {'xattr_reader': lambda: None}), patch.object(sys, 'argv', argv):
            with patch.object(sys, 'stderr', io.StringIO()) as err, self.assertRaises(SystemExit) as raised:
                functions['main']()
        self.assertEqual(raised.exception.code, 2)
        message, separator, residual = err.getvalue().partition('{')
        self.assertIn('eligible worktree', message)
        self.assertTrue(separator, err.getvalue())
        self.assertEqual(json.loads(separator + residual), {'xattrs': 'unchecked'})

    def script_functions(self):
        with patch.object(sys, 'path', [str(SCRIPT.parent), *sys.path]):
            return runpy.run_path(str(SCRIPT))['apply'].__globals__

    def test_git_resolver_uses_absolute_path(self):
        resolve_git = self.script_functions()['resolve_git']
        with patch.dict(os.environ, {'PATH': str(self.target)}):
            os.environ.pop('KAIZEN_GIT', None)
            locations = ('/usr/bin/git', '/opt/homebrew/bin/git', '/usr/local/bin/git')
            self.assertIn(resolve_git(self.primary), [Path(path).resolve() for path in locations])

    def test_identity_swap_between_passes(self):
        functions = self.script_functions()
        preflight = functions['preflight']
        calls = []

        def swap(*args):
            result = preflight(*args)
            if not calls:
                retired = self.target.with_name('retired')
                self.target.rename(retired)
                shutil.copytree(retired, self.target)
            calls.append(result)
            return result

        args = type('Args', (), dict(project=str(self.primary), path=str(self.target)))
        with patch.dict(functions, {'preflight': swap}):
            with self.assertRaisesRegex(functions['Refused'], 'identity .* changed'):
                functions['apply'](args)
        self.assertEqual(len(calls), 2)
