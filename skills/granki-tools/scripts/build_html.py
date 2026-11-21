#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml>=6"]
# ///
"""Build standalone offline HTML for the articles of a series, or for one article.

Sections are joined in prefix order, the first-level heading of the first
section becomes the article title, images are embedded, and a table of
contents is built from the headings. After rendering, the script checks that
headings, paragraphs, table cells, code, spoilers and images match the
source exactly and that the page loads nothing from outside.

Needs Pandoc: on PATH, in GRANKI_PANDOC or via --pandoc. HTML comments in
sections, such as caveat markers, are removed before rendering.

Prints JSON. Exit code 0 when every page passed its check, 1 when a check
failed, 2 on configuration errors or a missing Pandoc.
"""
from __future__ import annotations

import argparse
import base64
import html
import json
import os
import re
import shutil
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from granki_core import (COMMENT, FENCE, SECTION_NAME, GrankiError, dump_json, join_sections,  # noqa: E402
                         load_plan, load_series, section_paths, series_of, sha256_text)

TEMPLATE = Path(__file__).resolve().parent.parent / 'assets' / 'article.template.html'
FORMAT = 'markdown-smart-tex_math_dollars-implicit_figures'
IMAGE_SUFFIXES = ('.png', '.jpg', '.jpeg', '.svg', '.webp')


class BuildError(Exception):
    """A rendered page differs from its source or loads external content."""


def has_sections(plan_path: Path) -> bool:
    """An article can be built once it has a plan and at least one NN-*.md section."""
    if not plan_path.is_file():
        return False
    plan = load_plan(plan_path)
    folder = plan['_root'] / plan['sections_dir']
    return folder.is_dir() and any(SECTION_NAME.fullmatch(p.name) for p in folder.glob('*.md'))


