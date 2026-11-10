"""Security and configuration regressions for the scheduled runner (S-1, S-4, S-7 to S-9, S-13 to S-15)."""
from contextlib import redirect_stderr, redirect_stdout
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

from test_runner import STUB_AUDIT, STUB_CLAUDE
from test_scripts import SCRIPTS, StubCase, executable, jsonl, write


class SecurityCase(StubCase):
    def setUp(self):
        super().setUp()
        self.cfg = self.root / 'cfg'
        self.cx = self.root / 'cx'
        self.audits = self.root / 'audits'
        self.env.update(CLAUDE_CONFIG_DIR=str(self.cfg), CODEX_HOME=str(self.cx),
                        GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull,
                        GIT_AUTHOR_NAME='Test', GIT_AUTHOR_EMAIL='test@example.invalid',
                        GIT_COMMITTER_NAME='Test', GIT_COMMITTER_EMAIL='test@example.invalid',
                        AUDIT_RECORD=str(self.root / 'audit-calls.jsonl'), STUB_AUDITS=str(self.audits),
                        CLAUDE_PLUGIN_ROOT=str(SCRIPTS.parent))
        for name in ('STUB_EXIT', 'STUB_AUDIT_EXIT', 'STUB_KILL', 'STUB_FAIL_PROJECT',
                     'KAIZEN_BACKUP_DIR', 'KAIZEN_REVIEW_MODEL', 'KAIZEN_REVIEW_MAX_TURNS'):
            self.env.pop(name, None)
        environment = patch.dict(os.environ, self.env, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        loader = importlib.machinery.SourceFileLoader('kaizen_scheduled_security', str(SCRIPTS / 'kaizen-scheduled'))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        self.runner = importlib.util.module_from_spec(spec)
        loader.exec_module(self.runner)
        self.claude = executable(self.bin / 'stub claude', STUB_CLAUDE)
        self.audit = executable(self.bin / 'stub token-audit', STUB_AUDIT)
        self.pricing = write(self.root / 'pricing.json', '{}')
        self.global_path = self.cfg / 'agent-kaizen.json'

    def project(self, name, config='{}'):
        path = self.root / name
        write(path / 'docs/kaizen/config.json', config)
        return path

    def due(self, name, config='{}'):
        path = self.project(name, config)
        jsonl(self.cfg / 'projects' / 'lossy-folder' / (name + '.jsonl'),
              [dict(type='user', cwd=str(path))])
        return path

    def script(self, *args, code=0):
        return self.run_script('kaizen-scheduled', *args, code=code)

    def review(self, *args, code=0):
        return self.script('review', '--audits', self.audits, '--claude', self.claude,
                           '--token-audit', self.audit, '--pricing', self.pricing, *args, code=code)

    def git(self, path, *args):
        result = subprocess.run(['git', '-C', str(path), *args], env=self.env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def last_argv(self):
        return self.calls()[-1]['argv']

    @staticmethod
    def values(argv, flag):
        return [argv[index + 1] for index, value in enumerate(argv) if value == flag]

    def state(self, path):
        return json.loads((self.audits / 'projects' / self.runner.key(path) / 'state.json').read_text())

    def options(self):
        return self.runner.command_options(type('Args', (), {'dry_run': True})())


class AutoOptInTests(SecurityCase):
    """S-1: a tracked project file alone cannot switch a project to unattended auto mode."""

    def test_project_auto_without_opt_in_runs_as_propose(self):
        path = self.due('proj', '{"scheduledAutonomy":"auto"}')
        result = self.review('--project-dir', path)
        argv = self.last_argv()
        self.assertIn('/agent-kaizen:cycle propose-only ', self.values(argv, '-p')[0])
        self.assertEqual(self.values(argv, '--permission-mode'), ['dontAsk'])
        self.assertEqual(self.values(argv, '--allowedTools'), [self.runner.REVIEW_TOOLS])
        self.assertEqual(self.values(argv, '--tools'), [self.runner.REVIEW_AVAILABLE])
        self.assertIn('scheduledAutonomy=auto', result.stderr)
        self.assertIn('not in autoProjects', result.stderr)
        self.assertIn(f'config set --for {path} scheduledAutonomy=auto', result.stderr)

    def test_project_auto_with_opt_in_runs_as_auto(self):
        path = self.due('proj', '{"scheduledAutonomy":"auto"}')
        write(self.global_path, json.dumps({'autoProjects': [str(path)]}))
        result = self.review('--project-dir', path)
        argv = self.last_argv()
        self.assertIn('/agent-kaizen:cycle auto ', self.values(argv, '-p')[0])
        self.assertEqual(self.values(argv, '--permission-mode'), ['default'])
        self.assertEqual(self.values(argv, '--tools'), [self.runner.AUTO_AVAILABLE])
        self.assertNotIn('autoProjects', result.stderr)

    def test_opt_in_compares_resolved_paths(self):
        path = self.due('real', '{"scheduledAutonomy":"auto"}')
        alias = self.root / 'alias'
        alias.symlink_to(path, target_is_directory=True)
        write(self.global_path, json.dumps({'autoProjects': [str(alias)]}))
        self.assertEqual(self.runner.effective(path)['scheduledAutonomy'],
                         {'value': 'auto', 'source': 'project'})
        self.assertEqual(self.runner.effective(alias)['scheduledAutonomy']['value'], 'auto')

    def test_other_project_in_list_does_not_opt_in(self):
        path = self.project('proj', '{"scheduledAutonomy":"auto"}')
        write(self.global_path, json.dumps({'autoProjects': [str(self.root / 'other')]}))
        with redirect_stderr(io.StringIO()):
            self.assertEqual(self.runner.effective(path)['scheduledAutonomy']['value'], 'propose')

    def test_global_auto_still_works_without_opt_in(self):
        path = self.due('proj', '{}')
        write(self.global_path, '{"scheduledAutonomy":"auto"}')
        self.review('--project-dir', path)
        self.assertIn('/agent-kaizen:cycle auto ', self.values(self.last_argv(), '-p')[0])
        # A project file asking for auto adds nothing and loses nothing under global auto.
        write(path / 'docs/kaizen/config.json', '{"scheduledAutonomy":"auto"}')
        with redirect_stderr(io.StringIO()):
            self.assertEqual(self.runner.effective(path)['scheduledAutonomy']['value'], 'auto')
        write(path / 'docs/kaizen/config.json', '{"scheduledAutonomy":"propose"}')
        self.assertEqual(self.runner.effective(path)['scheduledAutonomy'],
                         {'value': 'propose', 'source': 'project'})

    def test_project_file_cannot_set_auto_projects(self):
        path = self.due('proj', json.dumps({'scheduledAutonomy': 'auto', 'autoProjects': []}))
        write(path / 'docs/kaizen/config.json', json.dumps({
            'scheduledAutonomy': 'auto', 'autoProjects': [str(path)]}))
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            data = self.runner.effective(path)
        self.assertEqual(data['autoProjects'], {'value': [], 'source': 'default'})
        self.assertEqual(data['scheduledAutonomy']['value'], 'propose')
        self.assertIn('autoProjects is global-only, ignored', stderr.getvalue())
        result = self.review('--project-dir', path)
        self.assertIn('/agent-kaizen:cycle propose-only ', self.values(self.last_argv(), '-p')[0])
        self.assertIn('autoProjects is global-only, ignored', result.stderr)
        result = self.script('config', 'set', '--for', path, 'autoProjects=[]', code=2)
        self.assertIn('autoProjects is global-only', result.stderr)

    def test_auto_projects_validation(self):
        valid = self.runner.valid_value
        self.assertTrue(valid('autoProjects', []))
        self.assertTrue(valid('autoProjects', ['/a/b', '/c']))
        for value in (['relative'], [''], [5], 'not-a-list', {'a': 1}, [' '], ['/a\0b']):
            with self.subTest(value=value):
                self.assertFalse(valid('autoProjects', value))
        write(self.global_path, '{"autoProjects":["relative"]}')
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            data = self.runner.effective()
        self.assertEqual(data['autoProjects'], {'value': [], 'source': 'default'})
        self.assertIn('autoProjects=', stderr.getvalue())
        self.script('config', 'set', 'autoProjects=["relative"]', code=2)

    def test_config_show_and_dry_run_make_the_downgrade_visible(self):
        path = self.due('proj', '{"scheduledAutonomy":"auto"}')
        shown = json.loads(self.script('config', 'show', '--for', path).stdout)
        self.assertEqual(shown['scheduledAutonomy']['value'], 'propose')
        self.assertIn('not in autoProjects', shown['scheduledAutonomy']['note'])
        self.assertIn('scheduledAutonomy=auto', shown['scheduledAutonomy']['note'])
        text = self.review('--dry-run', '--project-dir', path).stdout
        self.assertIn('scheduledAutonomy=propose', text)
        self.assertIn('note: ', text)
        self.assertIn('not in autoProjects', text)
        self.assertIn('/agent-kaizen:cycle propose-only', text)
        rows = json.loads(self.review('--dry-run', '--json', '--project-dir', path).stdout)
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]['path'], rows[0]['scheduledAutonomy']), (str(path), 'propose'))
        self.assertIn('not in autoProjects', rows[0]['note'])
        write(self.global_path, json.dumps({'autoProjects': [str(path)]}))
        shown = json.loads(self.script('config', 'show', '--for', path).stdout)
        self.assertEqual(shown['scheduledAutonomy'], {'value': 'auto', 'source': 'project'})
        rows = json.loads(self.review('--dry-run', '--json', '--project-dir', path).stdout)
        self.assertEqual(rows, [dict(path=str(path), scheduledAutonomy='auto', source='project')])

    def test_config_set_for_round_trip_updates_auto_projects(self):
        one, two = self.project('one'), self.project('two')
        write(self.global_path, json.dumps({'schedule': 'always', 'autoProjects': [str(two)]}))
        self.script('config', 'set', '--for', one, 'scheduledAutonomy=auto')
        self.assertEqual(json.loads((one / 'docs/kaizen/config.json').read_text()),
                         {'scheduledAutonomy': 'auto'})
        self.assertEqual(json.loads(self.global_path.read_text()),
                         {'schedule': 'always', 'autoProjects': [str(two), str(one)]})
        shown = json.loads(self.script('config', 'show', '--for', one).stdout)
        self.assertEqual(shown['scheduledAutonomy'], {'value': 'auto', 'source': 'project'})
        # Setting auto twice does not duplicate the entry.
        self.script('config', 'set', '--for', one, 'scheduledAutonomy=auto')
        self.assertEqual(json.loads(self.global_path.read_text())['autoProjects'], [str(two), str(one)])
        rows = json.loads(self.review('--dry-run', '--json', '--project-dir', one).stdout)
        self.assertEqual(rows, [dict(path=str(one), scheduledAutonomy='auto', source='project')])
        self.script('config', 'set', '--for', one, 'scheduledAutonomy=propose')
        self.assertEqual(json.loads((one / 'docs/kaizen/config.json').read_text()),
                         {'scheduledAutonomy': 'propose'})
        self.assertEqual(json.loads(self.global_path.read_text()),
                         {'schedule': 'always', 'autoProjects': [str(two)]})

    def test_config_set_for_uses_canonical_path_through_symlinks(self):
        path = self.project('real')
        alias = self.root / 'alias'
        alias.symlink_to(path, target_is_directory=True)
        self.script('config', 'set', '--for', alias, 'scheduledAutonomy=auto')
        self.assertEqual(json.loads(self.global_path.read_text())['autoProjects'], [str(path)])
        self.script('config', 'set', '--for', alias, 'scheduledAutonomy=propose')
        self.assertEqual(json.loads(self.global_path.read_text())['autoProjects'], [])

    def test_config_set_propose_without_opt_in_does_not_create_global_file(self):
        path = self.project('proj')
        self.script('config', 'set', '--for', path, 'scheduledAutonomy=propose')
        self.assertFalse(self.global_path.exists())

    def test_config_set_for_other_keys_leave_auto_projects_alone(self):
        path = self.project('proj')
        write(self.global_path, json.dumps({'autoProjects': [str(path)]}))
        self.script('config', 'set', '--for', path, 'schedule=always')
        self.assertEqual(json.loads(self.global_path.read_text()), {'autoProjects': [str(path)]})

    def test_config_set_for_with_unreadable_global_changes_nothing(self):
        path = self.project('proj')
        write(self.global_path, '{broken')
        result = self.script('config', 'set', '--for', path, 'scheduledAutonomy=auto', code=2)
        self.assertIn('invalid JSON', result.stderr)
        self.assertEqual((path / 'docs/kaizen/config.json').read_text(), '{}')
        self.assertEqual(self.global_path.read_text(), '{broken')

    # V1-1: the named directory is not always the project runs use.
    def nested(self, root_config='{"scheduledAutonomy": "auto"}'):
        repo = self.project('repo', root_config)
        package = repo / 'pkg'
        write(package / 'docs/kaizen/config.json', '{}')
        self.git(repo.parent, 'init', str(repo))
        self.git(repo, 'add', '.')
        self.git(repo, 'commit', '-m', 'init')
        return repo, package

    def test_auto_for_a_nested_project_is_refused_and_writes_nothing(self):
        repo, package = self.nested()
        write(self.global_path, json.dumps({'schedule': 'always'}))
        result = self.script('config', 'set', '--for', package, 'scheduledAutonomy=auto', code=2)
        lines = result.stderr.strip().splitlines()
        self.assertEqual(len(lines), 1, result.stderr)
        self.assertIn(str(package), lines[0])
        self.assertIn(f'config set --for {repo} scheduledAutonomy=auto', lines[0])
        self.assertEqual((package / 'docs/kaizen/config.json').read_text(), '{}')
        self.assertEqual(json.loads(self.global_path.read_text()), {'schedule': 'always'})
        self.assertEqual(json.loads((repo / 'docs/kaizen/config.json').read_text()),
                         {'scheduledAutonomy': 'auto'})

    def test_auto_refusal_creates_no_global_file(self):
        _, package = self.nested()
        self.script('config', 'set', '--for', package, 'scheduledAutonomy=auto', code=2)
        self.assertFalse(self.global_path.exists())

    def test_auto_for_the_canonical_root_works(self):
        repo, package = self.nested()
        result = self.script('config', 'set', '--for', repo, 'scheduledAutonomy=auto')
        self.assertEqual(result.stderr, '')
        self.assertEqual(json.loads(self.global_path.read_text())['autoProjects'], [str(repo)])

    def test_auto_for_a_linked_worktree_is_refused(self):
        repo, _ = self.nested('{}')
        worktree = self.root / 'linked'
        self.git(repo, 'worktree', 'add', str(worktree), '-b', 'wt')
        result = self.script('config', 'set', '--for', worktree, 'scheduledAutonomy=auto', code=2)
        self.assertIn(f'config set --for {repo} scheduledAutonomy=auto', result.stderr)
        self.assertEqual((worktree / 'docs/kaizen/config.json').read_text(), '{}')
        self.assertEqual((repo / 'docs/kaizen/config.json').read_text(), '{}')
        self.assertFalse(self.global_path.exists())

    def test_other_keys_for_a_subdirectory_land_in_the_canonical_file(self):
        repo, package = self.nested('{}')
        # The root is enrolled too, so runs use the root for everything below it.
        result = self.script('config', 'set', '--for', package, 'schedule=always')
        self.assertEqual(json.loads((repo / 'docs/kaizen/config.json').read_text()), {'schedule': 'always'})
        self.assertEqual((package / 'docs/kaizen/config.json').read_text(), '{}')
        self.assertEqual(result.stderr.strip().splitlines(),
                         [f'kaizen-scheduled: {package} is not the project runs use; '
                          f'wrote to {repo / "docs/kaizen/config.json"}'])
        # A plain subdirectory of a project: same rule.
        deep = package / 'src/deep'
        deep.mkdir(parents=True)
        result = self.script('config', 'set', '--for', deep, 'schedule=off')
        self.assertEqual(json.loads((repo / 'docs/kaizen/config.json').read_text()), {'schedule': 'off'})
        self.assertIn(str(repo / 'docs/kaizen/config.json'), result.stderr)

    def test_propose_for_a_worktree_removes_the_canonical_entry(self):
        repo, _ = self.nested('{}')
        worktree = self.root / 'linked'
        self.git(repo, 'worktree', 'add', str(worktree), '-b', 'wt')
        write(self.global_path, json.dumps({'autoProjects': [str(repo)]}))
        self.script('config', 'set', '--for', worktree, 'scheduledAutonomy=propose')
        self.assertEqual(json.loads(self.global_path.read_text())['autoProjects'], [])
        self.assertEqual(json.loads((repo / 'docs/kaizen/config.json').read_text()),
                         {'scheduledAutonomy': 'propose'})

    def test_a_directory_outside_any_project_is_still_an_error(self):
        outside = self.root / 'outside'
        outside.mkdir()
        self.script('config', 'set', '--for', outside, 'schedule=always', code=2)


