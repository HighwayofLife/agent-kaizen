"""Time token-audit's collect() against a baseline revision on synthetic data (no user data).

Not part of the unittest run. The baseline is HEAD unless --baseline or the
TOKEN_AUDIT_BASELINE environment variable names another revision.
"""
import argparse
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
OPTIONS = dict(stuck_repeats=3, fact_sessions=3, prune_prompts=10, prune_min_sessions=2, prune_sessions=5)
COMPARED = ('codex', 'codex_sessions', 'codex_briefs', 'models', 'sessions', 'tool_counts', 'unused_tools')


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows))


def codex_fixture(root):
    lines = [dict(timestamp='2026-01-01T00:00:00Z', type='turn_context', payload={'model': 'example'})]
    lines += [dict(timestamp='2026-01-01T00:00:01Z', type='response_item',
                   payload={'role': 'assistant', 'content': 'x' * 4000}) for _ in range(1998)]
    lines.append(dict(timestamp='2026-01-01T00:00:02Z', type='event_msg',
                      payload={'type': 'token_count', 'info': {'total_token_usage': {'total_tokens': 100}}}))
    write_jsonl(root / 'sessions/2026/01/01/session.jsonl', lines)


def claude_fixture(root):
    """One scanned project (no recorded tool definitions) and one project left unscanned."""
    def assistant(ident, name):
        return dict(type='assistant', timestamp='2026-01-01T00:00:03Z', sessionId='s', message=dict(
            id=ident, model='example', usage=dict(input_tokens=100, cache_read_input_tokens=900, output_tokens=20),
            content=[dict(type='text', text='y' * 2000),
                     dict(type='tool_use', id='use-' + ident, name=name, input=dict(command='ls -la', note='z' * 500))]))
    rows = []
    for index in range(400):
        rows.append(dict(type='user', timestamp='2026-01-01T00:00:02Z', uuid=f'p{index}', sessionId='s',
                         message=dict(content='prompt')))
        rows.append(assistant(f'm{index}', 'Bash'))
        rows.append(dict(type='user', timestamp='2026-01-01T00:00:04Z', sessionId='s', message=dict(content=[
            dict(type='tool_result', tool_use_id=f'use-m{index}', content='ok' * 200)])))
    write_jsonl(root / 'projects/example/s.jsonl', rows)
    write_jsonl(root / 'projects/unscanned/u.jsonl', [assistant(f'u{index}', f'mcp__server{index % 5}__query')
                                                      for index in range(4000)])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', default=os.environ.get('TOKEN_AUDIT_BASELINE', 'HEAD'),
                        help='git revision holding the baseline scripts/token-audit '
                        '(default: TOKEN_AUDIT_BASELINE or HEAD)')
    parser.add_argument('--max-ratio', type=float, help='fail if current/baseline median exceeds this ratio')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        os.environ['CLAUDE_CONFIG_DIR'] = str(root / 'claude')
        baseline_path = root / 'baseline.py'
        baseline_path.write_bytes(subprocess.check_output(
            ['git', 'show', f'{args.baseline}:scripts/token-audit'], cwd=ROOT))
        baseline = runpy.run_path(str(baseline_path))
        current = runpy.run_path(str(ROOT / 'scripts/token-audit'))
        codex_fixture(root)
        claude_fixture(root / 'claude')
        since = datetime(2025, 1, 1, tzinfo=timezone.utc)
        projects = [root / 'claude/projects/example']

        def run(module):
            return module['collect'](projects, root / 'sessions', since, {}, None, dict(OPTIONS))

        base_data, current_data = run(baseline), run(current)
        assert current_data['headline']['claude_calls'] == 400, 'the Claude fixture was not scanned'
        for key in COMPARED:
            assert base_data[key] == current_data[key], key
        times = [[], []]
        for _ in range(5):
            for index, module in enumerate((baseline, current)):
                start = time.perf_counter()
                run(module)
                times[index].append(time.perf_counter() - start)
        before, after = (statistics.median(samples) for samples in times)
        print(f'baseline {args.baseline}: {before:.6f}s; current: {after:.6f}s; ratio: {after / before:.3f}x')
        if args.max_ratio is not None and after / before > args.max_ratio:
            raise SystemExit(1)


if __name__ == '__main__':
    main()