def sha(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()


def find_pandoc(explicit: str | None) -> str:
    candidate = explicit or os.environ.get('GRANKI_PANDOC') or shutil.which('pandoc')
    if not candidate or not Path(candidate).exists() and not shutil.which(candidate):
        raise GrankiError('Pandoc not found: install it, set GRANKI_PANDOC or pass --pandoc')
    return candidate


def run_pandoc(binary, args, data: bytes) -> bytes:
    return subprocess.run([binary, *args], input=data, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, check=True).stdout


def nodes(value, tag):
    if isinstance(value, dict):
        if value.get('t') == tag:
            yield value
        for v in value.values():
            yield from nodes(v, tag)
    elif isinstance(value, list):
        for v in value:
            yield from nodes(v, tag)


def plain(value):
    if isinstance(value, list):
        return ''.join(plain(v) for v in value)
    if isinstance(value, dict):
        tag, c = value.get('t'), value.get('c')
        if tag in ['Str', 'Math']:
            return c if isinstance(c, str) else c[-1]
        if tag in ['Space', 'SoftBreak', 'LineBreak']:
            return ' '
        if tag in ['Code', 'CodeBlock']:
            return c[-1]
        if tag in ['Image', 'Link']:
            return plain(c[1])
        if tag in ['RawBlock', 'RawInline']:
            return ''
        return plain(c)
    return ''


def normal(value):
    return ' '.join(value.split())


class Inspect(HTMLParser):
    """Collect rendered text, table contents, code, images and local anchors."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_article = self.in_header = self.in_mobile = self.in_footer = self.in_code = False
        self.paragraph = self.cell = self.row = self.table = self.heading = None
        self.paragraphs, self.tables, self.code, self.images = [], [], [], []
        self.resources, self.ids, self.links, self.headings = [], [], [], []
        self.details = self.summaries = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get('id'):
            self.ids.append(a['id'])
        if tag == 'a':
            self.links.append(a.get('href', ''))
        if tag in ['img', 'script', 'link', 'iframe', 'source']:
            self.resources.append(a.get('src', a.get('href', '')))
        if tag == 'article':
            self.in_article = True
        if not self.in_article:
            return
        if tag == 'details' and a.get('class') == 'toc-mobile':
            self.in_mobile = True
        if tag == 'footer':
            self.in_footer = True
        if self.in_mobile or self.in_footer:
            return
        if tag == 'header':
            self.in_header = True
        if tag == 'img':
            self.images.append(a['src'])
        if tag == 'details':
            self.details += 1
        if tag == 'summary':
            self.summaries += 1
        if tag in ['h1', 'h2', 'h3']:
            self.heading = []
        if tag == 'table':
            self.table = []
        if tag == 'tr':
            self.row = []
        if tag in ['td', 'th']:
            self.cell = []
        if tag == 'p' and self.table is None and not self.in_header:
            self.paragraph = []
        if tag == 'pre':
            self.in_code = True
            self.code.append('')

    def handle_endtag(self, tag):
        if self.in_mobile:
            if tag == 'details':
                self.in_mobile = False
            return
        if self.in_footer:
            if tag == 'footer':
                self.in_footer = False
            return
        if tag == 'article':
            self.in_article = False
        if not self.in_article:
            return
        if tag == 'header':
            self.in_header = False
        if tag in ['h1', 'h2', 'h3'] and self.heading is not None:
            self.headings.append(normal(''.join(self.heading)))
            self.heading = None
        if tag == 'p' and self.paragraph is not None:
            self.paragraphs.append(normal(''.join(self.paragraph)))
            self.paragraph = None
        if tag in ['td', 'th'] and self.cell is not None:
            self.row.append(normal(''.join(self.cell)))
            self.cell = None
        if tag == 'tr' and self.row is not None:
            self.table.append(self.row)
            self.row = None
        if tag == 'table' and self.table is not None:
            self.tables.append(self.table)
            self.table = None
        if tag == 'pre':
            self.in_code = False

    def handle_data(self, data):
        if not self.in_article or self.in_mobile or self.in_footer:
            return
        for target in [self.paragraph, self.cell, self.heading]:
            if target is not None:
                target.append(data)
        if self.in_code:
            self.code[-1] += data


def strip_comments(text: str) -> str:
    """Drop HTML comments (caveat markers) outside fenced code; code keeps its text."""
    out, last = [], 0
    for match in FENCE.finditer(text):
        out.append(COMMENT.sub('', text[last:match.start()]))
        out.append(match.group(0))
        last = match.end()
    out.append(COMMENT.sub('', text[last:]))
    return ''.join(out)


EXTERNAL = re.compile(r'(?:\b(?:src|href|data|poster|srcset|action|formaction|background)\s*=\s*["\']?\s*(?:https?:)?//'
                      r'|url\(\s*["\']?\s*(?:https?:)?//|@import)', re.I)


def require(condition, message):
    if not condition:
        raise BuildError(message)


def verify(document, original, images, allow_external=False):
    rendered = Inspect()
    rendered.feed(document)
    require(rendered.headings == original.headings, 'Heading text changed')
    require(rendered.paragraphs == original.paragraphs, 'Paragraph text changed')
    require(rendered.tables == original.tables, 'Table cell changed')
    require(rendered.code == original.code, 'Fenced code changed')
    require(rendered.details == original.details and rendered.summaries == original.summaries, 'Spoiler changed')
    require(len(rendered.ids) == len(set(rendered.ids)), 'Duplicate anchor')
    require(all(link[1:] in rendered.ids for link in rendered.links if link.startswith('#')), 'Broken anchor')
    require(all(link.startswith('#') or link == 'index.html' or (allow_external and re.match(r'(?:https?:)?//|https?:', link))
                for link in rendered.links), 'Unexpected link: only anchors, the index page and allowed external links')
    require(all(r.startswith('data:') for r in rendered.resources), 'External resource')
    embedded = [base64.b64decode(r.split(',', 1)[1], validate=True) for r in rendered.images]
    require([sha(v) for v in embedded] == [sha(p.read_bytes()) for p in images], 'Image changed')
    require(not re.search(r'/Users/|/home/|file:/{2}|<script\b', document), 'Private path or active content')
    body = re.sub(r'<a\b[^>]*>', '<a>', document) if allow_external else document
    require(not EXTERNAL.search(body), 'External resource in the page')
    return dict(headings=len(rendered.headings), paragraphs=len(rendered.paragraphs),
                tables=len(rendered.tables), table_cells=sum(len(row) for table in rendered.tables for row in table),
                images=len(images), code_blocks=len(rendered.code), details=rendered.details,
                local_anchors=len([v for v in rendered.links if v.startswith('#')]), external_resources=0)


def render_article(pandoc, plan_path: Path, number: int, html_vars: dict) -> dict:
    plan = load_plan(plan_path)
    article = plan['_root']
    sections_dir = (article / plan['sections_dir']).resolve()
    paths = section_paths(sections_dir)
    raw = join_sections([strip_comments(p.read_text(encoding='utf-8')) for p in paths]).encode()
    ast = json.loads(run_pandoc(pandoc, ['--from=' + FORMAT, '--to=json'], raw))
    first = ast['blocks'][0]
    if not (first['t'] == 'Header' and first['c'][0] == 1):
        raise GrankiError(f'{article.name}: the first section must start with a first-level heading')
    title = plain(first['c'][2])
    assets = (article / plan['public']['assets_dir']).resolve()
    images = []
    for node in nodes(ast, 'Image'):
        path = (sections_dir / node['c'][2][0]).resolve()
        if not path.is_relative_to(assets) or path.suffix.lower() not in IMAGE_SUFFIXES:
            raise GrankiError(f'{article.name}: image outside {assets.name}/ or of unsupported type: {path.name}')
        images.append(path)
    # Pandoc's --embed-resources downloads remote files and inlines them as data: URIs, so the rendered page
    # would pass the resource check. Raw HTML that loads external content is refused before rendering.
    for node in [*nodes(ast, 'RawBlock'), *nodes(ast, 'RawInline')]:
        fmt, content = node['c']
        if fmt == 'html' and EXTERNAL.search(re.sub(r'<a\b[^>]*>', '<a>', content)):
            raise BuildError(f'{article.name}: external resource in raw HTML: {content.strip()[:80]}')
    baseline = run_pandoc(pandoc, ['--from=json', '--to=html5', '--wrap=none'], json.dumps(ast).encode()).decode()
    original = Inspect()
    original.feed('<article>' + baseline + '</article>')
    ast['blocks'].pop(0)
    ast['meta']['title'] = dict(t='MetaInlines', c=first['c'][2])
    variables = ['--variable=article-number:' + str(number)]
    variables += [f'--variable={k}:{v}' for k, v in html_vars.items() if v]
    result = run_pandoc(pandoc, ['--from=json', '--to=html5', '--standalone', '--embed-resources',
                                 '--resource-path=' + str(sections_dir), '--template=' + str(TEMPLATE),
                                 '--toc', '--toc-depth=3', '--wrap=none', *variables],
                        json.dumps(ast, ensure_ascii=False).encode()).decode()
    result = re.sub(r'<table\b', '<div class="table-scroll" tabindex="0" role="region" '
                    'aria-label="Таблица; прокрутка по горизонтали"><table', result)
    result = result.replace('</table>', '</table></div>')
    # Desktop and mobile tables of contents share destinations but must not duplicate link IDs.
    result = re.sub(r' id="toc-[^"]*"', '', result)
    proof = verify(result, original, images, bool(plan['public'].get('allow_external_links')))
    return {'name': article.name, 'title': title, 'description': plan.get('description'),
            'html': result, 'source_sha256': sha(raw), 'sections': [p.name for p in paths],
            'figures': [dict(file=p.name, sha256=sha(p.read_bytes())) for p in images], 'checks': proof}


def build(pandoc, plan_paths: list[Path], output: Path, settings: dict, first_number: int = 1) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    html_vars = {'brand': settings.get('brand') or 'Granki', 'tagline': settings.get('tagline')}
    pages, cards, entries = {}, [], []
    for number, plan_path in enumerate(plan_paths, first_number):
        page = render_article(pandoc, plan_path, number, html_vars)
        target = page['name'] + '.html'
        pages[target] = page['html']
        summary = f'<p>{html.escape(page["description"])}</p>' if page['description'] else ''
        cards.append(f'<li><p class="kicker">Статья {number}</p><a href="{html.escape(target)}">'
                     f'{html.escape(page["title"])}</a>{summary}</li>')
        entries.append(dict(file=target, title=page['title'], sections=page['sections'],
                            source_sha256=page['source_sha256'], html_sha256=sha(page['html'].encode()),
                            bytes=len(page['html'].encode()), figures=page['figures'], checks=page['checks']))
    css = TEMPLATE.read_text(encoding='utf-8').split('<style>', 1)[1].split('$if(highlighting-css)$', 1)[0]
    kicker = settings.get('index_kicker')
    index = ('<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8">'
             '<meta name="viewport" content="width=device-width, initial-scale=1">'
             f'<title>{html.escape(settings.get("index_title") or "Статьи")} — статьи</title><style>' + css +
             '</style></head><body><main class="index">' +
             (f'<p class="kicker">{html.escape(kicker)}</p>' if kicker else '') +
             f'<h1>{html.escape(settings.get("index_title") or "Статьи")}</h1>'
             '<ol class="article-list">' + ''.join(cards) + '</ol></main></body></html>\n')
    pages['index.html'] = index
    previous = output / 'manifest.json'
    removed = []
    if previous.is_file():  # pages of articles no longer in the series
        try:
            old = [a['file'] for a in json.loads(previous.read_text(encoding='utf-8')).get('articles', [])]
        except (ValueError, KeyError, TypeError):
            old = []
        for name in old:
            if name not in pages and (output / name).is_file():
                (output / name).unlink()
                removed.append(name)
    for filename, document in pages.items():
        (output / filename).write_text(document, encoding='utf-8')
    version = subprocess.check_output([pandoc, '--version'], text=True).splitlines()[0]
    manifest = dict(status='passed', pandoc=version, template_sha256=sha(TEMPLATE.read_bytes()),
                    articles=entries, index=dict(file='index.html', sha256=sha(index.encode())))
    (output / 'manifest.json').write_text(dump_json(manifest), encoding='utf-8')
    return {'status': 'passed', 'output': str(output), 'articles': len(entries), 'removed_pages': removed,
            'images': sum(e['checks']['images'] for e in entries),
            'tables': sum(e['checks']['tables'] for e in entries),
            'table_cells': sum(e['checks']['table_cells'] for e in entries)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--series', type=Path, help='series-plan.md; builds every article and an index page')
    parser.add_argument('--plan', type=Path, help='one article plan.md')
    parser.add_argument('--output', type=Path, required=True, help='output folder')
    parser.add_argument('--pandoc', help='path to the pandoc binary')
    args = parser.parse_args(argv)
    try:
        if bool(args.plan) == bool(args.series):
            raise GrankiError('Pass exactly one of --plan or --series')
        pandoc = find_pandoc(args.pandoc)
        if args.series:
            series = load_series(args.series)
            root = args.series.parent.resolve()
            plans = [root / folder / 'plan.md' for folder in series['articles']
                     if has_sections(root / folder / 'plan.md')]
            if not plans:
                raise GrankiError('No article of the series has a plan and sections yet')
            settings = series.get('html', {})
            settings.setdefault('index_title', series.get('title'))
        else:
            plans, settings, number = [args.plan.resolve()], {}, 1
            context = series_of(args.plan)
            if context:  # same brand, tagline and article number as in the series build
                series_path, series = context
                settings = dict(series.get('html', {}))
                settings.setdefault('index_title', series.get('title'))
                number = series['articles'].index(args.plan.resolve().parent.name) + 1
            report = build(pandoc, plans, args.output.resolve(), settings, first_number=number)
            sys.stdout.write(dump_json(report))
            return 0
        report = build(pandoc, plans, args.output.resolve(), settings)
    except BuildError as error:
        sys.stdout.write(dump_json({'status': 'failed', 'reason': str(error)}))
        return 1
    except (GrankiError, OSError, KeyError, subprocess.CalledProcessError) as error:
        sys.stdout.write(dump_json({'status': 'error', 'reason': str(error)}))
        return 2
    except Exception as error:
        sys.stdout.write(dump_json({'status': 'error', 'reason': f'{type(error).__name__}: {error}'}))
        return 2
    sys.stdout.write(dump_json(report))
    return 0


if __name__ == '__main__':
    sys.exit(main())