class DiscoveryRootTests(SecurityCase):
    """S-4 and S-14: enrolled subdirectories of a larger repository."""

    def monorepo(self, *packages, root_enrolled=False):
        repo = self.root / 'mono'
        write(repo / 'README.md', 'x')
        if root_enrolled:
            write(repo / 'docs/kaizen/config.json', '{}')
        for package in packages:
            write(repo / package / 'docs/kaizen/config.json', '{}')
        self.git(repo.parent, 'init', str(repo))
        self.git(repo, 'add', '.')
        self.git(repo, 'commit', '-m', 'init')
        return repo

    def discover(self, project_dirs):
        return self.runner.discover(self.cfg / 'projects', self.cx / 'sessions', {}, project_dirs)

    def test_enrolled_subdirectory_is_its_own_project(self):
        repo = self.monorepo('pkg')
        projects, not_enrolled = self.discover([repo / 'pkg'])
        self.assertEqual([project.canonical for project in projects], [repo / 'pkg'])
        self.assertEqual(not_enrolled, [])
        # Session discovery walks up from a nested folder to the enrolled subdirectory.
        nested = repo / 'pkg/src/deep'
        nested.mkdir(parents=True)
        jsonl(self.cfg / 'projects/x/s.jsonl', [dict(type='user', cwd=str(nested))])
        projects, not_enrolled = self.runner.discover(self.cfg / 'projects', self.cx / 'sessions', {})
        self.assertEqual([project.canonical for project in projects], [repo / 'pkg'])
        self.assertEqual(not_enrolled, [])

    def test_two_enrolled_subdirectories_are_two_projects(self):
        repo = self.monorepo('a', 'b')
        projects, _ = self.discover([repo / 'b', repo / 'a'])
        self.assertEqual([project.canonical for project in projects], [repo / 'a', repo / 'b'])
        self.assertEqual(len({project.key for project in projects}), 2)
        self.assertEqual([project.paths for project in projects], [[repo / 'a'], [repo / 'b']])

    def test_git_root_is_canonical_only_when_enrolled(self):
        repo = self.monorepo('pkg', root_enrolled=True)
        projects, _ = self.discover([repo / 'pkg', repo])
        self.assertEqual([project.canonical for project in projects], [repo])
        self.assertIn(repo / 'pkg', projects[0].paths)

    def test_linked_worktrees_of_an_enrolled_subdirectory_group(self):
        repo = self.monorepo('pkg')
        worktree = self.root / 'mono-wt'
        self.git(repo, 'worktree', 'add', str(worktree), '-b', 'wt')
        projects, not_enrolled = self.discover([worktree / 'pkg'])
        self.assertEqual([project.canonical for project in projects], [repo / 'pkg'])
        self.assertEqual(projects[0].paths, sorted([repo / 'pkg', worktree / 'pkg']))
        self.assertEqual(not_enrolled, [])
        both, _ = self.discover([repo / 'pkg', worktree / 'pkg'])
        self.assertEqual(len(both), 1)

    def test_review_dry_run_lists_monorepo_subdirectory(self):
        repo = self.monorepo('pkg')
        text = self.review('--dry-run', '--project-dir', repo / 'pkg').stdout
        self.assertIn(f'project: {repo / "pkg"}', text)
        self.assertNotIn('not enrolled', text)

    def test_config_show_reports_the_real_run_folder(self):
        key = self.runner.key
        folder = lambda path: str(self.audits_root() / 'projects' / key(path)) + '/'
        repo = self.root / 'main'
        write(repo / 'docs/kaizen/config.json', '{}')
        self.git(repo.parent, 'init', str(repo))
        self.git(repo, 'add', '.')
        self.git(repo, 'commit', '-m', 'init')
        worktree = self.root / 'linked'
        self.git(repo, 'worktree', 'add', str(worktree), '-b', 'wt')
        self.assertTrue((worktree / 'docs/kaizen').is_dir())
        (repo / 'src/deep').mkdir(parents=True)
        mono = self.monorepo('pkg')
        for given, canonical in ((repo, repo), (worktree, repo), (repo / 'src/deep', repo),
                                 (mono / 'pkg', mono / 'pkg'), (mono / 'pkg/..' / 'pkg', mono / 'pkg')):
            with self.subTest(given=given):
                shown = json.loads(self.script('config', 'show', '--for', given).stdout)
                self.assertEqual(shown['reports'], folder(canonical))
        outside = self.root / 'outside'
        outside.mkdir()
        shown = json.loads(self.script('config', 'show', '--for', outside).stdout)
        self.assertEqual(shown['reports'], folder(outside))

    def audits_root(self):
        return self.cfg / 'audits'


