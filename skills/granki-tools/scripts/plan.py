#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml>=6"]
# ///
"""Change the state recorded in an article's plan.md and log it to journal.md.

  status   --plan P --set STATUS          move the article along its lifecycle
  section  --plan P --file F --set STATUS set a section's status; "accepted"
                                          records the hash of the current text and
                                          is refused while the text has
                                          [нужно от автора: …], or the journal
                                          has open findings or critical deferred
                                          ones for the section
  entry    --plan P --file F [--caveats C1,C2] [--claims R1,R2] [--after G] [--set STATUS]
                                          add a section to the plan (status planned,
                                          or --set, e.g. drafted when restoring a
                                          plan for an existing text) or update its
                                          caveats and claims
  series   --series S --set STATUS        status of the series plan: draft,
                                          approved, writing, done
  sync     --plan P                       add section files missing from the plan
  publish  --plan P [--url U] [--date D] [--html F]
                                          ready -> published, records version,
                                          section hashes, the git commit and the
                                          hash of the built HTML page F
  revise   --plan P                       published -> revising, version + 1

Only the frontmatter is rewritten (YAML comments in it are not kept); the
plan body written for the author stays as it is. Article transitions follow
the lifecycle; --force allows any other move and logs it as forced.
Prints JSON. Exit code 0, or 2 on errors and refused transitions.
"""
from __future__ import annotations

import argparse
import datetime
import re
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from granki_core import (series_of, ARTICLE_STATUSES, SECTION_NAME, SECTION_STATUSES, GrankiError, atomic_write,  # noqa: E402
                         dump_json, load_plan, load_series, section_paths, sha256_text, split_frontmatter)
from journal import log_event, read as read_journal, state, table  # noqa: E402

TRANSITIONS = {
    'planned': {'plan-draft'},
    'plan-draft': {'plan-approved', 'planned'},
    'plan-approved': {'writing', 'plan-draft'},
    'writing': {'article-review', 'plan-draft'},
    'article-review': {'ready', 'writing'},
    'ready': {'published', 'article-review', 'writing'},
    'published': {'revising'},
    'revising': {'article-review', 'ready', 'writing'},
}


def load(path: Path) -> tuple[dict, str, dict]:
    """Raw frontmatter, body and the validated plan."""
    meta, body = split_frontmatter(path.read_text(encoding='utf-8'))
    return meta, body, load_plan(path)


def save(path: Path, meta: dict, body: str) -> None:
    text = '---\n' + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False, width=1000) + '---\n' + body
    atomic_write(path, text)


def log(plan: dict, actor: str, action: str, target: str | None = None) -> None:
    log_event(plan['_workspace'] / 'journal.md', actor, action, target)


def sections_dir(plan: dict) -> Path:
    return plan['_root'] / plan['sections_dir']


def set_status(path: Path, status: str, actor: str, force: bool) -> dict:
    meta, body, plan = load(path)
    current = plan['status']
    if status not in ARTICLE_STATUSES:
        raise GrankiError(f'Unknown article status {status!r}')
    if status in ('published', 'revising') and not force:
        raise GrankiError(f'Use the "{"publish" if status == "published" else "revise"}" command for {status}')
    allowed = TRANSITIONS.get(current, set())
    if status not in allowed and not force:
        raise GrankiError(f'Transition {current} -> {status} is not in the lifecycle; allowed: {", ".join(sorted(allowed))}')
    if status == 'plan-approved' and not force:
        context = series_of(path)
        if context and context[1].get('status') == 'draft':
            raise GrankiError('The series plan is still a draft: approve it first (plan.py series --set approved), '
                              'or pass --force when the author approves the article plan anyway')
    if status == 'article-review' and not force:
        pending = []
        for e in meta.get('sections', []):
            file = sections_dir(plan) / e.get('file', '')
            text_sha = sha256_text(file.read_text(encoding='utf-8')) if file.is_file() else None
            if e.get('status') != 'accepted' or not e.get('accepted_sha') or e.get('accepted_sha') != text_sha:
                pending.append(e.get('file'))
        if pending:
            raise GrankiError('Article review needs every section accepted and unchanged since; not yet: ' + ', '.join(pending))
    meta['status'] = status
    save(path, meta, body)
    log(plan, actor, f'статус статьи: {current} → {status}' + (' (принудительно)' if status not in allowed else ''))
    return {'status': 'passed', 'plan': str(path), 'from': current, 'to': status}


SERIES_STATUSES = ('draft', 'approved', 'writing', 'done')
AUTHOR_GAP = re.compile(r'\[нужно от автора', re.I)


def blocking_for(plan: dict, name: str) -> tuple[list[str], list[str]]:
    """(blocking, deferred) finding IDs for a section: open findings and critical deferred
    ones block acceptance; ordinary deferred ones do not, they are only reported."""
    journal_path = plan['_workspace'] / 'journal.md'
    if not journal_path.is_file():
        return [], []
    blocking, deferred = [], []
    for _, r in table(read_journal(journal_path))[2]:
        if r.get('Раздел') != name:
            continue
        status = state(r)
        if status == 'open' or (status == 'deferred' and (r.get('Важность') or '').lower() == 'критично'):
            blocking.append(r.get('ID'))
        elif status == 'deferred':
            deferred.append(r.get('ID'))
    return blocking, deferred


