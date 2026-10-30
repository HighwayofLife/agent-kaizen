"""Smoke tests for hooks/*.sh: pipe sample hook input JSON and check the decision."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1] / 'hooks'


def run_raw(hook, payload, env=None, cwd=None):
    return subprocess.run(['bash', str(HOOKS / hook)], input=json.dumps(payload), text=True,
                          capture_output=True, env={**os.environ, **(env or {})}, cwd=cwd, check=False)


def run(hook, payload, env=None, cwd=None):
    result = run_raw(hook, payload, env, cwd)
    result.check_returncode()
    return json.loads(result.stdout) if result.stdout.strip() else None


def bare_path(*tools):
    directory = tempfile.TemporaryDirectory()
    for name in ('bash', *tools):
        target = shutil.which(name)
        if target is None:
            directory.cleanup()
            raise unittest.SkipTest(f'{name} is required')
        (Path(directory.name) / name).symlink_to(target)
    return directory


def decision(output):
    return output and output['hookSpecificOutput'].get('permissionDecision')


class HookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_big_read_guard(self):
        big, small = self.tmp / 'big.py', self.tmp / 'small.py'
        big.write_text('x\n' * 500)
        small.write_text('x\n' * 10)
        self.assertEqual(decision(run('limit-big-read.sh', {'tool_input': {'file_path': str(big)}})), 'deny')
        self.assertIsNone(run('limit-big-read.sh', {'tool_input': {'file_path': str(big), 'limit': 500}}))
        self.assertIsNone(run('limit-big-read.sh', {'tool_input': {'file_path': str(small)}}))
        reason = run('limit-big-read.sh', {'tool_input': {'file_path': str(big)}})['hookSpecificOutput']
        self.assertIn('limit 500', reason['permissionDecisionReason'])  # the override is spelled out

    def test_image_guard(self):
        image = {'tool_input': {'file_path': '/x/shot.PNG'}, 'cwd': str(self.tmp)}
        cfg = self.tmp / 'cfg'
        env = {'CLAUDE_CONFIG_DIR': str(cfg), 'ALLOW_IMAGE_READS': '0', 'IMAGE_AGENTS': 'image-reader'}
        self.assertIsNone(run('block-image-read.sh', image, env))
        agents = cfg / 'agents'
        agents.mkdir(parents=True)
        (agents / 'image-reader.md').touch()
        self.assertEqual(decision(run('block-image-read.sh', image, env)), 'deny')
        self.assertIsNone(run('block-image-read.sh', {**image, 'agent_type': 'image-reader'}, env))
        self.assertIsNone(run('block-image-read.sh', image, {**env, 'ALLOW_IMAGE_READS': '1'}))
        self.assertIsNone(run('block-image-read.sh', {'tool_input': {'file_path': '/x/a.py'}}, env))
        (agents / 'image-reader.md').unlink()
        project_agents = self.tmp / '.claude/agents'
        project_agents.mkdir(parents=True)
        (project_agents / 'image-reader.md').touch()
        self.assertEqual(decision(run('block-image-read.sh', image, env)), 'deny')
        (project_agents / 'image-reader.md').unlink()
        (agents / 'viewer.md').touch()
        env['IMAGE_AGENTS'] = 'viewer image-reader'
        self.assertEqual(decision(run('block-image-read.sh', image, env)), 'deny')
        self.assertIsNone(run('block-image-read.sh', {**image, 'agent_type': 'viewer'}, env))

    def test_image_guard_optional_tools(self):
        agents = self.tmp / 'cfg/agents'
        agents.mkdir(parents=True)
        (agents / 'image-reader.md').touch()
        payload = {'tool_input': {'file_path': '/x/image.png'}, 'cwd': str(self.tmp)}
        with bare_path('jq', 'cat') as bindir:
            env = {'PATH': bindir, 'CLAUDE_CONFIG_DIR': str(self.tmp / 'cfg'),
                   'ALLOW_IMAGE_READS': '0', 'IMAGE_AGENTS': 'image-reader'}
            reason = run('block-image-read.sh', payload, env)['hookSpecificOutput']['permissionDecisionReason']
            self.assertNotIn('codex-review', reason)
            self.assertNotIn('magick', reason)
            for name in ('codex-review', 'magick'):
                stub = Path(bindir) / name
                stub.write_text('#!/bin/bash\nexit 0\n')
                stub.chmod(0o755)
            reason = run('block-image-read.sh', payload, env)['hookSpecificOutput']['permissionDecisionReason']
            self.assertIn('codex-review look', reason)
            self.assertIn('magick identify / magick compare', reason)

    def test_big_read_exemptions_and_hints(self):
        vue, md, noext = (self.tmp / name for name in ('large.vue', 'large.md', 'large'))
        for path in (vue, md, noext):
            path.write_text('x\n' * 500)
        def payload(path, **extra):
            return {'tool_input': {'file_path': str(path), **extra}}
        env = {'READ_GUARD_MAX_LINES': '400'}
        self.assertEqual(decision(run('limit-big-read.sh', payload(vue), env)), 'deny')
        self.assertIsNone(run('limit-big-read.sh', payload(md), env))
        self.assertEqual(decision(run('limit-big-read.sh', payload(noext), env)), 'deny')
        self.assertIsNone(run('limit-big-read.sh', payload(vue, limit=1), env))
        env['READ_GUARD_EXTENSIONS'] = 'vue'
        self.assertIsNone(run('limit-big-read.sh', payload(vue), env))
        self.assertEqual(decision(run('limit-big-read.sh', payload(md), env)), 'deny')
        with bare_path('jq', 'cat', 'wc', 'tr') as bindir:
            env = {'PATH': bindir, 'READ_GUARD_EXTENSIONS': 'md'}
            reason = run('limit-big-read.sh', payload(vue), env, self.tmp)['hookSpecificOutput']['permissionDecisionReason']
            self.assertIn('grep -n', reason)
            rg = Path(bindir) / 'rg'
            rg.write_text('#!/bin/bash\nexit 0\n')
            rg.chmod(0o755)
            reason = run('limit-big-read.sh', payload(vue), env, self.tmp)['hookSpecificOutput']['permissionDecisionReason']
            self.assertIn('rg -n', reason)

    def test_guards_missing_jq(self):
        with bare_path() as bindir:
            for hook in ('block-image-read', 'limit-big-read'):
                with self.subTest(hook=hook):
                    result = run_raw(hook + '.sh', {}, {'PATH': bindir, 'ALLOW_IMAGE_READS': '0'})
                    self.assertEqual(result.returncode, 0)
                    self.assertEqual(result.stdout, '')
                    self.assertEqual(result.stderr, f'jq missing: {hook} disabled\n')

    def test_subagent_context(self):
        repo = self.tmp / 'repo'
        ctx = repo / '.claude/agent-context'
        ctx.mkdir(parents=True)
        subprocess.run(['git', 'init', '-q', str(repo)], check=True)
        (ctx / 'common.md').write_text('COMMON RULES')
        (ctx / 'review.md').write_text('REVIEW RULES')
        (ctx / 'roles.conf').write_text('verifier=review\n')
        out = run('subagent-context.sh', {'agent_type': 'verifier', 'cwd': str(repo)})
        text = out['hookSpecificOutput']['additionalContext']
        self.assertIn('COMMON RULES', text)
        self.assertIn('REVIEW RULES', text)
        self.assertIsNone(run('subagent-context.sh', {'agent_type': 'Explore', 'cwd': str(repo)}))

    def test_audit_notice_once_per_day_and_scoped(self):
        audits, project = self.tmp / 'audits', self.tmp / 'project'
        audits.mkdir()
        (project / 'docs/kaizen').mkdir(parents=True)
        (audits / 'token-audit-1.md').write_text('x')
        env = {'AUDIT_DIR': str(audits), 'HOME': str(self.tmp / 'home'),
               'CLAUDE_CONFIG_DIR': str(self.tmp / 'cfg')}
        self.assertIn('token-audit-1.md', run('audit-notice.sh', {'cwd': str(project)}, env)
                      ['hookSpecificOutput']['additionalContext'])
        self.assertIsNone(run('audit-notice.sh', {'cwd': str(project)}, env))  # once per day
        self.assertIsNone(run('audit-notice.sh', {'cwd': str(self.tmp)}, env))  # not a kaizen project

    def test_audit_notice_project_and_worktree_index(self):
        cfg = (self.tmp / 'cfg').resolve()
        audits = cfg / 'audits'
        project, worktree = self.tmp / 'project', self.tmp / 'worktree'
        (project / 'docs/kaizen').mkdir(parents=True)
        (project / 'src/deep').mkdir(parents=True)
        (worktree / 'src/deep').mkdir(parents=True)
        reports = audits / 'projects/key'
        reports.mkdir(parents=True)
        (reports.parent / 'index.json').write_text(json.dumps({'v': 1, 'projects': {
            str(project.resolve()): 'key', str(worktree.resolve()): 'key'}}))
        report = reports / 'token-audit-project.md'
        report.write_text('project')
        global_report = audits / 'token-audit-global.md'
        global_report.write_text('global')
        proposal = reports / 'cycle-2026-01-01.md'
        proposal.write_text('proposal')
        os.utime(proposal, (300, 300))
        os.utime(report, (100, 100))
        os.utime(global_report, (200, 200))
        env = {'HOME': str(self.tmp / 'home'), 'CLAUDE_CONFIG_DIR': str(cfg), 'AUDIT_DIR': ''}
        for path in (project, project / 'src/deep', worktree, worktree / 'src/deep'):
            with self.subTest(path=path):
                out = run('audit-notice.sh', {'cwd': str(path)}, env)
                self.assertIn(str(report.resolve()), out['hookSpecificOutput']['additionalContext'])
                self.assertIn(str(proposal.resolve()), out['hookSpecificOutput']['additionalContext'])
                for marker in reports.glob('*.noticed-*'):
                    marker.unlink()

    def test_audit_notice_global_scope(self):
        cfg, project = (self.tmp / 'cfg').resolve(), self.tmp / 'project'
        audits = cfg / 'audits'
        audits.mkdir(parents=True)
        (project / 'docs/kaizen').mkdir(parents=True)
        filtered = audits / 'token-audit-filtered.md'
        unfiltered = audits / 'token-audit-global.md'
        filtered.write_text('<!-- token-audit-scope {"project":"x","cwd":null,"project_dirs":[]} -->\n')
        unfiltered.write_text('<!-- token-audit-scope {"project":null,"cwd":null,"project_dirs":[]} -->\n')
        proposal = audits / 'cycle-2026-01-01.md'
        proposal.write_text('proposal')
        os.utime(proposal, (300, 300))
        os.utime(filtered, (200, 200))
        os.utime(unfiltered, (100, 100))
        env = {'HOME': str(self.tmp / 'home'), 'CLAUDE_CONFIG_DIR': str(cfg), 'AUDIT_DIR': ''}
        out = run('audit-notice.sh', {'cwd': str(project)}, env)
        self.assertIn(str(unfiltered.resolve()), out['hookSpecificOutput']['additionalContext'])
        self.assertNotIn(str(proposal.resolve()), out['hookSpecificOutput']['additionalContext'])
        unfiltered.unlink()
        for marker in audits.glob('*.noticed-*'):
            marker.unlink()
        self.assertIsNone(run('audit-notice.sh', {'cwd': str(project)}, env))
        self.assertEqual(list(audits.glob('*.noticed-*')), [])

    def test_audit_notice_switches(self):
        cfg, project = (self.tmp / 'cfg').resolve(), self.tmp / 'project'
        audits = cfg / 'audits'
        audits.mkdir(parents=True)
        config = project / 'docs/kaizen/config.json'
        config.parent.mkdir(parents=True)
        deep = project / 'src/deep'
        deep.mkdir(parents=True)
        (audits / 'token-audit-1.md').write_text('x')
        global_config = cfg / 'agent-kaizen.json'
        env = {'HOME': str(self.tmp / 'home'), 'CLAUDE_CONFIG_DIR': str(cfg), 'AUDIT_DIR': ''}
        global_config.write_text('{"enabled": false}')
        self.assertIsNone(run('audit-notice.sh', {'cwd': str(project)}, env))
        global_config.write_text('{"enabled": true}')
        config.write_text('{"schedule": "off"}')
        for path in (project, deep):
            self.assertIsNone(run('audit-notice.sh', {'cwd': str(path)}, env))
        global_config.write_text('{"enabled": true, "schedule": "off"}')
        config.write_text('{"schedule": "active"}')
        self.assertIsNotNone(run('audit-notice.sh', {'cwd': str(deep)}, env))
        for marker in audits.glob('*.noticed-*'):
            marker.unlink()
        global_config.unlink()
        self.assertIsNotNone(run('audit-notice.sh', {'cwd': str(project)}, env))

    def test_audit_notice_missing_or_failing_jq(self):
        cfg, project, bindir = (self.tmp / 'cfg').resolve(), self.tmp / 'project', self.tmp / 'bin'
        audits = cfg / 'audits'
        audits.mkdir(parents=True)
        (project / 'docs/kaizen').mkdir(parents=True)
        (audits / 'token-audit-1.md').write_text('x')
        bindir.mkdir()
        bash, jq = shutil.which('bash'), shutil.which('jq')
        self.assertIsNotNone(bash)
        self.assertIsNotNone(jq)
        for name in ('ls', 'head', 'date', 'touch', 'grep'):
            (bindir / name).symlink_to(shutil.which(name))
        env = {**os.environ, 'HOME': str(self.tmp / 'home'), 'CLAUDE_CONFIG_DIR': str(cfg),
               'AUDIT_DIR': '', 'PATH': str(bindir)}
        def invoke():
            return subprocess.run([bash, str(HOOKS / 'audit-notice.sh')],
                                  input=json.dumps({'cwd': str(project)}), text=True,
                                  capture_output=True, env=env, check=True)
        self.assertEqual(invoke().stdout, '')
        self.assertEqual(list(audits.glob('*.noticed-*')), [])
        stub = bindir / 'jq'
        stub.write_text('#!/bin/bash\n[ "$1" = -n ] && exit 1\nexec "' + jq + '" "$@"\n')
        stub.chmod(0o755)
        self.assertEqual(invoke().stdout, '')
        self.assertEqual(list(audits.glob('*.noticed-*')), [])

    def test_after_compact(self):
        repo = self.tmp / 'r'
        subprocess.run(['git', 'init', '-q', str(repo)], check=True)
        out = run('after-compact.sh', {'cwd': str(repo)})
        self.assertIn('Recover state from disk', out['hookSpecificOutput']['additionalContext'])


if __name__ == '__main__':
    unittest.main()