class CredentialListTests(SecurityCase):
    HOME = ('.kube/config', '.npmrc', '.pypirc', '.git-credentials', '.netrc', '.config/gcloud/x',
            '.azure/x', '.config/op/x', '.terraform.d/credentials.tfrc.json', '.docker/config.json',
            '.config/gh/hosts.yml')
    PROJECT = ('.npmrc', '.envrc', 'a.pem', 'deploy.key', 'id_rsa', 'id_rsa.pub', 'id_ed25519',
               'id_ed25519.pub', '.env', '.env.example')

    def test_home_secret_stores_are_denied_in_both_modes(self):
        project = self.project('proj')
        options = self.options()
        for mode in ('auto', 'propose-only'):
            command = self.runner.review_command(options, mode, 'report', 'session', project)
            denied = set(self.values(command, '--disallowedTools')[0].split(','))
            home = self.home.resolve().as_posix().lstrip('/')
            for pattern in ('.kube/config', '.npmrc', '.pypirc', '.git-credentials', '.netrc',
                            '.config/gcloud/**', '.azure/**', '.config/op/**',
                            '.terraform.d/credentials.tfrc.json', '.docker/config.json', '.config/gh/**'):
                for tool in ('Read', 'Edit', 'Write'):
                    self.assertIn(f'{tool}(//{home}/{pattern})', denied, (mode, pattern))

    def test_project_secret_names_are_denied_in_every_directory(self):
        project = self.project('proj')
        command = self.runner.review_command(self.options(), 'auto', 'report', 'session', project)
        denied = set(self.values(command, '--disallowedTools')[0].split(','))
        root = project.as_posix().lstrip('/')
        for pattern in ('.npmrc', '.envrc', '*.pem', '*.key', 'id_rsa*', 'id_ed25519*', '.env', '.env.*'):
            for tool in ('Read', 'Edit', 'Write'):
                self.assertIn(f'{tool}(//{root}/**/{pattern})', denied, pattern)

    def test_is_credential_matches_new_paths(self):
        credentials = runpy.run_path(str(SCRIPTS / 'kaizen_credentials.py'))
        is_credential = credentials['is_credential']
        for relative in self.HOME:
            with self.subTest(relative=relative):
                self.assertTrue(is_credential(self.home / relative))
        self.assertFalse(is_credential(self.home / '.config/gcloudx/file'))
        self.assertFalse(is_credential(self.home / 'notes.txt'))
        previous = os.getcwd()
        os.chdir(self.work)
        try:
            for relative in self.PROJECT:
                with self.subTest(relative=relative):
                    self.assertTrue(is_credential(self.work / 'sub/dir' / relative))
                    self.assertTrue(is_credential(self.work / relative))
            self.assertFalse(is_credential(self.work / 'keyboard.txt'))
            self.assertFalse(is_credential(self.work / 'id_dsa_notes.txt'))
        finally:
            os.chdir(previous)


