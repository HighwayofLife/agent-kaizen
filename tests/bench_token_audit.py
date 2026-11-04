"""Compare synthetic Codex collection with the pre-05a scanner (no user data)."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import runpy
import statistics
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    old_source = subprocess.check_output(['git', 'show', 'ff207e5^:scripts/token-audit'], cwd=ROOT)
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        os.environ['CLAUDE_CONFIG_DIR'] = str(root / 'empty-claude')
        os.environ['CLAUDE_JSON'] = str(root / 'empty.json')
        old_path = root / 'old.py'
        old_path.write_bytes(old_source)
        old = runpy.run_path(str(old_path))
        head_path = root / 'head.py'
        head_path.write_bytes(subprocess.check_output(['git', 'show', 'HEAD:scripts/token-audit'], cwd=ROOT))
        head = runpy.run_path(str(head_path))
        new = runpy.run_path(str(ROOT / 'scripts/token-audit'))
        session = root / 'sessions/2026/01/01/session.jsonl'
        session.parent.mkdir(parents=True)
        lines = [dict(timestamp='2026-01-01T00:00:00Z', type='turn_context', payload={'model': 'example'})]
        lines += [dict(timestamp='2026-01-01T00:00:01Z', type='response_item',
                       payload={'role': 'assistant', 'content': 'x' * 4000}) for _ in range(1998)]
        lines.append(dict(timestamp='2026-01-01T00:00:02Z', type='event_msg',
                          payload={'type': 'token_count', 'info': {'total_token_usage': {'total_tokens': 100}}}))
        session.write_text(''.join(json.dumps(line) + '\n' for line in lines))
        since = datetime(2025, 1, 1, tzinfo=timezone.utc)
        baseline_data = head['collect']([], root / 'sessions', since, {}, None, {})
        current_data = new['collect']([], root / 'sessions', since, {}, None, {})
        for key in ('codex', 'codex_sessions', 'codex_briefs'):
            assert baseline_data[key] == current_data[key], key
        times = [[], [], []]
        for _ in range(5):
            for index, module in enumerate((old, head, new)):
                start = time.perf_counter()
                module['collect']([], root / 'sessions', since, {}, None, {})
                times[index].append(time.perf_counter() - start)
        before, baseline, after = (statistics.median(samples) for samples in times)
        print(f'pre-05a: {before:.6f}s; HEAD: {baseline:.6f}s; current: {after:.6f}s; ratio: {after / before:.3f}x')


if __name__ == '__main__':
    main()
