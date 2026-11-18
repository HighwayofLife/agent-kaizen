"""Coverage for aggregate transcript format drift metadata."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from unittest.mock import patch
import runpy
import tempfile
import unittest

AUDIT = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/token-audit'))
SINCE = datetime(2025, 1, 1, tzinfo=timezone.utc)


class FormatCanaryTests(unittest.TestCase):
    def test_claude_counts_and_skipped_records(self):
        counts = defaultdict(Counter)
        rows = [
            dict(type='user', version='1.0', message={'content': 'private prompt'}),
            dict(type='new_kind', version='1.0', payload='private prompt'),
            dict(type='assistant', version='1.0', message={'model': 'm', 'usage': {'input_tokens': 1, 'output_tokens': 2}}),
            dict(type='assistant', message={'model': 'm', 'usage': {'input_tokens': 1}}),
            dict(type='assistant', message={'model': '<synthetic>'}),
            dict(type='progress'),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'rows.jsonl'
            path.write_text(''.join(json.dumps(dict(row, timestamp='2026-01-01T00:00:00Z')) + '\n' for row in rows)
                            + '{"type":"new_kind", broken}\n')
            list(AUDIT['rows'](path, SINCE, Counter(), keep_tools=True, canary=counts))
        self.assertEqual(dict(counts['1.0']), {'records': 3, 'unknown_records': 1, ('unknown_type', 'new_kind'): 1})
        self.assertEqual(dict(counts['unknown']), dict(records=3, missing_usage=1))
        self.assertNotIn('private prompt', repr(counts))

    def test_non_string_types_are_unknown(self):
        counts = defaultdict(Counter)
        for kind in (['x'], {'a': 1}):
            row = dict(type=kind, timestamp='2026-01-01T00:00:00Z')
            AUDIT['canary_row'](json.dumps(row).encode(), SINCE, counts, False, None)
        self.assertEqual(dict(counts['unknown']),
                         {'records': 2, 'unknown_records': 2, ('unknown_type', '<other>'): 2})

    def test_invalid_versions_and_old_rows(self):
        counts = defaultdict(Counter)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'rows.jsonl'
            rows = [dict(type='user', version=v, timestamp='2026-01-01T00:00:00Z')
                    for v in ('/private/path', 'person@example.invalid', ['bad'])]
            old = b'{"timestamp":"2020-01-01T00:00:00Z","type":"future", broken}'
            path.write_bytes(old + b'\n' + b''.join(json.dumps(row).encode() + b'\n' for row in rows))
            original = json.loads
            def guarded(value, *args, **kwargs):
                self.assertNotEqual(value, old + b'\n')
                return original(value, *args, **kwargs)
            with patch.object(AUDIT['rows'].__globals__['json'], 'loads', side_effect=guarded):
                list(AUDIT['rows'](path, SINCE, Counter(), keep_tools=True, canary=counts))
        self.assertEqual(dict(counts['unknown']), {'records': 3})
        self.assertEqual(list(counts), ['unknown'])

    def test_codex_version_and_missing_usage(self):
        counts = defaultdict(Counter)
        version = None
        rows = [dict(type='session_meta', payload={'cli_version': '2.0'}),
                dict(type='future', payload={}),
                dict(type='event_msg', payload={'type': 'token_count', 'info': {'total_token_usage': {'input_tokens': 1}}}),
                dict(type='event_msg', payload={'type': 'token_count', 'info': {'total_token_usage': {'input_tokens': 1, 'output_tokens': 2, 'total_tokens': 3}}})]
        for row in rows:
            row['timestamp'] = '2026-01-01T00:00:00Z'
            version = AUDIT['canary_row'](json.dumps(row).encode(), SINCE, counts, True, version)
        self.assertEqual(dict(counts['2.0']), {'records': 4, 'unknown_records': 1, 'missing_usage': 1, ('unknown_type', 'future'): 1})
        self.assertEqual(AUDIT['canary_summary'](counts), 'format_canary: v1 unknown_records=1 missing_usage=1 cli=2.0')

    def test_new_known_types(self):
        claude = 'api-request api-request-blob atis-latch session-owner mode ai-title permission-mode tools-used cost-state file-history-delta'.split()
        codex = ['token_usage_record', 'world_state']
        for kinds, is_codex in ((claude, False), (codex, True)):
            counts = defaultdict(Counter)
            for kind in kinds:
                row = dict(type=kind, timestamp='2026-01-01T00:00:00Z')
                AUDIT['canary_row'](json.dumps(row).encode(), SINCE, counts, is_codex, None)
            self.assertEqual(counts['unknown']['unknown_records'], 0)

    def test_report_metadata_round_trip_and_no_data(self):
        options = dict(stuck_repeats=3, fact_sessions=3, prune_prompts=10, prune_min_sessions=2, prune_sessions=5)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = AUDIT['collect']([], root, SINCE, {}, None, options)
            scope = dict(cwd=None, project_dirs=[], project=None, window='all')
            out = root / 'token-audit-one.md'
            text, _ = AUDIT['report'](data, out, scope)
            self.assertIn('FORMAT-DRIFT: no transcript data observed.', text)
            out.write_text(text)
            previous, _ = AUDIT['previous_audit'](root / 'token-audit-two.md', scope)
            self.assertEqual(previous[1]['format_canary'], 'format_canary: v1 unknown_records=0 missing_usage=0 cli=none')
            project = root / 'project'
            project.mkdir()
            path = project / 'session.jsonl'
            for kind, expected in [('user', 0), ('brand-new', 1), ('unsafe type', 1)]:
                path.write_text(json.dumps(dict(type=kind, version='1.0', timestamp='2026-01-01T00:00:00Z', message={})) + '\n')
                with patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': str(root / 'empty')}):
                    data = AUDIT['collect']([project], root / 'absent', SINCE, {}, None, options)
                text, _ = AUDIT['report'](data, out, scope)
                out.write_text(text)
                previous, _ = AUDIT['previous_audit'](root / 'token-audit-two.md', scope)
                self.assertIn('unknown_records=' + str(expected), previous[1]['format_canary'])
                self.assertEqual('FORMAT-DRIFT:' in text, bool(expected))
                if expected:
                    name = kind if kind == 'brand-new' else '<other>'
                    self.assertIn('unknown_types=' + name + ':1', text)
                    self.assertNotIn('unknown_types=', previous[1]['format_canary'])


if __name__ == '__main__':
    unittest.main()
