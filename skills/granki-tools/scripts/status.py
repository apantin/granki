#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml>=6"]
# ///
"""Show the state of a series: articles, sections, changes, reviews and findings.

For every section the report compares the current text hash with the hash
recorded when the section was accepted. A review file (reviews/*.md with
frontmatter scope, target, reviewed_sha, findings) is:
  current    the reviewed text has not changed;
  processed  the text changed, and no finding of the review is still open
             (each is applied, rejected or deferred) — the review is used up;
  stale      the text changed while findings of the review are open, or the
             review recorded no findings at all.
Review scopes: section, article, plan (the article plan body), series (all
articles), series-plan (the series plan body). Pending findings (open or
deferred) come from each journal.md. An article listed in the series without
a plan.md yet is shown as planned.

Prints JSON, or a Markdown table with --format md. Exit code 0, or 2 on
configuration errors.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from granki_core import (GrankiError, SECTION_NAME, dump_json, join_sections, load_plan,  # noqa: E402
                         load_series, section_paths, sha256_text, split_frontmatter)
from journal import describe as journal_state, read as read_journal, state, table  # noqa: E402

DECIDED = ('applied', 'rejected')


def body_sha(path: Path) -> str | None:
    """Hash of a plan's body: the part written for the author, without frontmatter."""
    if not path.is_file():
        return None
    return sha256_text(split_frontmatter(path.read_text(encoding='utf-8'))[1])


def decisions(journal: Path) -> dict:
    if not journal.is_file():
        return {}
    try:
        return {r.get('ID'): state(r) for _, r in table(read_journal(journal))[2]}
    except GrankiError:
        return {}


def reviews(folder: Path, current_for, journal: Path) -> list[dict]:
    decided = decisions(journal)
    out = []
    for path in sorted((folder / 'reviews').glob('*.md')) if (folder / 'reviews').is_dir() else []:
        meta, _ = split_frontmatter(path.read_text(encoding='utf-8'))
        if not meta.get('scope'):
            continue
        scope = str(meta['scope']).strip().lower()
        ids = [str(i) for i in (meta.get('findings') or [])]
        current = current_for(scope, meta.get('target'))
        reviewed = meta.get('reviewed_sha')
        if reviewed and current and reviewed == current:
            review_state = 'current'
        elif ids and reviewed and all(decided.get(i) in DECIDED + ('deferred',) for i in ids):
            review_state = 'processed'
        else:
            review_state = 'stale'
        out.append({'file': path.name, 'scope': scope, 'target': meta.get('target'), 'lens': meta.get('lens'),
                    'date': str(meta.get('date', '')), 'reviewed_sha': reviewed, 'findings': ids,
                    'state': review_state, 'stale': review_state == 'stale'})
    return out


def article_state(plan_path: Path, folder: str) -> dict:
    if not plan_path.is_file():
        return {'article': folder, 'title': None, 'status': 'planned', 'has_plan': False, 'version': 1,
                'published_versions': 0, 'sha256': None, 'sections': [], 'reviews': [],
                'sections_accepted': 0, 'sections_total': 0, 'all_sections_accepted': False,
                'pending_findings': 0, 'critical_pending': 0}
    plan = load_plan(plan_path)
    article = plan['_root']
    folder_path = (article / plan['sections_dir']).resolve()
    has_files = folder_path.is_dir() and any(SECTION_NAME.fullmatch(p.name) for p in folder_path.glob('*.md'))
    paths = section_paths(folder_path) if has_files else []
    texts = {p.name: p.read_text(encoding='utf-8') for p in paths}
    shas = {n: sha256_text(t) for n, t in texts.items()}
    article_sha = sha256_text(join_sections(list(texts.values()))) if texts else None
    planned = {e['file']: e for e in plan['sections'] if 'file' in e}
    sections = []
    for name in list(planned) + [n for n in shas if n not in planned]:
        entry = planned.get(name, {})
        accepted = entry.get('accepted_sha')
        status = entry.get('status', 'planned' if name in planned else 'unplanned')
        problem = None
        if status == 'accepted' and not accepted:
            problem = 'accepted without accepted_sha: accept it again with plan.py'
        elif name not in shas and status != 'planned':
            problem = 'file is missing'
        sections.append({'file': name, 'status': status, 'exists': name in shas, 'sha256': shas.get(name),
                         'accepted_sha': accepted, 'problem': problem,
                         'modified_since_accepted': bool(accepted) and accepted != shas.get(name)})

    def current_for(scope, target):
        if scope == 'article':
            return article_sha
        if scope == 'plan':
            return body_sha(plan_path)
        return shas.get(target)

    workspace = plan['_workspace']
    journal_path = workspace / 'journal.md'
    review_list = reviews(workspace, current_for, journal_path)
    accepted = [s for s in sections if s['status'] == 'accepted' and s['accepted_sha'] and s['exists']
                and not s['modified_since_accepted']]
    journal = journal_state(journal_path, plan_path, False)
    return {'article': folder, 'title': plan.get('title'), 'status': plan['status'], 'has_plan': True,
            'version': plan.get('version', 1), 'published_versions': len(plan['published']),
            'sha256': article_sha, 'plan_sha256': body_sha(plan_path), 'sections': sections, 'reviews': review_list,
            'sections_accepted': len(accepted), 'sections_total': len(sections),
            'all_sections_accepted': bool(sections) and len(accepted) == len(sections),
            'pending_findings': journal['pending'], 'critical_pending': journal['critical_pending']}