class AutoEditDenyTests(SecurityCase):
    """S-8: executable and trusted files stay read-only in unattended auto mode."""

    PROJECT = ('.claude/hooks/**', '.claude/agents/**', '.claude/commands/**', '.claude/skills/**',
               '.mcp.json', '.github/workflows/**', '.husky/**')

    def rules(self, project, mode):
        command = self.runner.review_command(self.options(), mode, 'report', 'session', project)
        return set(self.values(command, '--disallowedTools')[0].split(','))

    def test_auto_denies_edit_and_write_to_trusted_files(self):
        project = self.project('proj')
        denied = self.rules(project, 'auto')
        for root in dict.fromkeys((project, project.resolve())):
            for pattern in self.PROJECT:
                for tool in ('Edit', 'Write'):
                    self.assertIn(f'{tool}(//{root.as_posix().lstrip("/")}/{pattern})', denied)
        for root in dict.fromkeys((self.cfg, self.cfg.resolve())):
            for tool in ('Edit', 'Write'):
                self.assertIn(f'{tool}(//{root.as_posix().lstrip("/")}/agents/**)', denied)
        for root in dict.fromkeys((self.cx, self.cx.resolve())):
            for tool in ('Edit', 'Write'):
                self.assertIn(f'{tool}(//{root.as_posix().lstrip("/")}/AGENTS.md)', denied)

    def test_denies_are_limited_to_the_named_home(self):
        denied = self.rules(self.project('proj'), 'auto')
        cfg, cx = (home.as_posix().lstrip('/') for home in (self.cfg, self.cx))
        for tool in ('Edit', 'Write'):
            self.assertNotIn(f'{tool}(//{cx}/agents/**)', denied)
            self.assertNotIn(f'{tool}(//{cfg}/AGENTS.md)', denied)

    def test_propose_mode_has_no_trusted_file_denies_and_claude_md_is_not_named(self):
        for rule in self.rules(self.project('proj'), 'propose-only'):
            for text in ('/agents/', '/hooks/', 'AGENTS.md', '.mcp.json', '.github', '.husky'):
                self.assertNotIn(text, rule)
        for rule in self.rules(self.project('proj'), 'auto'):
            self.assertNotIn('CLAUDE.md', rule)
            self.assertNotIn('/rules', rule)


