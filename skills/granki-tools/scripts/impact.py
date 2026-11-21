#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml>=6"]
# ///
"""Find which sections a series-level change touches and what may be done.

A change is described by claim IDs (--claim), text patterns (--term) and
explicit sections (--section ARTICLE/FILE). A section is affected when its
plan entry lists the claim ("declared"), when its prose contains a rendered
value of the claim ("value match", check by reading), or when it matches a
term. Options follow the article status: unpublished articles are reworked;
for a published article the author chooses a new version, a recorded
divergence or no change.

Read-only: prints a JSON matrix and changes no files. Exit code 0, or 2 on
configuration errors.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from granki_core import (COMMENT, GrankiError, dump_json, has_sections, load_plan, load_series,  # noqa: E402
                         read_csv, render, section_paths, strip_code)

PUBLISHED_OPTIONS = ['new-version', 'record-divergence', 'no-change']


def impact(series_path: Path, claim_ids: list[str], terms: list[str], explicit: list[str]) -> dict:
    series = load_series(series_path)
    root = series_path.parent.resolve()
    articles, known_claims = [], set()
    planned = [f for f in series['articles']
               if (root / f / 'plan.md').is_file() and has_sections(load_plan(root / f / 'plan.md'))]
    for folder in planned:
        plan = load_plan(root / folder / 'plan.md')
        for name in plan['claims']:
            known_claims |= {r['ID'] for r in read_csv(plan['_root'] / name)}
    unknown = sorted(set(claim_ids) - known_claims)
    if unknown:
        raise GrankiError('Unknown claim IDs: ' + ', '.join(unknown))
    for entry in explicit:
        folder, _, name = entry.partition('/')
        if folder not in planned or not name:
            raise GrankiError(f'--section must be ARTICLE/FILE with an article from the series: {entry!r}')
    for folder in planned:
        plan_path = root / folder / 'plan.md'
        plan = load_plan(plan_path)
        article = plan['_root']
        claims = {}
        for name in plan['claims']:
            for row in read_csv(article / name):
                if row['ID'] in claim_ids:
                    claims[row['ID']] = row['value']
        declared = {e['file']: set(e.get('claims', [])) for e in plan['sections'] if 'file' in e}
        numbers = plan['numbers']
        affected = []
        paths = section_paths((article / plan['sections_dir']).resolve())
        absent = [e for e in explicit if e.startswith(folder + '/') and e.split('/', 1)[1] not in {p.name for p in paths}]
        if absent:
            raise GrankiError('Sections not found: ' + ', '.join(absent))
        for path in paths:
            raw = path.read_text(encoding='utf-8')
            text = COMMENT.sub('', strip_code(raw))  # tables included: a value may appear only there
            reasons = []
            for cid in claim_ids:
                if cid in declared.get(path.name, set()):
                    reasons.append({'claim': cid, 'how': 'declared'})
                elif cid in claims:
                    forms = render(claims[cid], numbers['renderers'], numbers['decimal'])
                    if any(re.search(r'(?<![\w,.])' + re.escape(f) + r'(?![\w])', text) for f in forms):
                        reasons.append({'claim': cid, 'how': 'value match'})
            for term in terms:
                if re.search(term, text, re.I):
                    reasons.append({'term': term, 'how': 'term'})
            if f'{folder}/{path.name}' in explicit:
                reasons.append({'how': 'explicit'})
            if reasons:
                affected.append({'section': path.name, 'reasons': reasons})
        published = plan['status'] in ('published', 'revising') or bool(plan['published'])
        articles.append({'article': folder, 'status': plan['status'], 'published': published,
                         'affected_sections': affected,
                         'options': (PUBLISHED_OPTIONS if published else ['rework']) if affected else []})
    return {'status': 'passed', 'series': root.name, 'change': {'claims': claim_ids, 'terms': terms, 'sections': explicit},
            'articles': articles, 'affected_total': sum(len(a['affected_sections']) for a in articles)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--series', type=Path, required=True, help='series-plan.md')
    parser.add_argument('--claim', action='append', default=[], help='claim ID; repeatable')
    parser.add_argument('--term', action='append', default=[], help='regular expression; repeatable')
    parser.add_argument('--section', action='append', default=[], help='ARTICLE/FILE; repeatable')
    args = parser.parse_args(argv)
    try:
        if not (args.claim or args.term or args.section):
            raise GrankiError('Describe the change with --claim, --term or --section')
        report = impact(args.series, args.claim, args.term, args.section)
    except (GrankiError, OSError, KeyError, re.error) as error:
        sys.stdout.write(dump_json({'status': 'error', 'reason': str(error)}))
        return 2
    except Exception as error:
        sys.stdout.write(dump_json({'status': 'error', 'reason': f'{type(error).__name__}: {error}'}))
        return 2
    sys.stdout.write(dump_json(report))
    return 0


if __name__ == '__main__':
    sys.exit(main())
