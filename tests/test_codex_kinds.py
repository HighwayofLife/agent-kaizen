"""Codex session classification, durations, and report coverage."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import runpy

from test_scripts import SCRIPTS, StubCase, jsonl

AUDIT = runpy.run_path(str(SCRIPTS / 'token-audit'))


class CodexKindsTests(StubCase):
    def test_kinds_durations_and_json(self):
        now = datetime.now(timezone.utc).replace(microsecond=0)
        prompts = [('review-plan', 'VERDICT: APPROVE | REVISE'),
                   ('review-diff', 'VERDICT: NO ISSUES'),
                   ('planner', 'as the engineering planner'),
                   ('engineer', 'You are working in a git repository. Read AGENTS'),
                   ('other', 'ordinary request')]
        for i, (kind, prompt) in enumerate(prompts + [prompts[0]]):
            start = now - timedelta(minutes=40)
            end = start + timedelta(minutes=10 if i != 5 else 30)
            rows = [dict(timestamp=start.isoformat(), type='turn_context',
                         payload=dict(model='model-a', effort='high')),
                    dict(timestamp=start.isoformat(), type='response_item',
                         payload=dict(role='user', content=[dict(text=prompt)])),
                    dict(timestamp=end.isoformat(), type='event_msg',
                         payload=dict(type='token_count', info=dict(total_token_usage=dict(total_tokens=100))))]
            if kind == 'other':
                rows = [dict(timestamp=start.isoformat(), type='event_msg',
                             payload=dict(type='token_count', info=dict(total_token_usage=dict(total_tokens=100))))]
            jsonl(self.home / f'.codex/sessions/2026/01/01/{i}.jsonl', rows)
        data = json.loads(self.run_script('token-audit', '--json').stdout)
        sessions = data['codex_sessions']
        self.assertEqual(len(sessions), 6)
        by_kind = {row['kind']: row for row in sessions}
        self.assertEqual(set(by_kind), {kind for kind, _ in prompts})
        self.assertEqual(by_kind['planner'], dict(kind='planner', model='model-a', effort='high',
                                                  tokens=100, duration_s=600))
        self.assertEqual(by_kind['other']['duration_s'], None)
        report = Path(data['report_path']).read_text()
        self.assertIn('review-plan | model-a | high | 2 | 20.0 | 0.7 | 200', report)
        self.assertIn('other | unknown | n/a | 1 | n/a | n/a | 100', report)
        self.assertIn('## 7. Codex by model', report)
        self.assertLessEqual(len(report.split('## Cost')[0].splitlines()), 80)