class SymlinkedConfigTests(SecurityCase):
    """S-9: config set keeps a symlinked config file a symlink."""

    def check(self, link, target, extra=()):
        write(target, '{"keep": 1}\n')
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(target)
        os.chmod(target, 0o640)
        self.script('config', 'set', *extra, 'schedule=always')
        self.assertTrue(link.is_symlink())
        self.assertEqual(os.readlink(link), str(target))
        self.assertEqual(json.loads(target.read_text()), {'keep': 1, 'schedule': 'always'})
        self.assertEqual(oct(target.stat().st_mode & 0o777), '0o640')
        self.assertEqual([path.name for path in target.parent.iterdir()], [target.name])

    def test_global_config_symlink_is_kept(self):
        self.check(self.global_path, self.root / 'dot/agent-kaizen.json')

    def test_project_config_symlink_is_kept(self):
        project = self.project('proj')
        (project / 'docs/kaizen/config.json').unlink()
        self.check(project / 'docs/kaizen/config.json', self.root / 'shared/config.json', ('--for', project))

    def test_chained_and_dangling_links(self):
        real = self.root / 'dot/real.json'
        write(real, '{}')
        middle = self.root / 'dot/middle.json'
        middle.symlink_to(real)
        self.cfg.mkdir(parents=True)
        self.global_path.symlink_to(middle)
        self.script('config', 'set', 'schedule=off')
        self.assertTrue(self.global_path.is_symlink() and middle.is_symlink())
        self.assertEqual(json.loads(real.read_text()), {'schedule': 'off'})
        self.global_path.unlink()
        dangling = self.root / 'dot2/new.json'
        dangling.parent.mkdir()
        self.global_path.symlink_to(dangling)
        self.script('config', 'set', 'schedule=off')
        self.assertTrue(self.global_path.is_symlink())
        self.assertEqual(json.loads(dangling.read_text()), {'schedule': 'off'})


