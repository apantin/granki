"""The version number is the same everywhere it is written (see docs/dev/release.md)."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
SEMVER = r'\d+\.\d+\.\d+'


class VersionTests(unittest.TestCase):
    def test_version_matches_in_every_place(self):
        module = re.search(rf'^module_version:\s*"({SEMVER})"\s*$',
                           (REPO / 'skills' / 'module.yaml').read_text(encoding='utf-8'), re.M)
        self.assertIsNotNone(module, 'skills/module.yaml has no module_version "X.Y.Z"')
        version = module.group(1)

        market = json.loads((REPO / '.claude-plugin' / 'marketplace.json').read_text(encoding='utf-8'))
        plugin = next(p for p in market['plugins'] if p['name'] == 'granki')
        self.assertEqual(plugin['version'], version, 'marketplace.json and module.yaml disagree')

        status = [l for l in (REPO / 'README.md').read_text(encoding='utf-8').splitlines()
                  if l.startswith('> **Статус')]
        self.assertEqual(len(status), 1, 'README must have one status line')
        self.assertIn(f'версия {version}', status[0], 'README status line shows another version')

        changelog = (REPO / 'CHANGELOG.md').read_text(encoding='utf-8')
        first = re.search(rf'^## ({SEMVER}) — ', changelog, re.M)
        self.assertIsNotNone(first, 'CHANGELOG.md has no "## X.Y.Z — …" section')
        self.assertEqual(first.group(1), version, 'the latest CHANGELOG section is another version')


if __name__ == '__main__':
    unittest.main()
