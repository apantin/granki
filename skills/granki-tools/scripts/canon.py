#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml>=6"]
# ///
"""Merge the canon (editorial rules) for an article from project, series and article layers.

Layers, from general to specific:
  project  the file named by `canon:` in series-plan.md (for example the
           project's .agents/canon.md)
  series   canon.md next to series-plan.md, if present
  article  canon.md in the article folder, if present

Each layer is Markdown split into `##` sections. In a more specific layer:
  ## Title       replaces the section with the same title
  ## Title (+)   appends to that section
  ## Title (-)   removes that section
  any other title is added at the end.
A (+) or (-) for a title no upper layer has is reported in `warnings`: it is
usually a typo or a section named differently in the project layer.
The standard section titles are those of the template
assets/templates/canon.md.
Text before the first `##` of the project layer is kept as the preamble.

Prints the merged Markdown with a source note per section, or JSON with
--format json. Exit code 0, or 2 on configuration errors.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from granki_core import GrankiError, dump_json, load_series, split_frontmatter  # noqa: E402

HEADING = re.compile(r'^## +(.+?)\s*$', re.M)
MODIFIER = re.compile(r'^(.*?)\s*\((\+|-)\)$')
CANON_FILE = 'canon.md'


FENCE = re.compile(r'(```|~~~).*?\1', re.S)


def parse(text: str) -> tuple[str, list[tuple[str, str | None, str]]]:
    """Return the preamble and a list of (title, modifier, body). Headings inside code blocks do not count."""
    _, text = split_frontmatter(text)
    fenced = [(m.start(), m.end()) for m in FENCE.finditer(text)]
    matches = [m for m in HEADING.finditer(text) if not any(a <= m.start() < b for a, b in fenced)]
    preamble = text[:matches[0].start()] if matches else text
    sections = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        title, modifier = match.group(1).strip(), None
        found = MODIFIER.match(title)
        if found:
            title, modifier = found.group(1).strip(), found.group(2)
        sections.append((title, modifier, text[match.end():end].strip('\n')))
    return preamble.strip('\n'), sections


def merge(layers: list[tuple[str, Path]]) -> dict:
    preamble, order, content, sources, warnings = '', [], {}, {}, []
    for index, (name, path) in enumerate(layers):
        head, sections = parse(path.read_text(encoding='utf-8'))
        if index == 0:
            preamble = head
        elif not sections:
            warnings.append(f'{name} layer {path} has no ## sections and changes nothing')
        elif head.strip() and not head.strip().startswith('#'):
            warnings.append(f'{name} layer {path}: text before the first ## is ignored')
        for title, modifier, body in sections:
            key = title.casefold()
            if modifier == '-':
                if key in content:
                    order.remove(key)
                    del content[key], sources[key]
                elif index:
                    warnings.append(f'{name} layer removes «{title}», but no upper layer has it; check the title')
                continue
            if modifier == '+' and key in content:
                content[key] = (content[key][0], content[key][1].rstrip() + '\n\n' + body)
                sources[key].append(name)
                continue
            if modifier == '+' and index:
                warnings.append(f'{name} layer appends to «{title}», but no upper layer has it; '
                                'added as a new section, check the title')
            if key not in content:
                order.append(key)
            elif not re.sub(r'<!--.*?-->', '', body, flags=re.S).strip() and content[key][1].strip():
                warnings.append(f'{name} layer replaces «{title}» with an empty section; use «## {title} (+)» to add or «(-)» to remove')
            content[key] = (title, body)
            sources[key] = [name]
    return {'layers': [{'layer': n, 'path': str(p)} for n, p in layers],
            'preamble': preamble,
            'sections': [{'title': content[k][0], 'sources': sources[k], 'body': content[k][1]} for k in order],
            'warnings': warnings}


def layers_for(series_path: Path, article: str | None) -> list[tuple[str, Path]]:
    series = load_series(series_path)
    root = series_path.parent.resolve()
    layers = []
    if series.get('canon'):
        project = (root / series['canon']).resolve()
        if not project.is_file():
            raise GrankiError(f'Project canon not found: {project}')
        layers.append(('project', project))
    if (root / CANON_FILE).is_file():
        layers.append(('series', root / CANON_FILE))
    if article:
        article = Path(article).name  # accept a path to the article folder too
        if article not in series['articles']:
            raise GrankiError(f'Article {article} is not listed in {series_path.name}')
        if (root / article / CANON_FILE).is_file():
            layers.append(('article', root / article / CANON_FILE))
    if not layers:
        raise GrankiError('No canon layers: set `canon:` in series-plan.md or add canon.md')
    return layers


def markdown(merged: dict) -> str:
    parts = [merged['preamble']] if merged['preamble'] else []
    parts.append('<!-- Собрано из: ' + ', '.join(f'{l["layer"]} — {l["path"]}' for l in merged['layers']) + ' -->')
    parts += [f'<!-- ВНИМАНИЕ: {w} -->' for w in merged['warnings']]
    for section in merged['sections']:
        parts.append(f'## {section["title"]}\n<!-- источник: {", ".join(section["sources"])} -->\n\n{section["body"]}')
    return '\n\n'.join(parts) + '\n'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--series', type=Path, required=True, help='series-plan.md')
    parser.add_argument('--article', help='article folder name; without it only project and series layers apply')
    parser.add_argument('--format', choices=['md', 'json'], default='md')
    args = parser.parse_args(argv)
    try:
        merged = merge(layers_for(args.series, args.article))
    except (GrankiError, OSError) as error:
        sys.stdout.write(dump_json({'status': 'error', 'reason': str(error)}))
        return 2
    sys.stdout.write(dump_json(merged) if args.format == 'json' else markdown(merged))
    return 0


if __name__ == '__main__':
    sys.exit(main())
