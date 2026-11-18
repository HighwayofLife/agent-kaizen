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
        self.assertEqual(dict(counts['1.0']), dict(records=3, unknown_records=1))
        self.assertEqual(dict(counts['unknown']), dict(records=3, missing_usage=1))
        self.assertNotIn('private prompt', repr(counts))

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
        self.assertEqual(dict(counts['2.0']), dict(records=4, unknown_records=1, missing_usage=1))
        self.assertEqual(AUDIT['canary_summary'](counts), 'format_canary: v1 unknown_records=1 missing_usage=1 cli=2.0')

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
            for kind, expected in [('user', 0), ('future', 1)]:
                path.write_text(json.dumps(dict(type=kind, version='1.0', timestamp='2026-01-01T00:00:00Z', message={})) + '\n')
                with patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': str(root / 'empty')}):
                    data = AUDIT['collect']([project], root / 'absent', SINCE, {}, None, options)
                text, _ = AUDIT['report'](data, out, scope)
                out.write_text(text)
                previous, _ = AUDIT['previous_audit'](root / 'token-audit-two.md', scope)
                self.assertIn('unknown_records=' + str(expected), previous[1]['format_canary'])
                self.assertEqual('FORMAT-DRIFT:' in text, bool(expected))


if __name__ == '__main__':
    unittest.main()
