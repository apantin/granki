"""Every Markdown file is listed in the README table of contents, and relative links resolve."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
SKIP = {'README.md'}  # the README itself
LINK = re.compile(r'\]\(([^)\s]+)\)')


def markdown_files() -> list[Path]:
    return sorted(p for p in REPO.rglob('*.md')
                  if not any(part in {'.git', '.venv', 'node_modules'} for part in p.parts))


def code_free(text: str) -> str:
    """Drop fenced blocks and inline code: links inside them are examples."""
    text = re.sub(r'```.*?```', '', text, flags=re.S)
    return re.sub(r'`[^`\n]*`', '', text)


class ReadmeTests(unittest.TestCase):
    def test_table_of_contents_lists_every_markdown_file(self):
        readme = (REPO / 'README.md').read_text(encoding='utf-8')
        linked = {Path(m).as_posix() for m in re.findall(r'\]\(([^)#\s]+\.md)\)', readme)}
        files = {p.relative_to(REPO).as_posix() for p in markdown_files()}
        missing = sorted(files - linked - SKIP)
        self.assertEqual(missing, [], 'add these files to the README table of contents')

    def test_relative_links_resolve(self):
        broken = []
        for f in markdown_files():
            for target in LINK.findall(code_free(f.read_text(encoding='utf-8'))):
                path = target.split('#', 1)[0]
                if not path or re.match(r'^[a-z]+:', target):
                    continue
                if not (f.parent / path).exists():
                    broken.append(f'{f.relative_to(REPO)} -> {target}')
        self.assertEqual(broken, [], 'links to missing files')


if __name__ == '__main__':
    unittest.main()