def set_section(path: Path, name: str, status: str, actor: str, force: bool = False) -> dict:
    if status not in SECTION_STATUSES:
        raise GrankiError(f'Unknown section status {status!r}')
    meta, body, plan = load(path)
    entries = meta.setdefault('sections', [])
    entry = next((e for e in entries if e.get('file') == name), None)
    file = sections_dir(plan) / name
    if entry is None:
        raise GrankiError(f'{name} is not in the plan; add it to the plan first (or run sync)')
    if status in ('drafted', 'agent-reviewed', 'accepted') and not file.is_file():
        raise GrankiError(f'Section file not found: {file}')
    before = entry.get('status', 'planned')
    forced = ''
    if status == 'accepted':
        blockers = []
        if AUTHOR_GAP.search(file.read_text(encoding='utf-8')):
            blockers.append('the text still has [нужно от автора: …]')
        pending, deferred = blocking_for(plan, name)
        if pending:
            blockers.append('undecided or critical findings ' + ', '.join(pending))
        if blockers and not force:
            raise GrankiError(f'{name} cannot be accepted: ' + '; '.join(blockers) +
                              '. Resolve them, or pass --force when the author accepts anyway')
        if blockers:
            forced = ' (принят при: ' + '; '.join(blockers) + ')'
        if deferred:
            forced += ' (отложены: ' + ', '.join(deferred) + ')'
    entry['status'] = status
    if status == 'accepted':
        entry['accepted_sha'] = sha256_text(file.read_text(encoding='utf-8'))
    save(path, meta, body)
    log(plan, actor, f'раздел: {before} → {status}{forced}', name)
    return {'status': 'passed', 'plan': str(path), 'section': name, 'from': before, 'to': status,
            'accepted_sha': entry.get('accepted_sha') if status == 'accepted' else None}


def upsert_entry(path: Path, name: str, caveats: list[str] | None, claims: list[str] | None,
                 after: str | None, actor: str, status: str | None = None) -> dict:
    meta, body, plan = load(path)
    if not SECTION_NAME.fullmatch(name):
        raise GrankiError(f'Section file must be NN-name.md, got {name!r}')
    entries = meta.setdefault('sections', [])
    entry = next((e for e in entries if e.get('file') == name), None)
    created = entry is None
    if status and status not in SECTION_STATUSES:
        raise GrankiError(f'Unknown section status {status!r}')
    if created:
        entry = {'file': name, 'status': status or 'planned'}
        index = next((i + 1 for i, e in enumerate(entries) if e.get('file') == after), len(entries)) if after else len(entries)
        entries.insert(index, entry)
    unknown = [c for c in caveats or [] if c not in plan['caveats']]
    if unknown:
        raise GrankiError('Unknown caveats (define them in caveats: first): ' + ', '.join(unknown))
    if caveats is not None:
        entry['caveats'] = caveats
    if claims is not None:
        entry['claims'] = claims
    save(path, meta, body)
    log(plan, actor, ('в план добавлен раздел' if created else 'обновлена запись раздела')
        + (f'; оговорки: {", ".join(caveats)}' if caveats else '') + (f'; опоры: {", ".join(claims)}' if claims else ''), name)
    return {'status': 'passed', 'plan': str(path), 'section': name, 'created': created}


SERIES_TRANSITIONS = {None: {'draft', 'approved'}, 'draft': {'approved'}, 'approved': {'writing', 'draft'},
                      'writing': {'done', 'draft'}, 'done': {'writing'}}


def set_series(path: Path, status: str, actor: str, force: bool = False) -> dict:
    if status not in SERIES_STATUSES:
        raise GrankiError(f'Unknown series status {status!r}; use one of {", ".join(SERIES_STATUSES)}')
    load_series(path)
    meta, body = split_frontmatter(path.read_text(encoding='utf-8'))
    before = meta.get('status')
    allowed = SERIES_TRANSITIONS.get(before, set(SERIES_STATUSES))
    if status not in allowed and not force:
        raise GrankiError(f'Series transition {before} -> {status} is not allowed; allowed: {", ".join(sorted(allowed))}')
    meta['status'] = status
    save(path, meta, body)
    log_event(path.parent / 'journal.md', actor, f'статус плана серии: {before} → {status}')
    return {'status': 'passed', 'series': str(path), 'from': before, 'to': status}


def sync(path: Path, actor: str) -> dict:
    meta, body, plan = load(path)
    entries = meta.setdefault('sections', [])
    known = {e.get('file') for e in entries}
    added = []
    for file in section_paths(sections_dir(plan)):
        if file.name not in known:
            entries.append({'file': file.name, 'status': 'drafted'})
            added.append(file.name)
    entries.sort(key=lambda e: e.get('file', ''))
    if added:
        save(path, meta, body)
        log(plan, actor, 'в план добавлены разделы: ' + ', '.join(added))
    return {'status': 'passed', 'plan': str(path), 'added': added}


