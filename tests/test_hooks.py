"""Smoke tests for hooks/*.sh: pipe sample hook input JSON and check the decision."""
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / 'hooks'


def run_raw(hook, payload, env=None, cwd=None, text=True):
    inherited = {k: v for k, v in os.environ.items()
                 if k not in ('KAIZEN_HOST', 'PLUGIN_ROOT', 'COPILOT_PLUGIN_ROOT')}
    data = json.dumps(payload)
    return subprocess.run(['bash', str(HOOKS / hook)], input=data if text else data.encode(), text=text,
                          capture_output=True, env={**inherited, **(env or {})}, cwd=cwd, check=False)


def run(hook, payload, env=None, cwd=None):
    result = run_raw(hook, payload, env, cwd)
    result.check_returncode()
    return (json.loads(result.stdout) or None) if result.stdout.strip() else None


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
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def notice_setup(self):
        project, audits, plugin = (self.tmp / name for name in ('project', 'audits', 'plugin'))
        (project / 'docs/kaizen').mkdir(parents=True)
        audits.mkdir()
        (plugin / 'scripts').mkdir(parents=True)
        env = {'AUDIT_DIR': str(audits), 'HOME': str(self.tmp / 'home'),
               'CLAUDE_CONFIG_DIR': str(self.tmp / 'cfg'), 'CLAUDE_PLUGIN_ROOT': str(plugin)}
        return project, audits, plugin, env

    def test_claude_notice_golden(self):
        # Captured from d1accc4 scripts, not JSON reserialization; <TMP> replaces the temp root.
        project, audits, plugin, env = self.notice_setup()
        (audits / 'token-audit-1.md').write_text('audit')
        expected = ('{\n  "hookSpecificOutput": {\n    "hookEventName": "SessionStart",\n'
                    '    "additionalContext": "An unreviewed usage audit exists: <TMP>/audits/token-audit-1.md. '
                    'When there is a pause, run /agent-kaizen:review (read the headline and flagged sections, '
                    'not the whole file), propose changes to the user, then touch <TMP>/audits/token-audit-1.reviewed."\n  }\n}\n')
        result = run_raw('audit-notice.sh', {'cwd': str(project)}, env, text=False)
        self.assertEqual(result.stdout, expected.replace('<TMP>', str(self.tmp)).encode())
        for path in audits.iterdir():
            path.unlink()
        (plugin / 'scripts/experiment-check').write_text('print("synthetic finding")\nraise SystemExit(1)\n')
        expected = ('{\n  "hookSpecificOutput": {\n    "hookEventName": "SessionStart",\n'
                    '    "additionalContext": "Experiments need attention in this project (docs/kaizen/LEDGER.md):'
                    '\\nsynthetic finding\\nWhen there is a pause, run /agent-kaizen:review."\n  }\n}\n')
        self.assertEqual(run_raw('audit-notice.sh', {'cwd': str(project)}, env, text=False).stdout, expected.encode())
        self.assertEqual(run_raw('audit-notice.sh', {'cwd': str(self.tmp)}, env, text=False).stdout, b'{}\n')

    def test_claude_burst_golden(self):
        for event in ('PostToolUse', 'PostToolUseFailure'):
            payload = {'session_id': event, 'hook_event_name': event, 'tool_name': 'Bash'}
            expected = ('{\n  "hookSpecificOutput": {\n    "hookEventName": "' + event + '",\n'
                        '    "additionalContext": "1 Bash calls this turn. Chain the remaining steps into one command '
                        'or script that prints a summary, or hand the investigation to a cheaper read-only subagent."\n  }\n}\n')
            self.assertEqual(run_raw('bash-burst.sh', payload, self.burst_env(KAIZEN_BASH_BURST='1'), text=False)
                             .stdout, expected.encode())

    def test_host_notice_detection_and_override(self):
        project, audits, plugin, env = self.notice_setup()
        (audits / 'token-audit-1.md').write_text('audit')
        cases = [({'PLUGIN_ROOT': str(plugin)}, 'codex'),
                 ({'PLUGIN_ROOT': str(plugin), 'COPILOT_PLUGIN_ROOT': str(plugin)}, 'copilot'),
                 ({'COPILOT_PLUGIN_ROOT': str(plugin), 'KAIZEN_HOST': 'codex'}, 'codex'),
                 ({'PLUGIN_ROOT': str(plugin), 'KAIZEN_HOST': 'claude'}, 'claude'),
                 ({'PLUGIN_ROOT': str(plugin), 'KAIZEN_HOST': 'unknown'}, 'codex'),
                 ({'COPILOT_PLUGIN_ROOT': str(plugin), 'KAIZEN_HOST': 'unknown'}, 'copilot')]
        for extra, host in cases:
            with self.subTest(extra=extra):
                for marker in audits.glob('*.noticed-*'):
                    marker.unlink()
                fixture_host = 'copilot' if host == 'copilot' else 'codex'
                payload = json.loads((ROOT / f'tests/fixtures/hooks/{fixture_host}_sessionstart.json').read_text())
                payload['cwd'] = str(project)
                out = run('audit-notice.sh', payload, {**env, **extra})
                if host == 'copilot':
                    self.assertEqual(set(out), {'additionalContext'})
                    text = out['additionalContext']
                else:
                    self.assertEqual(set(out), {'hookSpecificOutput'})
                    text = out['hookSpecificOutput']['additionalContext']
                skill = '$agent-kaizen:review' if host == 'codex' else '/agent-kaizen:review'
                self.assertIn(skill, text)
                self.assertNotIn('/agent-kaizen:review' if host == 'codex' else '$agent-kaizen:review', text)

    def test_host_burst_tools_and_reset(self):
        for host in ('claude', 'codex', 'copilot'):
            extra = {} if host == 'claude' else {'PLUGIN_ROOT': str(ROOT)}
            if host == 'copilot':
                extra['COPILOT_PLUGIN_ROOT'] = str(ROOT)
            env = self.burst_env(**extra)
            fixture_host = 'codex' if host == 'claude' else host
            payload = json.loads((ROOT / f'tests/fixtures/hooks/{fixture_host}_posttooluse_bash.json').read_text())
            reset = json.loads((ROOT / f'tests/fixtures/hooks/{fixture_host}_userpromptsubmit.json').read_text())
            for index, tool in enumerate(('Bash', 'bash')):
                with self.subTest(host=host, tool=tool):
                    payload.update(session_id=f'{host}-{index}', tool_name=tool)
                    reset['session_id'] = payload['session_id']
                    self.assertIsNone(run('bash-burst.sh', payload, env))
                    out = run('bash-burst.sh', payload, env)
                    if tool == 'bash' and host != 'copilot':
                        self.assertIsNone(out)
                    else:
                        key = 'additionalContext' if host == 'copilot' else 'hookSpecificOutput'
                        self.assertEqual(set(out), {key})
                    self.assertEqual(run_raw('bash-burst.sh', reset, env).stdout, '')
                    self.assertIsNone(run('bash-burst.sh', payload, env))

    def test_host_helpers_identical(self):
        helpers = []
        for name in ('audit-notice.sh', 'session-audit.sh', 'bash-burst.sh'):
            text = (HOOKS / name).read_text()
            start, end = '# --- host helper ---', '# --- end host helper ---'
            self.assertEqual(text.count(start), 1)
            self.assertEqual(text.count(end), 1)
            helpers.append(text.split(start)[1].split(end)[0])
        self.assertTrue(helpers[0].strip())
        self.assertEqual(helpers, [helpers[0]] * 3)

    def test_bash_burst_counts_and_resets(self):
        env = {'TMPDIR': str(self.tmp), 'KAIZEN_BASH_BURST': '2'}
        payload = {'session_id': '../session', 'hook_event_name': 'PostToolUse',
                   'tool_name': 'Bash'}
        hook = 'bash-burst.sh'
        self.assertIsNone(run(hook, {**payload, 'tool_name': 'Read'}, env))
        self.assertIsNone(run(hook, {**payload, 'agent_id': 'a1', 'agent_type': 'scout'}, env))
        self.assertIsNone(run(hook, payload, env))
        output = run(hook, payload, env)['hookSpecificOutput']
        self.assertEqual(output['hookEventName'], 'PostToolUse')
        self.assertIn('2 Bash calls this turn', output['additionalContext'])
        self.assertNotIn('haiku', output['additionalContext'])
        self.assertIsNone(run(hook, payload, env))
        self.assertIn('4 Bash calls this turn', run(hook, payload, env)
                      ['hookSpecificOutput']['additionalContext'])
        self.assertIsNone(run(hook, {**payload, 'hook_event_name': 'UserPromptSubmit'}, env))
        self.assertIsNone(run(hook, payload, env))
        self.assertIn('2 Bash calls this turn', run(hook, payload, env)
                      ['hookSpecificOutput']['additionalContext'])

    def test_bash_burst_bad_json_and_default_threshold(self):
        env = {**os.environ, **self.burst_env(KAIZEN_BASH_BURST='invalid')}
        for key in ('KAIZEN_HOST', 'PLUGIN_ROOT', 'COPILOT_PLUGIN_ROOT'):
            env.pop(key, None)
        result = subprocess.run(['bash', str(HOOKS / 'bash-burst.sh')], input='{',
                                text=True, capture_output=True, env=env, check=False)
        self.assertEqual((result.returncode, result.stdout), (0, ''))
        payload = {'session_id': 'default', 'hook_event_name': 'PostToolUse', 'tool_name': 'Bash'}
        for _ in range(7):
            self.assertIsNone(run('bash-burst.sh', payload, env))
        self.assertIn('8 Bash calls this turn', run('bash-burst.sh', payload, env)
                      ['hookSpecificOutput']['additionalContext'])

    def burst_env(self, **extra):
        return {'TMPDIR': str(self.tmp), 'HOME': str(self.tmp / 'home'),
                'CLAUDE_CONFIG_DIR': str(self.tmp / 'cfg'), 'KAIZEN_BASH_BURST': '2', **extra}

    def test_bash_burst_counts_failed_bash_and_skips_interrupts(self):
        env = self.burst_env()
        payload = {'session_id': 's', 'hook_event_name': 'PostToolUseFailure', 'tool_name': 'Bash'}
        self.assertIsNone(run('bash-burst.sh', {**payload, 'is_interrupt': True}, env))
        self.assertIsNone(run('bash-burst.sh', payload, env))
        output = run('bash-burst.sh', {**payload, 'hook_event_name': 'PostToolUse'}, env)['hookSpecificOutput']
        self.assertEqual(output['hookEventName'], 'PostToolUse')
        self.assertIsNone(run('bash-burst.sh', payload, env))
        output = run('bash-burst.sh', payload, env)['hookSpecificOutput']
        self.assertEqual(output['hookEventName'], 'PostToolUseFailure')
        self.assertIn('4 Bash calls this turn', output['additionalContext'])

    def test_bash_burst_main_session_is_decided_by_agent_id(self):
        env = self.burst_env()
        payload = {'session_id': 's', 'hook_event_name': 'PostToolUse', 'tool_name': 'Bash'}
        self.assertIsNone(run('bash-burst.sh', {**payload, 'agent_id': 'a1'}, env))
        self.assertIsNone(run('bash-burst.sh', {**payload, 'agent_id': 'a1'}, env))
        self.assertIsNone(run('bash-burst.sh', {**payload, 'agent_type': 'my-agent'}, env))
        self.assertIn('2 Bash calls this turn', run('bash-burst.sh', {**payload, 'agent_type': 'my-agent'}, env)
                      ['hookSpecificOutput']['additionalContext'])

    def test_bash_burst_silent_without_jq_or_session_id(self):
        payload = {'hook_event_name': 'PostToolUse', 'tool_name': 'Bash'}
        for session in ({}, {'session_id': ''}, {'session_id': 5}):
            result = run_raw('bash-burst.sh', {**payload, **session}, self.burst_env())
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))
        with bare_path() as bindir:
            result = run_raw('bash-burst.sh', {**payload, 'session_id': 's'}, self.burst_env(PATH=bindir))
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))
        self.assertEqual(list(self.tmp.glob('kaizen-bash-burst-*')), [])

    def test_bash_burst_parallel_calls_are_all_counted(self):
        env = self.burst_env(KAIZEN_BASH_BURST='1000')
        payload = {'session_id': 'par', 'hook_event_name': 'PostToolUse', 'tool_name': 'Bash'}
        with ThreadPoolExecutor(16) as pool:
            results = list(pool.map(lambda _: run_raw('bash-burst.sh', payload, env), range(16)))
        self.assertEqual([r.returncode for r in results], [0] * 16)
        state = next(self.tmp.glob('kaizen-bash-burst-*')) / 'par'
        self.assertEqual(state.stat().st_size, 16)

    def test_bash_burst_off_switch_and_bad_threshold(self):
        payload = {'session_id': 's', 'hook_event_name': 'PostToolUse', 'tool_name': 'Bash'}
        env = self.burst_env(KAIZEN_BASH_BURST='0')
        for _ in range(10):
            self.assertIsNone(run('bash-burst.sh', payload, env))
        self.assertEqual(list(self.tmp.glob('kaizen-bash-burst-*')), [])
        env = self.burst_env(KAIZEN_BASH_BURST='often')
        for _ in range(7):
            self.assertIsNone(run('bash-burst.sh', payload, env))
        self.assertIn('8 Bash calls this turn', run('bash-burst.sh', payload, env)
                      ['hookSpecificOutput']['additionalContext'])

    def test_bash_burst_honours_enabled_false(self):
        cfg = self.tmp / 'cfg'
        cfg.mkdir()
        payload = {'session_id': 's', 'hook_event_name': 'PostToolUse', 'tool_name': 'Bash'}
        env = self.burst_env(KAIZEN_BASH_BURST='1')
        (cfg / 'agent-kaizen.json').write_text('{"enabled": false}')
        self.assertIsNone(run('bash-burst.sh', payload, env))
        (cfg / 'agent-kaizen.json').write_text('{"note": {"enabled": false}, "enabled": true}')
        self.assertIsNotNone(run('bash-burst.sh', payload, env))
        (cfg / 'agent-kaizen.json').write_text('not json')
        self.assertIsNotNone(run('bash-burst.sh', payload, env))

    def test_bash_burst_state_dir_must_be_private_and_owned(self):
        payload = {'session_id': 's', 'hook_event_name': 'PostToolUse', 'tool_name': 'Bash'}
        env = self.burst_env(KAIZEN_BASH_BURST='1')
        self.assertIsNotNone(run('bash-burst.sh', payload, env))
        state = self.tmp / f'kaizen-bash-burst-{os.getuid()}'
        self.assertEqual(state.stat().st_mode & 0o777, 0o700)
        state.rename(self.tmp / 'real')
        state.symlink_to(self.tmp / 'real')
        result = run_raw('bash-burst.sh', payload, env)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))
        self.assertEqual((self.tmp / 'real' / 's').stat().st_size, 1)
        state.unlink()
        state.write_text('a file')
        result = run_raw('bash-burst.sh', payload, env)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))

    def test_hook_scripts_named_in_configs_exist(self):
        config = json.loads((HOOKS / 'hooks.json').read_text())
        template = json.loads((ROOT / 'templates/settings.example.json').read_text())
        for source in (config, template):
            commands = [hook['command'] for entries in source['hooks'].values()
                        for entry in entries for hook in entry['hooks']]
            self.assertTrue(commands)
            for command in commands:
                names = re.findall(r'hooks/([\w.-]+\.sh)', command)
                self.assertEqual(len(names), 1, command)
                self.assertTrue((HOOKS / names[0]).is_file(), command)

    def test_template_hooks_use_config_dir_and_timeouts(self):
        template = json.loads((ROOT / 'templates/settings.example.json').read_text())
        for entries in template['hooks'].values():
            for entry in entries:
                for hook in entry['hooks']:
                    self.assertIn('"${CLAUDE_CONFIG_DIR:-$HOME/.claude}/hooks/', hook['command'])
                    self.assertIsInstance(hook.get('timeout'), int, hook['command'])

    def test_agent_context_roles_have_files(self):
        context = ROOT / 'templates/agent-context'
        roles = [line.split('=', 1)[1].strip() for line in (context / 'roles.conf').read_text().splitlines()
                 if '=' in line and not line.startswith('#')]
        self.assertTrue(roles)
        for role in roles:
            self.assertTrue((context / f'{role}.md').is_file(), role)
        for agent in ('judge', 'swarm-lead', 'image-reader'):
            line = next(l for l in (context / 'roles.conf').read_text().splitlines() if l.startswith(agent + '='))
            self.assertNotEqual(line, agent + '=review')
        verdict = (context / 'verdict.md').read_text()
        self.assertNotIn('PASS', verdict)
        self.assertNotIn('Rank findings', verdict)

    def test_big_read_guard(self):
        big, small = self.tmp / 'big.py', self.tmp / 'small.py'
        big.write_text('x\n' * 500)
        small.write_text('x\n' * 10)
        self.assertEqual(decision(run('limit-big-read.sh', {'tool_input': {'file_path': str(big)}})), 'deny')
        self.assertIsNone(run('limit-big-read.sh', {'tool_input': {'file_path': str(big), 'limit': 500}}))
        self.assertIsNone(run('limit-big-read.sh', {'tool_input': {'file_path': str(small)}}))
        reason = run('limit-big-read.sh', {'tool_input': {'file_path': str(big)}})['hookSpecificOutput']
        self.assertIn('limit 500', reason['permissionDecisionReason'])  # the override is spelled out

    def test_big_read_hint_quotes_the_path(self):
        odd = self.tmp / "a dir" / "it's big.py"
        odd.parent.mkdir()
        odd.write_text('x\n' * 500)
        reason = run('limit-big-read.sh', {'tool_input': {'file_path': str(odd)}},
                     cwd=self.tmp)['hookSpecificOutput']['permissionDecisionReason']
        hint = re.search(r'`(?:rg|grep) -n PATTERN (.*?)`, then', reason).group(1)
        quoted = subprocess.run(['bash', '-c', 'printf "%s" ' + hint], capture_output=True, text=True).stdout
        self.assertEqual(quoted, str(odd))

    def test_big_read_offset_without_limit(self):
        big = self.tmp / 'big.py'
        big.write_text('x\n' * 500)
        env = {'READ_GUARD_MAX_LINES': '400'}
        def payload(**extra):
            return {'tool_input': {'file_path': str(big), **extra}}
        self.assertEqual(decision(run('limit-big-read.sh', payload(offset=50), env)), 'deny')
        self.assertEqual(decision(run('limit-big-read.sh', payload(offset=100), env)), 'deny')
        self.assertIsNone(run('limit-big-read.sh', payload(offset=101), env))
        self.assertIsNone(run('limit-big-read.sh', payload(offset=495), env))
        self.assertEqual(decision(run('limit-big-read.sh', payload(offset='x'), env)), 'deny')

    def test_image_guard_follows_symlinks(self):
        agents = self.tmp / 'cfg/agents'
        agents.mkdir(parents=True)
        (agents / 'image-reader.md').touch()
        env = {'CLAUDE_CONFIG_DIR': str(self.tmp / 'cfg'), 'ALLOW_IMAGE_READS': '0', 'IMAGE_AGENTS': 'image-reader'}
        shot = self.tmp / 'shot.PNG'
        shot.write_bytes(b'x')
        link = self.tmp / 'link'
        link.symlink_to(shot)
        chain = self.tmp / 'chain'
        chain.symlink_to(link)
        text = self.tmp / 'notes.txt'
        text.write_text('x')
        text_link = self.tmp / 'text-link'
        text_link.symlink_to(text)
        for path in (link, chain):
            payload = {'tool_input': {'file_path': str(path)}, 'cwd': str(self.tmp)}
            self.assertEqual(decision(run('block-image-read.sh', payload, env)), 'deny', path)
        payload = {'tool_input': {'file_path': str(text_link)}, 'cwd': str(self.tmp)}
        self.assertIsNone(run('block-image-read.sh', payload, env))

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

    def test_after_compact_missing_jq_is_silent(self):
        repo = self.tmp / 'r'
        subprocess.run(['git', 'init', '-q', str(repo)], check=True)
        with bare_path('git') as bindir:
            result = run_raw('after-compact.sh', {'cwd': str(repo)}, {'PATH': bindir})
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))

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

    def test_experiment_notice_and_audit(self):
        project = self.tmp / 'project'
        ledger = project / 'docs/kaizen/LEDGER.md'
        ledger.parent.mkdir(parents=True)
        ledger.write_text('| date | change | measured effect | keep/revert | review date |\n'
                          '| --- | --- | --- | --- | --- |\n'
                          '| 2020-01-01 | test | pending | | 2020-01-02 |\n')
        audits = self.tmp / 'audits'
        env = {'AUDIT_DIR': str(audits), 'CLAUDE_CONFIG_DIR': str(self.tmp / 'cfg'),
               'CLAUDE_PLUGIN_ROOT': str(ROOT)}
        payload = {'cwd': str(project)}
        text = run('audit-notice.sh', payload, env)['hookSpecificOutput']['additionalContext']
        self.assertIn('Experiments need attention', text)
        self.assertIsNone(run('audit-notice.sh', payload, env))
        for marker in audits.glob('experiments-*.noticed-*'):
            marker.unlink()
        (audits / 'token-audit-1.md').write_text('audit')
        text = run('audit-notice.sh', payload, env)['hookSpecificOutput']['additionalContext']
        self.assertIn('Experiments need attention', text)
        self.assertIn('unreviewed usage audit', text)
        self.assertIsNone(run('audit-notice.sh', payload, env))
        ledger.write_text('')
        for marker in audits.glob('*.noticed-*'):
            marker.unlink()
        text = run('audit-notice.sh', payload, env)['hookSpecificOutput']['additionalContext']
        self.assertNotIn('Experiments need attention', text)

    def test_experiment_failures_preserve_audit(self):
        project = self.tmp / 'project'
        ledger = project / 'docs/kaizen/LEDGER.md'
        ledger.parent.mkdir(parents=True)
        ledger.mkdir()  # Unreadable as a ledger, even when running as root.
        audits = self.tmp / 'audits'
        audits.mkdir()
        (audits / 'token-audit-1.md').write_text('audit')
        plugin = self.tmp / 'plugin'
        (plugin / 'scripts').mkdir(parents=True)
        checker = plugin / 'scripts/experiment-check'
        env = {'AUDIT_DIR': str(audits), 'CLAUDE_CONFIG_DIR': str(self.tmp / 'cfg'),
               'CLAUDE_PLUGIN_ROOT': str(ROOT), 'KAIZEN_NOTICE_TIMEOUT': '1'}
        payload = {'cwd': str(project)}
        for case in ('ledger', 'missing', 'no_python', 'hung'):
            with self.subTest(case=case):
                for marker in audits.glob('*.noticed-*'):
                    marker.unlink()
                env['CLAUDE_PLUGIN_ROOT'] = str(ROOT if case in ('ledger', 'no_python') else plugin)
                if case == 'hung':
                    checker.write_text('import time\ntime.sleep(20)\n')
                path = None
                if case == 'no_python':
                    path = bare_path('jq', 'ls', 'head', 'grep', 'date', 'dirname', 'touch')
                    env['PATH'] = path.name
                start = time.monotonic()
                try:
                    text = run('audit-notice.sh', payload, env)['hookSpecificOutput']['additionalContext']
                finally:
                    if path:
                        path.cleanup()
                        env.pop('PATH')
                self.assertLess(time.monotonic() - start, 5)
                self.assertIn('unreviewed usage audit', text)
                self.assertNotIn('Experiments need attention', text)

    def test_notice_term_resistant_checker_and_atomic_marker(self):
        project, audits, plugin = self.tmp / 'project', self.tmp / 'audits', self.tmp / 'plugin'
        (project / 'docs/kaizen').mkdir(parents=True)
        (plugin / 'scripts').mkdir(parents=True)
        checker = plugin / 'scripts/experiment-check'
        checker.write_text('import signal, time\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\ntime.sleep(20)\n')
        audits.mkdir()
        (audits / 'token-audit-1.md').write_text('audit')
        env = {'AUDIT_DIR': str(audits), 'CLAUDE_CONFIG_DIR': str(self.tmp / 'cfg'),
               'CLAUDE_PLUGIN_ROOT': str(plugin), 'KAIZEN_NOTICE_TIMEOUT': '1'}
        start = time.monotonic()
        result = run_raw('audit-notice.sh', {'cwd': str(project)}, env)
        self.assertEqual(result.returncode, 0)
        self.assertIn('unreviewed usage audit', json.loads(result.stdout)['hookSpecificOutput']['additionalContext'])
        self.assertLess(time.monotonic() - start, 5)
        for marker in audits.glob('*.noticed-*'):
            marker.unlink()
        with bare_path('jq', 'ls', 'head', 'grep', 'date', 'dirname', 'touch', 'python3', 'cksum', 'mktemp', 'sleep', 'rm', 'mkdir') as binpath:
            start = time.monotonic()
            result = run_raw('audit-notice.sh', {'cwd': str(project)}, {**env, 'PATH': binpath})
            self.assertEqual(result.returncode, 0)
            self.assertIn('unreviewed usage audit', json.loads(result.stdout)['hookSpecificOutput']['additionalContext'])
            self.assertLess(time.monotonic() - start, 5)
        for marker in audits.glob('*.noticed-*'):
            marker.unlink()
        checker.write_text('import time\ntime.sleep(0.2)\nprint("finding")\nraise SystemExit(1)\n')
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: run_raw('audit-notice.sh', {'cwd': str(project)}, env), range(2)))
        messages = [json.loads(result.stdout).get('hookSpecificOutput', {}).get('additionalContext', '') for result in results]
        self.assertEqual(sum('unreviewed usage audit' in m for m in messages), 1)
        self.assertEqual(sum('Experiments need attention' in m for m in messages), 1)

    def test_due_checks_index_and_worktree(self):
        cfg, project, worktree = (self.tmp / 'cfg').resolve(), (self.tmp / 'project').resolve(), (self.tmp / 'worktree').resolve()
        (project / 'docs/kaizen').mkdir(parents=True)
        subprocess.run(['git', 'init', '-q', str(project)], check=True)
        subprocess.run(['git', '-C', str(project), '-c', 'user.name=Test', '-c', 'user.email=test@localhost', '-c', 'commit.gpgsign=false', 'commit', '--allow-empty', '-qm', 'initial'], check=True)
        subprocess.run(['git', '-C', str(project), 'worktree', 'add', '-q', '-b', 'test-worktree', str(worktree)], check=True)
        (worktree / 'src').mkdir()
        audits = cfg / 'audits'
        env = {'CLAUDE_CONFIG_DIR': str(cfg), 'CLAUDE_PLUGIN_ROOT': str(ROOT)}
        state = Path(subprocess.check_output(['python3', str(ROOT / 'scripts/kaizen-scheduled'), 'checks', 'path', '--for', str(project)], env={**os.environ, **env}, text=True).strip())
        state.parent.mkdir(parents=True)
        (audits / 'projects/index.json').write_text(json.dumps({'projects': {str(project): state.parent.name, str(worktree): state.parent.name}}))
        for path in (project, worktree / 'src'):
            text = run('audit-notice.sh', {'cwd': str(path)}, env)['hookSpecificOutput']['additionalContext']
            self.assertIn('models: never run', text)
            for marker in audits.glob('experiments-*.noticed-*'):
                marker.unlink()
        for name in ('models', 'roster', 'whats-new'):
            result = subprocess.run(['python3', str(ROOT / 'scripts/kaizen-scheduled'), 'checks', 'record', '--for', str(project), name], env={**os.environ, **env}, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(state.exists())
        for marker in audits.glob('*.noticed-*'):
            marker.unlink()
        self.assertIsNone(run('audit-notice.sh', {'cwd': str(project)}, env))
        self.assertIsNone(run('audit-notice.sh', {'cwd': str(worktree / 'src')}, env))
        (audits / 'projects/index.json').unlink()
        self.assertIsNone(run('audit-notice.sh', {'cwd': str(project)}, env))

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
        for name in ('ls', 'head', 'date', 'touch', 'grep', 'rm'):
            (bindir / name).symlink_to(shutil.which(name))
        env = {**os.environ, 'HOME': str(self.tmp / 'home'), 'CLAUDE_CONFIG_DIR': str(cfg),
               'AUDIT_DIR': '', 'PATH': str(bindir)}
        for key in ('KAIZEN_HOST', 'PLUGIN_ROOT', 'COPILOT_PLUGIN_ROOT'):
            env.pop(key, None)
        def invoke():
            return subprocess.run([bash, str(HOOKS / 'audit-notice.sh')],
                                  input=json.dumps({'cwd': str(project)}), text=True,
                                  capture_output=True, env=env, check=True)
        self.assertEqual(json.loads(invoke().stdout), {})
        self.assertEqual(list(audits.glob('*.noticed-*')), [])
        stub = bindir / 'jq'
        stub.write_text('#!/bin/bash\n[ "$1" = -n ] && exit 1\nexec "' + jq + '" "$@"\n')
        stub.chmod(0o755)
        self.assertEqual(json.loads(invoke().stdout), {})
        self.assertEqual(list(audits.glob('*.noticed-*')), [])

    def test_after_compact(self):
        repo = self.tmp / 'r'
        subprocess.run(['git', 'init', '-q', str(repo)], check=True)
        out = run('after-compact.sh', {'cwd': str(repo)})
        self.assertIn('Recover state from disk', out['hookSpecificOutput']['additionalContext'])


if __name__ == '__main__':
    unittest.main()
