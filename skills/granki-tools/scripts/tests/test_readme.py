"""Every Markdown file of the repository is listed in the README table of contents."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
SKIP = {'README.md'}  # the README itself


class ReadmeTests(unittest.TestCase):
    def test_table_of_contents_lists_every_markdown_file(self):
        readme = (REPO / 'README.md').read_text(encoding='utf-8')
        linked = {Path(m).as_posix() for m in re.findall(r'\]\(([^)#\s]+\.md)\)', readme)}
        files = {p.relative_to(REPO).as_posix() for p in REPO.rglob('*.md')
                 if not any(part in {'.git', '.venv', 'node_modules'} for part in p.parts)}
        missing = sorted(files - linked - SKIP)
        self.assertEqual(missing, [], 'add these files to the README table of contents')
        broken = sorted(f for f in linked if not (REPO / f).is_file())
        self.assertEqual(broken, [], 'README links to missing files')


if __name__ == '__main__':
    unittest.main()
