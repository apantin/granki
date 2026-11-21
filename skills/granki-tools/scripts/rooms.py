#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""Install Granki discussion rooms into a BMad project's party-mode customization.

  install --project-root P   append Granki members and groups to
                             P/_bmad/custom/bmad-party-mode.toml
  status  --project-root P   report which Granki members and groups are there

Existing entries with the same member `code` or group `id` are left as they
are, so a team can override a Granki persona in that file. Running install
again adds nothing new. Prints JSON. Exit code 0, or 2 on errors.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path

ROOMS = Path(__file__).resolve().parent.parent / 'assets' / 'party-rooms.toml'
BLOCK = re.compile(r'^\[\[workflow\.(party_members|party_groups)\]\]\s*$', re.M)


def blocks(text: str) -> list[tuple[str, str, str]]:
    """(kind, key, text) for every member or group block of the rooms file."""
    starts = [m for m in BLOCK.finditer(text)]
    out = []
    for i, match in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(text)
        chunk = text[match.start():end].rstrip() + '\n'
        data = tomllib.loads(chunk.replace(match.group(0), '[x]', 1))['x']
        kind = match.group(1)
        out.append((kind, data['code'] if kind == 'party_members' else data['id'], chunk))
    return out


def existing(path: Path) -> tuple[set, set]:
    if not path.is_file():
        return set(), set()
    data = tomllib.loads(path.read_text(encoding='utf-8')).get('workflow', {})
    return ({m.get('code') for m in data.get('party_members', [])},
            {g.get('id') for g in data.get('party_groups', [])})


def target(project: Path) -> Path:
    if not (project / '_bmad').is_dir():
        raise SystemExit(json.dumps({'status': 'error', 'reason': f'No _bmad/ in {project}: install BMad Method v6 core first'}, ensure_ascii=False))
    return project / '_bmad' / 'custom' / 'bmad-party-mode.toml'


def install(project: Path) -> dict:
    path = target(project)
    members, groups = existing(path)
    added = []
    chunks = []
    for kind, key, chunk in blocks(ROOMS.read_text(encoding='utf-8')):
        present = members if kind == 'party_members' else groups
        if key not in present:
            chunks.append(chunk)
            added.append(key)
    if chunks:
        path.parent.mkdir(parents=True, exist_ok=True)
        old = path.read_text(encoding='utf-8') if path.is_file() else ''
        header = '' if old else '# Team overrides for bmad-party-mode.\n'
        text = old.rstrip('\n') + ('\n\n' if old else header + '\n') + '# --- Granki rooms ---\n\n' + '\n'.join(chunks)
        tomllib.loads(text)  # refuse to write a file party mode could not read
        path.write_text(text, encoding='utf-8')
    return {'status': 'passed', 'file': str(path), 'added': added}


def status(project: Path) -> dict:
    if not (project / '_bmad').is_dir():
        return {'status': 'passed', 'installed': False, 'bmad_core': False,
                'reason': f'No _bmad/ in {project}: install BMad Method v6 core first, then run rooms.py install'}
    path = target(project)
    members, groups = existing(path)
    wanted = blocks(ROOMS.read_text(encoding='utf-8'))
    missing = [key for kind, key, _ in wanted if key not in (members if kind == 'party_members' else groups)]
    return {'status': 'passed', 'file': str(path), 'bmad_core': True, 'installed': not missing, 'missing': missing}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=['install', 'status'])
    parser.add_argument('--project-root', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = install(args.project_root) if args.command == 'install' else status(args.project_root)
    except SystemExit as stop:
        sys.stdout.write(str(stop) + '\n')
        return 2
    except (OSError, tomllib.TOMLDecodeError) as error:
        sys.stdout.write(json.dumps({'status': 'error', 'reason': str(error)}, ensure_ascii=False) + '\n')
        return 2
    sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
