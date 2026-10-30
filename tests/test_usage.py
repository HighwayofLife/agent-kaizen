"""Offline agent usage and extract contract tests."""
from collections import Counter, defaultdict
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import runpy
import unittest
from unittest import mock

from test_scripts import SCRIPTS, StubCase, jsonl, write


AUDIT = runpy.run_path(str(SCRIPTS / 'token-audit'))


class UsageTests(StubCase):
    def fixture(self):
        now = datetime.now(timezone.utc).isoformat()
        project = self.home / '.claude/projects/example'

        def row(kind, content, ident=None, model='claude-cheap', **fields):
            message = dict(content=content)
            if kind == 'assistant':
                message.update(id=ident, model=model, usage=dict(output_tokens=100000))
            return dict(type=kind, timestamp=now, message=message, **fields)

        def tool(ident, name='Bash', **inputs):
            return dict(type='tool_use', id=ident, name=name, input=inputs)

        def result(ident, content, failed=False):
            return dict(type='tool_result', tool_use_id=ident, content=content, is_error=failed)

        main = row('assistant', [tool('spawn-one', 'Agent', subagent_type='worker', prompt='one'),
                                 tool('spawn-two', 'Agent', subagent_type='worker', prompt='two'),
                                 tool('spawn-other', 'Agent', subagent_type='other', prompt='other')], 'main')
        main['message']['usage']['output_tokens'] = 1000000
        jsonl(project / 'main.jsonl', [row('user', 'start'), main,
            row('user', [result('spawn-one', 'x' * 10), result('spawn-two', 'y' * 20)])])
        first = row('assistant', [tool(f'fail-{i}', command='pytest tests') for i in range(3)],
                    'one', 'claude-pro-version', perTurnEffort='high', effort='low')
        first_rows = [row('user', 'start'), first, copy.deepcopy(first),
            row('user', [result(f'fail-{i}', 'Exit code: 2\nfailed', True) for i in range(3)]),
            row('user', 'next'),
            row('assistant', [tool('benign', command='rg absent'), tool('read', 'Read')],
                'two', 'claude-pro-version', effort='low'),
            row('user', [result('benign', 'Exit code: 1\nno matches', True), result('read', 'ok')])]
        second_rows = [row('user', 'start'),
            row('assistant', [], 'three', 'claude-mid', effort='low'),
            row('assistant', [], 'four', 'claude-mid', perTurnEffort=['bad'], effort='high'),
            row('assistant', [], 'five', 'claude-mid'),
            row('assistant', [], 'six', 'claude-mid', effort=42)]
        for name, kind, rows in [('one', 'worker', first_rows), ('two', 'worker', second_rows),
                                 ('other', 'other', [row('assistant', [], 'other')])]:
            path = project / f'main/subagents/{name}.jsonl'
            jsonl(path, rows)
            write(path.with_suffix('.meta.json'), json.dumps(dict(agentType=kind)))
        return write(self.root / 'prices.json', json.dumps(dict(models={
            'claude-cheap': dict(output=1), 'claude-mid': dict(output=2), 'claude-pro': dict(output=4)},
            aliases={'claude-': 'claude-cheap', 'claude-pro-': 'claude-pro'})))

    def audit(self, *args):
        return json.loads(self.run_script('token-audit', '--pricing', self.fixture(), '--json', *args).stdout)

    def test_exact_usage_and_report_contract(self):
        data = self.audit()
        expected = [dict(agent='worker', spawns=2, calls_median=3, calls_p90=4,
            cost=1.6, cost_share=0.592593, models={'claude-pro-version': 2, 'claude-mid': 4},
            effort=dict(high=1, low=2, unknown=3), result_chars_median=17,
            stuck_share=0.333333, failure_rate=0.6, cheaper_model_candidate=True),
            dict(agent='other', spawns=1, calls_median=1, calls_p90=1, cost=0.1, cost_share=0.037037,
                 models={'claude-cheap': 1}, effort=dict(unknown=1), result_chars_median=None,
                 stuck_share=0.0, failure_rate=0.0, cheaper_model_candidate=False)]
        self.assertEqual(data['agent_usage'], expected)
        self.assertFalse(any(key.startswith('_') for key in data))
        text = Path(data['report_path']).read_text()
        self.assertLessEqual(len(text.split('## Cost')[0].splitlines()), 80)
        self.assertIn('Agent | Spawns | Median/max calls | Context | Avg context | Median minutes | '
                      'Median/max brief chars | Cost share | Models | Effort', text)
        self.assertIn('| 59.3% | claude-mid, claude-pro-version | unknown 3, low 2, high 1', text)
        lines = text.splitlines()
        index = next(i for i, line in enumerate(lines) if line.startswith('<!-- token-audit-headline '))
        self.assertEqual(lines[index + 1], '<!-- token-audit-scope ' + json.dumps(data['scope'], sort_keys=True) + ' -->')
        self.assertEqual(lines[index + 2], '<!-- token-audit-extract ' + json.dumps(dict(
            v=1, file=Path(data['extract_path']).name)) + ' -->')
        self.assertNotIn('extract', json.loads(lines[index][len('<!-- token-audit-headline '):-len(' -->')]))

    def test_extract_defaults_override_and_privacy(self):
        pricing = self.fixture()
        for config in (None, self.root / 'config'):
            with self.subTest(config=config):
                if config is not None:
                    self.env['CLAUDE_CONFIG_DIR'] = str(config)
                output = self.root / 'docs/kaizen'
                data = json.loads(self.run_script('token-audit', '--pricing', pricing, '--out', output, '--json').stdout)
                report = Path(data['report_path'])
                extract = Path(data['extract_path'])
                self.assertTrue(extract.is_absolute())
                self.assertEqual(extract.parent, (config or self.home / '.claude') / 'audits/extracts')
                self.assertEqual(extract.name, report.stem + '.extract.json')
                self.assertFalse(list(output.rglob('*.extract.json')))
                value = json.loads(extract.read_text())
                self.assertEqual(value, dict(v=1, scope=data['scope'], since=data['since'], report=report.name,
                    usage=dict(agents=data['agent_usage'], sessions=[], task_switches=[], instructions=[])))
                for text in (extract.read_text(), report.read_text()):
                    self.assertNotIn(str(self.home), text)
                    self.assertNotIn(str(self.root), text)
        data = json.loads(self.run_script('token-audit', '--pricing', pricing, '--extract-out', self.root / 'x', '--json').stdout)
        self.assertEqual(Path(data['extract_path']).parent, self.root / 'x')
        self.assertEqual(list((self.root / 'x').iterdir()), [Path(data['extract_path'])])

    def test_extract_failure_is_nonfatal_and_normal_stdout_unchanged(self):
        blocked = write(self.root / 'blocked', 'file, not a directory')
        result = self.run_script('token-audit', '--extract-out', blocked, '--json')
        data = json.loads(result.stdout)
        self.assertIsNone(data['extract_path'])
        self.assertTrue(Path(data['report_path']).is_file())
        self.assertIn('token-audit: extract not written (', result.stderr)
        normal = self.run_script('token-audit', '--extract-out', self.root / 'extracts')
        report = Path(normal.stdout.splitlines()[0])
        self.assertTrue(report.is_file())
        self.assertTrue((self.root / 'extracts' / (report.stem + '.extract.json')).is_file())

    def test_atomic_replace_failure_cleans_temporary_file(self):
        directory = self.root / 'extracts'
        out = self.root / 'token-audit-test.md'
        with mock.patch.object(AUDIT['os'], 'replace', side_effect=OSError('fixture')), \
                mock.patch.object(AUDIT['sys'], 'stderr') as stderr:
            self.assertIsNone(AUDIT['write_extract'](dict(since='date', agent_usage=[]), out, directory, {}))
        self.assertEqual(list(directory.iterdir()), [])
        self.assertIn('extract not written', ''.join(call.args[0] for call in stderr.write.call_args_list))

    def test_missing_and_malformed_model_and_effort(self):
        now = datetime.now(timezone.utc).isoformat()
        path = self.home / '.claude/projects/example/main/subagents/worker.jsonl'
        rows = [dict(type='assistant', timestamp=now, message=dict(usage=dict(output_tokens=1))),
                dict(type='assistant', timestamp=now, perTurnEffort={}, effort=None,
                     message=dict(model=['bad'], usage=dict(output_tokens=1))),
                dict(type='assistant', timestamp=now, perTurnEffort=None, effort='low',
                     message=dict(model=None, usage=dict(output_tokens=1)))]
        jsonl(path, rows)
        write(path.with_suffix('.meta.json'), json.dumps(dict(agentType='worker')))
        data = json.loads(self.run_script('token-audit', '--json').stdout)
        self.assertEqual(data['agent_usage'][0]['models'], dict(unknown=3))
        self.assertEqual(data['agent_usage'][0]['effort'], dict(unknown=2, low=1))


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.data = dict(agents={'worker': [dict(calls=15)]},
            cost=dict(total=20, by_agent={'worker': 1}),
            _pricing=dict(models={'claude-cheap': dict(output=1), 'claude-pro': dict(output=4)},
                          aliases={'claude-': 'claude-cheap', 'claude-pro-': 'claude-pro'}),
            _agent_models=defaultdict(Counter, worker=Counter({'claude-pro-version': 1})),
            _agent_effort=defaultdict(Counter), _agent_result_chars=defaultdict(list, worker=[4000]),
            _agent_turns=Counter(), _agent_flagged=Counter(), _agent_results=Counter(), _agent_failed=Counter())

    def usage(self):
        return AUDIT['agent_usage'](self.data)[0]

    def test_thresholds_inclusive(self):
        self.assertTrue(self.usage()['cheaper_model_candidate'])

    def test_each_condition_independently(self):
        original = copy.deepcopy(self.data)
        for condition in ('cost', 'calls', 'chars', 'missing_chars', 'cheap', 'unpriced', 'no_pricing', 'no_claude'):
            with self.subTest(condition=condition):
                self.data = copy.deepcopy(original)
                if condition == 'cost':
                    self.data['cost']['total'] = 21
                elif condition == 'calls':
                    self.data['agents']['worker'][0]['calls'] = 16
                elif condition == 'chars':
                    self.data['_agent_result_chars']['worker'] = [4001]
                elif condition == 'missing_chars':
                    self.data['_agent_result_chars']['worker'] = []
                elif condition in ('cheap', 'unpriced'):
                    self.data['_agent_models']['worker'] = Counter({
                        'claude-cheap' if condition == 'cheap' else 'unknown': 1})
                elif condition == 'no_pricing':
                    self.data['_pricing'] = {}
                else:
                    self.data['_pricing']['models'] = {'other': dict(output=4)}
                self.assertFalse(self.usage()['cheaper_model_candidate'])

    def test_zero_total_sorting_and_nearest_rank(self):
        self.data['cost'] = dict(total=0, by_agent={})
        self.data['agents'] = {'worker': [dict(calls=n) for n in range(1, 11)], 'aaa': [dict(calls=1)]}
        rows = AUDIT['agent_usage'](self.data)
        self.assertEqual([row['agent'] for row in rows], ['aaa', 'worker'])
        self.assertEqual((rows[1]['calls_median'], rows[1]['calls_p90']), (5.5, 9))
        self.assertEqual((rows[1]['cost'], rows[1]['cost_share']), (0, 0))

    def test_pricing_lookup_and_unpriced_models_ignored(self):
        pricing = self.data['_pricing']
        self.assertEqual(AUDIT['pricing_key'](pricing, 'claude-pro-version'), 'claude-pro')
        self.assertEqual(AUDIT['pricing_key'](pricing, 'claude-cheap'), 'claude-cheap')
        self.assertIsNone(AUDIT['pricing_key'](pricing, 'unknown'))
        pricing['aliases']['missing'] = 'absent'
        self.assertIsNone(AUDIT['pricing_key'](pricing, 'missing-version'))
        self.data['_agent_models']['worker']['unknown'] = 100
        self.assertTrue(self.usage()['cheaper_model_candidate'])

    def test_report_cells_escape_and_limit_models(self):
        name = 'worker|\nname'
        data = dict(agents={name: [dict(calls=1, context=1, minutes=0)]}, briefs={}, agent_usage=[dict(
            agent=name, cost_share=0.5, models={'fourth': 1, 'third': 2, 'second': 3, 'first|\nx': 4},
            effort={'high|\nx': 2})])
        text = AUDIT['agent_stats'](data)[0][2]
        self.assertIn('worker\\| name', text)
        self.assertIn('first\\| x, second, third', text)
        self.assertIn('high\\| x 2', text)
        self.assertNotIn('fourth', text)


if __name__ == '__main__':
    unittest.main()
