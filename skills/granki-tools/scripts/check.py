#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml>=6"]
# ///
"""Check one section, one article or a whole series against its plan.

Checks: plan and section files agree, prose length, every decimal number in
prose traces to a claim, claims still equal their source cells, required
caveats are present, links resolve, forbidden public content is absent,
figure files match their manifest, published sections are unchanged.

Scope:
  --plan PLAN                    the whole article
  --plan PLAN --section FILE     one section
  --series SERIES_PLAN           every article with sections, plus cross-article
                                 claims; articles without a plan or without
                                 section files are listed in not_planned

Prints a JSON report. Exit code 0 when every check passed, 1 when a check
failed, 2 on configuration errors.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from granki_core import (without_dates, GrankiError, bare_markers, caveat_markers, decimal_tokens, dump_json,  # noqa: E402
                         has_sections, integer_tokens, join_sections, link_targets, load_plan, load_series, prose,
                         read_csv, render, section_paths, series_of, sha256_file, sha256_text)
from claims import verify_rows  # noqa: E402


IMAGE_SUFFIXES = ('.png', '.jpg', '.jpeg', '.svg', '.webp')


def result(name, ok, warn=False, **details):
    """A check outcome; warn=True turns a failure into a warning that does not fail the run."""
    return {'name': name, 'status': 'passed' if ok else ('warning' if warn else 'failed'), **details}


def load_claims(plan, article):
    rows = []
    for name in plan['claims']:
        for row in read_csv(article / name):
            row['_file'] = name
            rows.append(row)
    return rows


def check_numbers(texts, claims, plan):
    numbers = plan['numbers']
    allowed = set(str(a) for a in numbers.get('allow', []))
    for claim in claims:
        allowed |= render(claim['value'], numbers['renderers'], numbers['decimal'])
    integers = bool(numbers.get('integers'))
    if integers:
        for claim in claims:
            allowed |= render(claim['value'], ['fixed:0', 'percent:0'], numbers['decimal'])
    untraced, total = [], 0
    for name, text in texts:
        body = prose(text)
        tokens = decimal_tokens(body, numbers['decimal'])
        if integers:
            tokens += integer_tokens(body if numbers.get('dates') else without_dates(body), numbers['decimal'])
        for token in tokens:
            total += 1
            if token not in allowed:
                untraced.append({'section': name, 'number': token})
    return result('numbers', not untraced, occurrences=total, integers=integers, untraced=untraced)


def check_caveats(texts, plan, scope_files):
    required = {}
    if scope_files is None:
        for cid in plan['required_caveats']:
            required[cid] = None
    for entry in plan['sections']:
        if scope_files is None or entry.get('file') in scope_files:
            for cid in entry.get('caveats', []):
                required[cid] = entry.get('file')
    joined = '\n\n'.join(t for _, t in texts)
    markers = set(caveat_markers(joined))
    bare = sorted(set(bare_markers(joined)))
    found, missing = {}, []
    for cid, where in sorted(required.items()):
        scope_text = joined if where is None else next((t for n, t in texts if n == where), '')
        if cid in markers and (where is None or cid in caveat_markers(scope_text)):
            found[cid] = 'marker'
            continue
        pattern = (plan['caveats'].get(cid) or {}).get('pattern')
        if pattern and re.search(pattern, scope_text, re.I):
            found[cid] = 'pattern'
            continue
        missing.append({'caveat': cid, 'section': where})
    unknown = sorted(c for c in markers | set(bare) if c not in plan['caveats'])
    return result('caveats', not missing and not unknown and not bare, found=found, missing=missing,
                  unknown_markers=unknown, markers_without_text=bare)


def check_links(texts, sections_dir, article, plan):
    """Same rule as build_html: anchors, and images inside the assets folder; external links only if allowed."""
    assets = (article / plan['public']['assets_dir']).resolve()
    allow_external = plan['public']['allow_external_links']
    bad, targets = [], []
    for name, text in texts:
        for target in link_targets(text):
            targets.append(target)
            if target.startswith('#'):
                continue
            if re.match(r'[a-z][a-z0-9+.-]*:', target, re.I) or target.startswith('//'):
                if not allow_external:
                    bad.append({'section': name, 'link': target, 'reason': 'external link'})
                continue
            path = (sections_dir / target.split('#', 1)[0]).resolve()
            if not path.exists():
                bad.append({'section': name, 'link': target, 'reason': 'missing file'})
            elif path.suffix.lower() not in IMAGE_SUFFIXES:
                bad.append({'section': name, 'link': target, 'reason': 'local link to a non-image; the HTML page cannot carry it'})
            elif not path.is_relative_to(assets):
                bad.append({'section': name, 'link': target, 'reason': 'image outside assets'})
    return result('links', not bad, links=len(targets), problems=bad)


def check_forbidden(texts, plan):
    hits = []
    for pattern in plan['public']['forbidden']:
        for name, text in texts:
            match = re.search(pattern, text, re.I)
            if match:
                hits.append({'section': name, 'pattern': pattern, 'match': match.group()})
    return result('public', not hits, patterns=len(plan['public']['forbidden']), hits=hits)


def check_figures(article, plan):
    manifests = sorted(article.glob(plan['figures']['manifest']))
    drift, checked = [], 0
    for manifest in manifests:
        data = json.loads(manifest.read_text(encoding='utf-8'))
        items = data.get('images', []) if isinstance(data, dict) else data
        for item in items:
            path = manifest.parent / item['file']
            checked += 1
            if not path.is_file() or sha256_file(path) != item['sha256']:
                drift.append(item['file'])
    return result('figures', not drift, manifests=len(manifests), figures=checked, drift=drift)


def check_lock(plan, shas, scope_files=None):
    """A published article must match the section hashes of its last published version."""
    if plan['status'] != 'published' or not plan['published']:
        return result('published-lock', True, applies=False)
    recorded = plan['published'][-1].get('sections', {})
    files = set(recorded) | set(shas) if scope_files is None else set(scope_files)
    changed = sorted(f for f in files if recorded.get(f) != shas.get(f))
    return result('published-lock', not changed, applies=True, changed=changed,
                  hint='switch the article to "revising" before editing a published version' if changed else None)


def check_plan_sections(plan, names, claim_ids):
    planned = [e.get('file') for e in plan['sections']]
    if not planned:
        return result('plan-sections', True, planned=0)
    # a planned section is not written yet: that is the plan stage, not a lost file
    missing = [e.get('file') for e in plan['sections'] if e.get('file') not in names and e.get('status') != 'planned']
    not_written = [e.get('file') for e in plan['sections'] if e.get('file') not in names and e.get('status') == 'planned']
    unplanned = [f for f in names if f not in planned]
    unknown_claims = sorted({c for e in plan['sections'] for c in e.get('claims', []) if c not in claim_ids})
    unknown_caveats = sorted({c for e in plan['sections'] for c in e.get('caveats', []) if c not in plan['caveats']})
    ok = not (missing or unplanned or unknown_claims or unknown_caveats)
    return result('plan-sections', ok, planned=len(planned), not_written=not_written, missing_files=missing, unplanned_files=unplanned,
                  unknown_claims=unknown_claims, unknown_caveats=unknown_caveats)


def check_article(plan_path: Path, article_dir: Path | None = None, section: str | None = None) -> dict:
    plan = load_plan(plan_path)
    article = (article_dir or plan['_root']).resolve()
    sections_dir = (article / plan['sections_dir']).resolve()
    # before the first section is written the folder may not exist; the plan can still be checked
    paths = section_paths(sections_dir) if sections_dir.is_dir() or section is not None else []
    names = [p.name for p in paths]
    if section is not None and section not in names:
        raise GrankiError(f'Section {section} not found in {sections_dir}')
    all_texts = [(p.name, p.read_text(encoding='utf-8')) for p in paths]
    texts = all_texts if section is None else [t for t in all_texts if t[0] == section]
    text = join_sections([t for _, t in all_texts])
    shas = {n: sha256_text(t) for n, t in all_texts}
    claims = load_claims(plan, article)
    checks = []
    if section is None:
        checks.append(check_plan_sections(plan, names, {c.get('ID') for c in claims}))
        length = len(prose(text))
        bounds = plan.get('length') or {}
        ok = bounds.get('min', 0) <= length <= bounds.get('max', float('inf'))
        checks.append(result('length', ok, warn=not bounds.get('strict', False), characters=length,
                             min=bounds.get('min'), max=bounds.get('max'), strict=bool(bounds.get('strict', False))))
    checks.append(check_numbers(texts, claims, plan))
    if plan['claims']:
        dirs = [(article / d).resolve() for d in plan['data_dirs']]
        verified = verify_rows(claims, dirs)
        # In a published article, drift of a claim the series accepted as a divergence is reported, not failed.
        context = series_of(plan_path)
        known = set(context[1]['known_divergences']) if context else set()
        accepted = []
        if plan['status'] in ('published',) and known:
            accepted = [d for d in verified['drift'] if d['id'] in known]
            verified['drift'] = [d for d in verified['drift'] if d['id'] not in known]
        ok = not any(verified[k] for k in ('drift', 'ambiguous', 'missing', 'invalid', 'duplicates'))
        checks.append(result('claims', ok, claims=verified['claims'],
                             drift=verified['drift'], ambiguous=verified['ambiguous'], missing=verified['missing'],
                             invalid=verified['invalid'], duplicates=verified['duplicates'],
                             unverifiable=verified['unverifiable'], accepted_divergences=accepted))
    checks.append(check_caveats(texts, plan, None if section is None else {section}))
    checks.append(check_links(texts, sections_dir, article, plan))
    checks.append(check_forbidden(texts, plan))
    if section is None:
        checks.append(check_figures(article, plan))
    checks.append(check_lock(plan, shas, None if section is None else {section}))
    failed = [c['name'] for c in checks if c['status'] == 'failed']
    warnings = [c['name'] for c in checks if c['status'] == 'warning']
    return {'status': 'failed' if failed else 'passed', 'warnings': warnings,
            'scope': 'section' if section else 'article',
            'article': str(article), 'title': plan.get('title'), 'article_status': plan['status'],
            'section': section, 'sha256': shas[section] if section else sha256_text(text),
            'sections': len(names), 'failed': failed, 'checks': checks}


def check_series(series_path: Path) -> dict:
    series = load_series(series_path)
    root = series_path.parent.resolve()
    articles, values = [], {}
    not_planned = []
    for folder in series['articles']:
        plan_path = root / folder / 'plan.md'
        if not plan_path.is_file() or not has_sections(load_plan(plan_path)):
            not_planned.append(folder)
            continue
        report = check_article(plan_path)
        articles.append(report)
        plan = load_plan(plan_path)
        for claim in load_claims(plan, plan['_root']):
            values.setdefault(claim['ID'], {})[folder] = claim['value']
    known = set(series['known_divergences'])
    conflicts = [{'id': cid, 'values': v} for cid, v in sorted(values.items())
                 if len(set(v.values())) > 1 and cid not in known]
    cross = result('series-claims', not conflicts, shared_ids=sum(1 for v in values.values() if len(v) > 1),
                   conflicts=conflicts, known_divergences=sorted(known))
    failed = [a['article'] for a in articles if a['status'] == 'failed']
    status = 'failed' if failed or cross['status'] == 'failed' else 'passed'
    return {'status': status, 'scope': 'series', 'series': str(root), 'title': series.get('title'),
            'failed_articles': failed, 'not_planned': not_planned, 'checks': [cross],
            'articles': [{'article': a['article'], 'status': a['status'], 'failed': a['failed']} for a in articles],
            'article_reports': articles}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--plan', type=Path, help='article plan.md')
    parser.add_argument('--article-dir', type=Path, help='article folder (default: folder of the plan)')
    parser.add_argument('--section', help='check one section file, for example 03-results.md')
    parser.add_argument('--series', type=Path, help='series-plan.md; checks every article')
    parser.add_argument('--report', type=Path, help='also write the JSON report to this file')
    args = parser.parse_args(argv)
    try:
        if bool(args.plan) == bool(args.series):
            raise GrankiError('Pass exactly one of --plan or --series')
        report = check_series(args.series) if args.series else check_article(args.plan, args.article_dir, args.section)
    except (GrankiError, OSError, KeyError, ValueError) as error:
        sys.stdout.write(dump_json({'status': 'error', 'reason': str(error)}))
        return 2
    except Exception as error:  # unexpected input must not look like a failed check
        sys.stdout.write(dump_json({'status': 'error', 'reason': f'{type(error).__name__}: {error}'}))
        return 2
    output = dump_json(report)
    if args.report:
        args.report.write_text(output, encoding='utf-8')
    sys.stdout.write(output)
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    sys.exit(main())
