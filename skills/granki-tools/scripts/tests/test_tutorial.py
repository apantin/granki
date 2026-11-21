"""Run every bash block of docs/user/tutorial.md and check the outputs it promises.

The tutorial is part of the documentation: when a script changes its output or
behaviour, this test fails instead of leaving the tutorial out of date.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
TUTORIAL = REPO / 'docs' / 'user' / 'tutorial.md'


def pandoc_available() -> bool:
    return bool(os.environ.get('GRANKI_PANDOC') or shutil.which('pandoc'))


@unittest.skipUnless(shutil.which('uv') and shutil.which('bash'), 'needs uv and bash')
@unittest.skipUnless(pandoc_available(), 'needs Pandoc for the HTML step')
class TutorialTests(unittest.TestCase):
    def test_tutorial_commands_produce_the_documented_results(self):
        blocks = re.findall(r'```bash\n(.*?)```', TUTORIAL.read_text(encoding='utf-8'), re.S)
        script = '\n'.join(f'echo "### block {i}"\n{b}' for i, b in enumerate(blocks))
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        env = {**os.environ, 'TMPDIR': tmp}  # the tutorial's mktemp lands here and is removed
        result = subprocess.run(['bash', '-c', script], cwd=REPO, capture_output=True, text=True, timeout=600, env=env)
        out = result.stdout
        expected = [
            '| 01-flour | writing v1 | принято 0/3; drafted 3 | — | — | — |',
            '"number": "2,2"',
            '"added": [\n    "N001",\n    "N002",\n    "N003"\n  ]',
            'cannot be accepted: the text still has [нужно от автора',
            '| 01-flour | writing v1 | принято 3/3; accepted 3 | — | — | 2 (критичных 0) |',
            "passed ['plan-sections', 'length', 'numbers', 'claims', 'headings', 'caveats', 'links', 'public', 'figures', 'published-lock']",
            "'name': 'published-lock', 'status': 'failed'",
            '"options": [\n        "new-version",\n        "record-divergence",\n        "no-change"\n      ]',
            '"added": [\n    "N004"',
            '| 01-flour | revising v2 | принято 2/3; accepted 2, drafted после правки 1 | 02-advice.md | section-02-advice-editorial-2026-11-21-1610.md | 2 (критичных 0) |',
            'N002 deferred обычно бесспорная 01-results.md цитата на месте',
            'N003 deferred обычно вопрос 01-results.md цитата на месте',
        ]
        for line in expected:
            self.assertIn(line, out, f'tutorial output changed; stderr:\n{result.stderr[-2000:]}')
        text = TUTORIAL.read_text(encoding='utf-8')
        for line in expected:
            if not line.startswith('"'):  # JSON lines are abbreviated in the tutorial
                self.assertIn(line, text, 'the tutorial no longer shows this output')


if __name__ == '__main__':
    unittest.main()