def git_commit(directory: Path) -> str | None:
    try:
        return subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=directory, capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def publish(path: Path, url: str | None, date: str | None, actor: str, html: Path | None = None,
            force: bool = False) -> dict:
    meta, body, plan = load(path)
    if plan['status'] not in ('ready',):
        raise GrankiError(f'Publish needs status "ready", the article is "{plan["status"]}"')
    shas = {p.name: sha256_text(p.read_text(encoding='utf-8')) for p in section_paths(sections_dir(plan))}
    # the author accepted a text; a later edit must be accepted again before it goes out
    changed = [e.get('file') for e in meta.get('sections', [])
               if e.get('status') != 'accepted' or shas.get(e.get('file')) != e.get('accepted_sha')]
    if changed and not force:
        raise GrankiError('Sections not accepted or changed after acceptance: ' + ', '.join(changed) +
                          '. Accept them again (plan.py section --set accepted), or pass --force')
    version = int(meta.get('version', 1))
    release = {'version': version, 'date': date or datetime.date.today().isoformat()}
    if url:
        release['url'] = url
    commit = git_commit(plan['_root'])
    if commit:
        release['commit'] = commit
    if html:
        if not html.is_file():
            raise GrankiError(f'HTML page not found: {html}')
        import hashlib
        release['html_sha256'] = hashlib.sha256(html.read_bytes()).hexdigest()
    release['sections'] = shas
    meta.setdefault('published', []).append(release)
    meta['status'] = 'published'
    save(path, meta, body)
    log(plan, actor, f'опубликована версия {version}' + (f': {url}' if url else ''))
    return {'status': 'passed', 'plan': str(path), 'version': version, 'sections': len(shas), 'commit': commit}


def revise(path: Path, actor: str) -> dict:
    meta, body, plan = load(path)
    if plan['status'] != 'published':
        raise GrankiError(f'Revise needs status "published", the article is "{plan["status"]}"')
    meta['version'] = int(meta.get('version', 1)) + 1
    meta['status'] = 'revising'
    save(path, meta, body)
    log(plan, actor, f'начата версия {meta["version"]}')
    return {'status': 'passed', 'plan': str(path), 'version': meta['version']}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=['status', 'section', 'entry', 'series', 'sync', 'publish', 'revise'])
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--series', type=Path, help='series-plan.md (series)')
    parser.add_argument('--caveats', help='comma-separated caveat IDs (entry)')
    parser.add_argument('--claims', help='comma-separated claim IDs (entry)')
    parser.add_argument('--after', help='insert the new entry after this section file (entry)')
    parser.add_argument('--set', help='new status (status, section)')
    parser.add_argument('--file', help='section file (section)')
    parser.add_argument('--url', help='published URL (publish)')
    parser.add_argument('--date', help='publication date YYYY-MM-DD (publish)')
    parser.add_argument('--html', type=Path, help='built HTML page of the article (publish)')
    parser.add_argument('--actor', default='агент')
    parser.add_argument('--force', action='store_true', help='allow a transition outside the lifecycle')
    args = parser.parse_args(argv)
    def ids(value):
        return None if value is None else [v.strip() for v in value.split(',') if v.strip()]

    try:
        if args.command == 'series':
            if not (args.series and args.set):
                raise GrankiError('series needs --series and --set')
            report = set_series(args.series, args.set, args.actor, args.force)
            sys.stdout.write(dump_json(report))
            return 0
        if not args.plan:
            raise GrankiError(f'{args.command} needs --plan')
        if args.command == 'entry':
            if not args.file:
                raise GrankiError('entry needs --file')
            report = upsert_entry(args.plan, args.file, ids(args.caveats), ids(args.claims), args.after, args.actor,
                                  args.set)
        elif args.command == 'status':
            if not args.set:
                raise GrankiError('status needs --set')
            report = set_status(args.plan, args.set, args.actor, args.force)
        elif args.command == 'section':
            if not (args.file and args.set):
                raise GrankiError('section needs --file and --set')
            report = set_section(args.plan, args.file, args.set, args.actor, args.force)
        elif args.command == 'sync':
            report = sync(args.plan, args.actor)
        elif args.command == 'publish':
            report = publish(args.plan, args.url, args.date, args.actor, args.html, args.force)
        else:
            report = revise(args.plan, args.actor)
    except (GrankiError, OSError) as error:
        sys.stdout.write(dump_json({'status': 'error', 'reason': str(error)}))
        return 2
    except Exception as error:
        sys.stdout.write(dump_json({'status': 'error', 'reason': f'{type(error).__name__}: {error}'}))
        return 2
    sys.stdout.write(dump_json(report))
    return 0


if __name__ == '__main__':
    sys.exit(main())
