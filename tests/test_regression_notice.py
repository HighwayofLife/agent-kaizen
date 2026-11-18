"""SessionStart regression notice isolation, deadline and atomic daily claim."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

from test_hooks import HOOKS, ROOT, bare_path


class RegressionNoticeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.project, self.audits, self.plugin = (root / name for name in ('project', 'audits', 'plugin'))
        (self.project / 'docs/kaizen').mkdir(parents=True)
        self.audits.mkdir()
        (self.audits / 'token-audit-synthetic.md').write_text('audit')
        self.checker = self.plugin / 'scripts/usage-db'
        self.checker.parent.mkdir(parents=True)
        self.db = root / 'usage.db'
        self.env = dict(os.environ, AUDIT_DIR=str(self.audits), CLAUDE_CONFIG_DIR=str(root / 'config'),
                        CLAUDE_PLUGIN_ROOT=str(self.plugin), KAIZEN_USAGE_DB=str(self.db))
        self.finding = 'REGRESSION main_avg_context 30000 vs 10000'

    def markers(self):
        return list(self.audits.glob('usage-regression.noticed-*'))

    def notice(self, **env):
        result = subprocess.run(['bash', str(HOOKS / 'audit-notice.sh')], text=True, capture_output=True,
                                input=json.dumps({'cwd': str(self.project)}), timeout=6, check=True,
                                env={**self.env, **env})
        self.assertEqual(result.stderr, '')
        return json.loads(result.stdout).get('hookSpecificOutput', {}).get('additionalContext', '')

    def test_combines_notices_and_claims_one_line_across_concurrent_sessions(self):
        self.checker.write_text(f'import time\ntime.sleep(0.15)\nprint({self.finding!r})\n'
                                'print("REGRESSION output_per_call 300 vs 50")\n')
        self.checker.with_name('experiment-check').write_text('print("synthetic check")\nraise SystemExit(1)\n')
        merged = self.notice()
        self.assertIn('unreviewed usage audit', merged)
        self.assertIn('Experiments need attention', merged)
        self.assertEqual([line for line in merged.splitlines() if line.startswith('REGRESSION ')], [self.finding])
        self.assertEqual(self.notice(), '')
        for marker in self.audits.glob('*.noticed-*'):
            marker.unlink()
        with ThreadPoolExecutor(max_workers=6) as pool:
            messages = list(pool.map(lambda _: self.notice(), range(6)))
        self.assertEqual(sum(msg.count('REGRESSION ') for msg in messages), 1)
        self.assertEqual(sum('unreviewed usage audit' in msg for msg in messages), 1)
        self.assertEqual(sum('Experiments need attention' in msg for msg in messages), 1)
        self.assertEqual([path.name for path in self.markers()],
                         ['usage-regression.noticed-' + datetime.now(timezone.utc).date().isoformat()])

    def test_bad_data_missing_tool_deadline_and_permission_preserve_audit(self):
        self.db.write_text('invalid SQLite')
        for case, code in (
            ('sqlite', None), ('missing', None), ('no_python', f'print({self.finding!r})'),
            ('malformed', 'print("REGRESSION bogus data")'), ('insufficient', 'print("insufficient data metric")'),
            ('permission', f'print({self.finding!r})\nraise PermissionError("denied")'),
            ('timeout', 'import signal, time\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\ntime.sleep(30)'),
        ):
            with self.subTest(case=case):
                for marker in self.audits.glob('*.noticed-*'):
                    marker.unlink()
                if code:
                    self.checker.write_text(code)
                options = {'CLAUDE_PLUGIN_ROOT': str(ROOT)} if case == 'sqlite' else {}
                start = time.monotonic()
                if case == 'no_python':
                    with bare_path('jq', 'ls', 'head', 'grep', 'date') as path:
                        msg = self.notice(PATH=path, **options)
                else:
                    msg = self.notice(**options)
                self.assertLess(time.monotonic() - start, 5)
                self.assertIn('unreviewed usage audit', msg)
                self.assertNotIn('REGRESSION ', msg)
                self.assertEqual(self.markers(), [])

    def test_marker_is_released_if_notice_cannot_be_encoded(self):
        self.checker.write_text(f'print({self.finding!r})\n')
        with tempfile.TemporaryDirectory() as binpath:
            jq = Path(binpath) / 'jq'
            jq.write_text(f'#!/bin/bash\n[ "$1" = -n ] && exit 1\nexec "{shutil.which("jq")}" "$@"\n')
            jq.chmod(0o755)
            self.assertEqual(self.notice(PATH=binpath + os.pathsep + self.env['PATH']), '')
        self.assertEqual(self.markers(), [])
        self.assertIn(self.finding, self.notice())
