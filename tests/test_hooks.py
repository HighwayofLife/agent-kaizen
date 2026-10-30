"""Smoke tests for hooks/*.sh: pipe sample hook input JSON and check the decision."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1] / 'hooks'


def run(hook, payload, env=None, cwd=None):
    result = subprocess.run(['bash', str(HOOKS / hook)], input=json.dumps(payload), text=True,
                            capture_output=True, env={**os.environ, **(env or {})}, cwd=cwd, check=True)
    return json.loads(result.stdout) if result.stdout.strip() else None


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
        image = {'tool_input': {'file_path': '/x/shot.PNG'}}
        self.assertEqual(decision(run('block-image-read.sh', image)), 'deny')
        self.assertIsNone(run('block-image-read.sh', {**image, 'agent_type': 'image-reader'}))
        self.assertIsNone(run('block-image-read.sh', image, env={'ALLOW_IMAGE_READS': '1'}))
        self.assertIsNone(run('block-image-read.sh', {'tool_input': {'file_path': '/x/a.py'}}))

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
        env = {'AUDIT_DIR': str(audits)}
        self.assertIn('token-audit-1.md', run('audit-notice.sh', {'cwd': str(project)}, env)
                      ['hookSpecificOutput']['additionalContext'])
        self.assertIsNone(run('audit-notice.sh', {'cwd': str(project)}, env))  # once per day
        self.assertIsNone(run('audit-notice.sh', {'cwd': str(self.tmp)}, env))  # not a kaizen project

    def test_after_compact(self):
        repo = self.tmp / 'r'
        subprocess.run(['git', 'init', '-q', str(repo)], check=True)
        out = run('after-compact.sh', {'cwd': str(repo)})
        self.assertIn('Recover state from disk', out['hookSpecificOutput']['additionalContext'])


if __name__ == '__main__':
    unittest.main()