def series_state(series_path: Path) -> dict:
    series = load_series(series_path)
    root = series_path.parent.resolve()
    articles = [article_state(root / folder / 'plan.md', folder) for folder in series['articles']]
    series_sha = sha256_text('\n'.join(f'{a["article"]}:{a["sha256"]}' for a in articles))

    def current_for(scope, target):
        return body_sha(series_path) if scope == 'series-plan' else series_sha

    review_list = reviews(root, current_for, root / 'journal.md')
    journal = journal_state(root / 'journal.md', None, False)
    return {'series': root.name, 'title': series.get('title'), 'status': series.get('status'),
            'sha256': series_sha, 'series_plan_sha256': body_sha(series_path), 'articles': articles, 'reviews': review_list,
            'pending_findings': journal['pending'], 'critical_pending': journal['critical_pending']}


def markdown(state_: dict) -> str:
    lines = [f'# {state_.get("title") or state_["series"]}', '',
             f'План серии: {state_.get("status") or "—"}. Нерешённые находки серии: {state_["pending_findings"]}'
             f' (критичных {state_["critical_pending"]}).', '',
             '| Статья | Статус | Разделы | Изменены после приёмки | Устаревшие ревью | Нерешённые находки |',
             '|---|---|---|---|---|---|']
    for a in state_['articles']:
        if not a['has_plan']:
            lines.append(f'| {a["article"]} | planned, плана нет | — | — | — | — |')
            continue
        modified = [s['file'] for s in a['sections'] if s['modified_since_accepted']]
        stale = [r['file'] for r in a['reviews'] if r['stale']]
        pending = f'{a["pending_findings"]} (критичных {a["critical_pending"]})' if a['pending_findings'] else '—'
        counts = {}
        for s in a['sections']:
            key = s['status'] + (' после правки' if s['modified_since_accepted'] else '')
            counts[key] = counts.get(key, 0) + 1
        by_status = ', '.join(f'{k} {v}' for k, v in counts.items())
        lines.append(f'| {a["article"]} | {a["status"]} v{a["version"]} | принято {a["sections_accepted"]}/{a["sections_total"]}'
                     f'{"; " + by_status if by_status else ""} '
                     f'| {", ".join(modified) or "—"} | {", ".join(stale) or "—"} | {pending} |')
    problems = [f'{a["article"]}/{s["file"]}: {s["problem"]}' for a in state_['articles'] for s in a['sections'] if s['problem']]
    stale = [r['file'] for r in state_['reviews'] if r['stale']]
    lines += ['', f'Ревью уровня серии (план серии и серия целиком): {len(state_["reviews"])}, устаревших: {len(stale)}'
              + (f' ({", ".join(stale)})' if stale else '')]
    if problems:
        lines += ['', 'Требует внимания:'] + [f'- {p}' for p in problems]
    return '\n'.join(lines) + '\n'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--series', type=Path, required=True, help='series-plan.md')
    parser.add_argument('--format', choices=['json', 'md'], default='json')
    args = parser.parse_args(argv)
    try:
        result = series_state(args.series)
    except (GrankiError, OSError, KeyError) as error:
        sys.stdout.write(dump_json({'status': 'error', 'reason': str(error)}))
        return 2
    except Exception as error:
        sys.stdout.write(dump_json({'status': 'error', 'reason': f'{type(error).__name__}: {error}'}))
        return 2
    sys.stdout.write(markdown(result) if args.format == 'md' else dump_json(result))
    return 0


if __name__ == '__main__':
    sys.exit(main())
