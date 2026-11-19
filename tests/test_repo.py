"""Repository consistency checks: manifests, skills, references, README table, privacy."""
import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = sorted(p.parent.name for p in (ROOT / 'skills').glob('*/SKILL.md'))
PREAMBLE = ('**Plugin root:** `${CLAUDE_PLUGIN_ROOT}`. If that is still a `${...}` placeholder, use the folder '
            'that contains `skills/` (this file is `skills/<name>/SKILL.md`), and substitute that path, in '
            'quotes, wherever this skill uses `CLAUDE_PLUGIN_ROOT`.\n'
            '**Not in Claude Code?** Read `docs/hosts.md` in the plugin root first. Skip steps that only work '
            'in Claude Code, and follow its propose-only rule before changing any host configuration.\n')
AGENT_PREAMBLE = PREAMBLE.replace(
    'the folder that contains `skills/` (this file is `skills/<name>/SKILL.md`)',
    'the folder that contains `agents/` (this file is `agents/kaizen-auditor.md`)').replace(
    'wherever this skill uses', 'wherever this agent uses')
# Tracked and untracked files, minus git-ignored ones (out/, caches, .DS_Store).
FILES = subprocess.run(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=ROOT,
                       capture_output=True, text=True, check=True).stdout.split('\0')
TEXT = [ROOT / f for f in FILES if f and not (ROOT / f).is_symlink() and (ROOT / f).is_file() and Path(f).suffix in
        {'.md', '.json', '.sh', '.py', '.toml', '.conf', '.yml', '.yaml', ''}]


def frontmatter(path):
    text = path.read_text()
    match = re.match(r'---\n(.*?)\n---\n', text, re.S)
    assert match, f'{path}: missing frontmatter'
    fields = {}
    for line in match[1].splitlines():
        key, _, value = line.partition(':')
        fields[key.strip()] = value.strip()
    return fields


class RepoTests(unittest.TestCase):
    def test_skill_preamble(self):
        for name in SKILLS:
            with self.subTest(skill=name):
                text = (ROOT / 'skills' / name / 'SKILL.md').read_text()
                self.assertEqual(text.count(PREAMBLE), 1)
                body = text.split('---\n', 2)[2]
                heading = re.search(r'^# .*\n\n', body, re.M)
                self.assertIsNotNone(heading)
                self.assertTrue(body[heading.end():].startswith(PREAMBLE))

    def test_agent_preamble(self):
        text = (ROOT / 'agents/kaizen-auditor.md').read_text()
        self.assertEqual(text.count(AGENT_PREAMBLE), 1)
        self.assertTrue(text.split('---\n', 2)[2].startswith('\n' + AGENT_PREAMBLE))

    def test_host_map(self):
        path = ROOT / 'docs/hosts.md'
        self.assertTrue(path.is_file())
        text = path.read_text()
        for heading in ('Claude Code', 'Codex CLI', 'Copilot'):
            with self.subTest(heading=heading):
                self.assertRegex(text, rf'(?m)^#+ {re.escape(heading)}(?:[ \t]+[^\n]*)?$')

    def test_codex_dispatch_inside_codex(self):
        text = (ROOT / 'skills/codex-dispatch/SKILL.md').read_text()
        self.assertIn(PREAMBLE + 'Inside Codex, this skill does not apply: do the work in the current session.\n', text)

    def test_json_files_parse(self):
        for path in [*ROOT.glob('.claude-plugin/*.json'), ROOT / 'hooks/hooks.json',
                     *ROOT.glob('templates/*.json')]:
            with self.subTest(path=path.name):
                json.loads(path.read_text())

    def test_manifest_names_match(self):
        plugin = json.loads((ROOT / '.claude-plugin/plugin.json').read_text())
        market = json.loads((ROOT / '.claude-plugin/marketplace.json').read_text())
        self.assertRegex(plugin['name'], r'^[a-z0-9]+(-[a-z0-9]+)*$')
        self.assertFalse(plugin['name'].startswith(('claude-', 'anthropic-')))
        self.assertIn(plugin['name'], [p['name'] for p in market['plugins']])
        self.assertRegex(plugin['version'], r'^\d+\.\d+\.\d+$')
        self.assertIn(f"## {plugin['version']}", (ROOT / 'CHANGELOG.md').read_text())

    def test_skill_frontmatter(self):
        for name in SKILLS:
            with self.subTest(skill=name):
                fields = frontmatter(ROOT / 'skills' / name / 'SKILL.md')
                self.assertEqual(fields.get('name'), name)
                self.assertRegex(fields.get('description', ''), r'^".+"$', 'description must be quoted')
                self.assertEqual(fields.get('disable-model-invocation'), 'true')

    def test_skills_have_codex_visibility_sidecar(self):
        for name in SKILLS:
            with self.subTest(skill=name):
                path = ROOT / 'skills' / name / 'agents' / 'openai.yaml'
                self.assertTrue(path.is_file(), str(path))
                self.assertEqual(path.read_text(encoding='utf-8'),
                                 'policy:\n  allow_implicit_invocation: false\n')

    def test_agent_frontmatter(self):
        for path in [*ROOT.glob('agents/*.md'), *ROOT.glob('templates/agents/*.md')]:
            with self.subTest(agent=path.name):
                fields = frontmatter(path)
                self.assertEqual(fields.get('name'), path.stem)
                self.assertTrue(fields.get('description'))
                self.assertTrue(fields.get('tools'), 'agents need a tools allowlist')

    def test_plugin_root_references_exist(self):
        for path in TEXT:
            # Implementation plans may reference files that later packets create.
            if path.relative_to(ROOT).parts[:2] == ('docs', 'plans'):
                continue
            for ref in re.findall(r'\$\{CLAUDE_PLUGIN_ROOT\}/([A-Za-z0-9_./*-]+)', path.read_text()):
                ref = ref.rstrip('.,`)')
                with self.subTest(file=str(path.relative_to(ROOT)), ref=ref):
                    if '*' in ref:
                        self.assertTrue(list(ROOT.glob(ref)), ref)
                    else:
                        self.assertTrue((ROOT / ref).exists(), ref)

    def test_readme_lists_every_skill(self):
        readme = (ROOT / 'README.md').read_text()
        listed = set(re.findall(r'`/agent-kaizen:([a-z-]+)`', readme))
        self.assertEqual(listed - set(SKILLS), set(), 'README names skills that do not exist')
        self.assertEqual(set(SKILLS) - listed, set(), 'skills missing from README')

    def test_no_personal_data(self):
        pattern = re.compile(r'/Users/[A-Za-z]|/home/[a-z]+/|[A-Za-z0-9._%+-]+@(gmail|outlook|yahoo|icloud)\.com'
                             r'|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}')
        for path in TEXT:
            if path.name == 'test_repo.py':
                continue
            with self.subTest(file=str(path.relative_to(ROOT))):
                self.assertIsNone(pattern.search(path.read_text()))


if __name__ == '__main__':
    unittest.main()