class BackupRootTests(SecurityCase):
    """S-13: backup_root follows the rule scripts/kaizen-backup uses."""

    def test_default_follows_the_claude_home(self):
        self.assertEqual(self.runner.backup_root(), self.cfg / 'kaizen-backups')
        with patch.dict(os.environ):
            os.environ.pop('CLAUDE_CONFIG_DIR')
            self.assertEqual(self.runner.backup_root(), self.home / '.claude/kaizen-backups')

    def test_env_override_wins_and_empty_means_unset(self):
        with patch.dict(os.environ, {'KAIZEN_BACKUP_DIR': '~/elsewhere'}):
            self.assertEqual(self.runner.backup_root(), self.home / 'elsewhere')
        with patch.dict(os.environ, {'KAIZEN_BACKUP_DIR': ''}):
            self.assertEqual(self.runner.backup_root(), self.cfg / 'kaizen-backups')

    def test_deny_rules_use_the_new_default(self):
        root = (self.cfg / 'kaizen-backups').as_posix().lstrip('/')
        self.assertIn(f'Read(//{root}/**)', self.runner.backup_deny())


class UnsupportedPathTests(SecurityCase):
    """S-15 (a) and (b): paths the rule syntax cannot express fail closed and visibly."""

    def test_unsupported_home_is_recorded_in_state(self):
        path = self.due('proj')
        bad = self.root / 'bad,codex (old)'
        self.env['CODEX_HOME'] = str(bad)
        result = self.review('--project-dir', path)
        state = self.state(path)
        self.assertEqual(state['status'], 'unsupported-path')
        self.assertIn(str(bad), state['last_error'])
        self.assertIn("'(),'", state['last_error'])
        self.assertIn('cannot be reviewed', state['last_error'])
        self.assertIn('last_error_at', state)
        self.assertNotIn('reviewed_at', state)
        self.assertIn(f'{path}: unsupported-path: ', result.stdout)
        self.assertFalse(self.record.exists())
        # A later good run clears the message.
        self.env['CODEX_HOME'] = str(self.cx)
        self.review('--project-dir', path)
        state = self.state(path)
        self.assertEqual(state['status'], 'ok')
        self.assertNotIn('last_error', state)

    def test_unsupported_project_path_is_recorded_in_state(self):
        path = self.due('proj [old]')
        self.review('--project-dir', path)
        state = self.state(path)
        self.assertEqual(state['status'], 'unsupported-path')
        self.assertIn(str(path), state['last_error'])
        self.assertIn("'[]'", state['last_error'])

    def make_scripts(self, name):
        scripts = self.root / name
        scripts.mkdir()
        for helper in ('kaizen_credentials.py', 'kaizen-scheduled'):
            shutil.copy2(SCRIPTS / helper, scripts / helper)
        for helper in ('kaizen-backup', 'notes-ledger'):
            executable(scripts / helper, '#!/bin/sh\n')
        loader = importlib.machinery.SourceFileLoader('copied_' + name.replace(' ', '_').replace(',', '_'),
                                                      str(scripts / 'kaizen-scheduled'))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        return scripts, module

    def test_allow_rule_paths_with_breaking_characters_fail_closed(self):
        project = self.project('proj')
        for name in ('scripts,comma', 'scripts space', 'scripts(paren)', 'scripts"quote'):
            with self.subTest(name=name):
                scripts, module = self.make_scripts(name)
                options = module.command_options(type('Args', (), {'dry_run': True, 'token_audit': self.audit,
                                                                   'pricing': self.pricing})())
                with self.assertRaisesRegex(ValueError, 'cannot build allow rules: path contains') as error:
                    module.review_command(options, 'auto', 'report', 'session', project)
                self.assertIn(str(scripts / 'kaizen-backup'), str(error.exception))
                # Propose mode embeds no Bash path, so it still builds.
                module.review_command(options, 'propose-only', 'report', 'session', project)

    def test_python_path_with_breaking_characters_fails_closed(self):
        project = self.project('proj')
        for python in ('/opt/py,thon/python3', '/opt/py thon/python3'):
            with self.subTest(python=python):
                options = self.options()
                options.python = python
                with self.assertRaisesRegex(ValueError, 'cannot build allow rules: path contains'):
                    self.runner.review_command(options, 'auto', 'report', 'session', project)

    def test_allow_rule_failure_is_recorded_in_state(self):
        path = self.due('proj', '{"scheduledAutonomy":"auto"}')
        write(self.global_path, json.dumps({'autoProjects': [str(path)]}))
        python = executable(self.root / 'py,thon', f'#!/bin/sh\nexec {sys.executable} "$@"\n')
        self.review('--project-dir', path, '--python', python)
        state = self.state(path)
        self.assertEqual(state['status'], 'unsupported-path')
        self.assertIn(str(python), state['last_error'])
        self.assertIn("','", state['last_error'])
        self.assertFalse(self.record.exists())

    def test_ordinary_paths_still_build(self):
        project = self.project('proj')
        command = self.runner.review_command(self.options(), 'auto', 'report', 'session', project)
        self.assertIn('--allowedTools', command)


if __name__ == '__main__':
    unittest.main()
